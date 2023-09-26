import json
import uuid
import os
from datetime import datetime
from datetime import timezone

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from history import HistoryDB
from note import NoteDB
import event
from thread import ThreadManager


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

                        if (!data.complete) {
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


@app.websocket("/api/events")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    if thread_manager is None:
        await websocket.send_json({"type": "error", "content": "Server not ready."})
        await websocket.close()
        return

    async def on_event(event):
        await websocket.send_json(event.as_dict())

    thread = thread_manager.get("user1")
    unsubscribe = thread.subscribe(on_event)

    while True:
        try:
            data = json.loads(await websocket.receive_text())
        except WebSocketDisconnect:
            unsubscribe()
            break

        if data.get("type") == "message":
            await thread.send_message(data.get("content", ""))
