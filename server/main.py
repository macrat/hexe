import json
import uuid
import os
from datetime import datetime
from datetime import timezone
from typing import AsyncIterator
import asyncio

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from history import HistoryDB
from note import NoteDB
import event
from thread import ThreadManager, Thread


app = FastAPI()
history: HistoryDB | None = None
thread_manager: ThreadManager | None = None


@app.on_event("startup")
def startup():
    global history
    global thread_manager

    os.makedirs("./db", exist_ok=True)

    history = HistoryDB("./db/history.db")
    thread_manager = ThreadManager(
        history,
        NoteDB("./db/notes", uuid.uuid5(uuid.NAMESPACE_DNS, "notes")),
    )


@app.on_event("shutdown")
async def shutdown():
    await thread_manager.shutdown()


@app.get("/")
async def get():
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


@app.post("/api/message")
async def post_message(request: Request):
    if thread_manager is None:
        return JSONResponse(
            {
                "error": "Server not ready yet.",
            },
            status_code=503,
        )

    content_type = request.headers.get("content-type")
    if content_type is None or content_type.split(";")[0] != "text/plain":
        return JSONResponse(
            {
                "error": "The content type must be text/plain.",
            },
            status_code=400,
        )

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


@app.get("/api/events")
async def get_events(
    limit: int = 20, since: int = 0, until: int | None = None, stream: bool = False
):
    if thread_manager is None or history is None:
        return JSONResponse(
            {
                "error": "Server not ready yet.",
            },
            status_code=503,
        )

    if stream:
        thread = thread_manager.get("user1")

        async def stream_events() -> AsyncIterator[str]:
            for er in reversed(list(history.load("user1", limit=limit, order="DESC"))):
                yield er.event.as_json() + "\n"

            async for ev in thread.stream():
                yield ev.as_json() + "\n"

        return StreamingResponse(stream_events(), media_type="application/x-ndjson")
    else:
        return {
            "events": [
                x.event
                for x in history.load(
                    "user1",
                    limit=limit,
                    since=datetime.fromtimestamp(since, tz=timezone.utc)
                    if since
                    else None,
                    until=datetime.fromtimestamp(until, tz=timezone.utc)
                    if until
                    else None,
                )
            ]
        }


@app.websocket("/api/events")
async def websocket_events(websocket: WebSocket):
    await websocket.accept()

    if thread_manager is None:
        await websocket.send_json({"type": "error", "content": "Server not ready yet."})
        await websocket.close()
        return

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
