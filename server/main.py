import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from typing import AsyncIterator, TypedDict

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, StreamingResponse

import event
from history import HistoryDB
from note import NoteDB
from thread import Thread, ThreadManager

app = FastAPI()
history: HistoryDB | None = None
thread_manager: ThreadManager | None = None


@app.on_event("startup")
def startup() -> None:
    global history
    global thread_manager

    os.makedirs("./db", exist_ok=True)

    history = HistoryDB("./db/history.db")
    thread_manager = ThreadManager(
        history,
        NoteDB("./db/notes", uuid.uuid5(uuid.NAMESPACE_DNS, "notes")),
    )


@app.on_event("shutdown")
async def shutdown() -> None:
    if thread_manager is not None:
        await thread_manager.shutdown()


@app.get("/")
async def get() -> HTMLResponse:
    return HTMLResponse(
        """
        <html>
            <head>
                <title>Chat</title>
            </head>
            <body>
                <ol id='messages'></ol>
                <form action="" onsubmit="sendMessage(event)">
                    <textarea id="messageText"></textarea>
                    <button>Send</button>
                </form>
                <script>
                    const messages = document.getElementById('messages');

                    const ws = new WebSocket("ws://localhost:8000/api/events");
                    ws.onmessage = function(event) {
                        const data = JSON.parse(event.data);

                        if (!data.delta) {
                            console.log(data);
                            return;
                        }
                        const message = document.createElement('li');
                        message.classList.add(data.type);

                        const type = document.createElement('b');
                        type.appendChild(document.createTextNode(data.type));
                        message.appendChild(type);

                        message.appendChild(document.createTextNode(': '));

                        if (data.type === 'function_call') {
                            const content = document.createTextNode(`${data.name}(${data.arguments})`);
                            message.appendChild(content);
                        } else if (data.type === 'status') {
                            const content = document.createTextNode(`[generating=${data.generating}]`);
                            message.appendChild(content);
                        } else {
                            const content = document.createTextNode(data.content);
                            message.appendChild(content);
                        }

                        messages.appendChild(message);
                    };

                    const input = document.getElementById("messageText");
                    function sendMessage(event) {
                        event.preventDefault();
                        ws.send(JSON.stringify({
                            type: 'message',
                            content: input.value,
                        }));
                        input.value = '';
                    }
                </script>
            </body>
        </html>
    """
    )


class PostMessageResponse(TypedDict):
    messages: list[event.EventDict]


@app.post("/api/messages")
async def post_message(request: Request) -> PostMessageResponse:
    if thread_manager is None:
        raise HTTPException(503, detail="Server not ready yet.")

    content_type = request.headers.get("content-type")
    if content_type is None or content_type.split(";")[0] != "text/plain":
        raise HTTPException(400, detail="The content type must be text/plain.")

    content = (await request.body()).decode("utf-8")

    async def collect_messages(thread: Thread) -> list[event.EventDict]:
        messages: list[event.EventDict] = []
        async for ev in thread.stream():
            match ev:
                case event.Status(generating=False):
                    return messages
                case event.Assistant() | event.FunctionCall() | event.FunctionOutput() | event.Error() if not ev.delta:
                    messages.append(ev.as_dict())
        return messages

    thread = thread_manager.get("user1")

    messages, _ = await asyncio.gather(
        collect_messages(thread),
        thread.send_message(content),
    )

    return {
        "messages": messages,
    }


class GetEventsResponse(TypedDict):
    events: list[event.EventDict]


@app.get("/api/events", response_model=GetEventsResponse)
async def get_events(
    limit: int = 20, since: int = 0, until: int | None = None, stream: bool = False
) -> GetEventsResponse | StreamingResponse:
    if thread_manager is None or history is None:
        raise HTTPException(503, detail="Server not ready yet.")

    if stream:
        thread = thread_manager.get("user1")

        async def stream_events() -> AsyncIterator[str]:
            for er in reversed(list(history.load("user1", limit=limit, order="DESC"))):
                yield "data: " + er.event.as_json() + "\n\n"

            async for ev in thread.stream():
                yield "data: " + ev.as_json() + "\n\n"

        return StreamingResponse(stream_events(), media_type="text/event-stream")
    else:
        return {
            "events": [
                x.event.as_dict()
                for x in history.load(
                    "user1",
                    limit=limit,
                    since=(
                        datetime.fromtimestamp(since, tz=timezone.utc)
                        if since
                        else None
                    ),
                    until=(
                        datetime.fromtimestamp(until, tz=timezone.utc)
                        if until
                        else None
                    ),
                )
            ],
        }


@app.websocket("/api/events")
async def websocket_events(websocket: WebSocket):
    if thread_manager is None:
        raise HTTPException(503, detail="Server not ready yet.")

    await websocket.accept()

    async def on_event(event):
        await websocket.send_json(event.as_dict())

    thread = thread_manager.get("user1")
    thread.subscribe(on_event)

    while True:
        try:
            data = json.loads(await websocket.receive_text())
        except WebSocketDisconnect:
            thread.unsubscribe(on_event)
            break

        if data.get("type") == "message":
            await thread.send_message(data.get("content", ""))
