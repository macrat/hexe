import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from typing import AsyncIterator

from fastapi import Cookie, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

import event
from auth import Auth, User
from history import HistoryDB
from note import NoteDB
from thread import Thread, ThreadManager

app = FastAPI()
history: HistoryDB | None = None
thread_manager: ThreadManager | None = None
auth: Auth | None = None


@app.on_event("startup")
def startup() -> None:
    global history
    global thread_manager
    global auth

    os.makedirs("./db", exist_ok=True)

    history = HistoryDB("./db/history.db")
    thread_manager = ThreadManager(
        history,
        NoteDB("./db/notes", uuid.uuid5(uuid.NAMESPACE_DNS, "notes")),
    )

    auth = Auth("./db/auth.db")

    try:
        # DEBUG
        # TODO: Remove this
        auth.register("Test User", "user1", "user1")
    except Exception:
        pass


@app.on_event("shutdown")
async def shutdown() -> None:
    if thread_manager is not None:
        await thread_manager.shutdown()


async def userinfo(session: str | None = Cookie(None)) -> User:
    if auth is None:
        raise HTTPException(503, detail="Server not ready yet.")
    if session is None:
        raise HTTPException(401, detail="Login required.")

    try:
        return auth.get_user(session)
    except ValueError:
        raise HTTPException(401, detail="Login required.")


class LoginRequest(BaseModel):
    id: str
    password: str


class LoginResponse(BaseModel):
    message: str


@app.post("/api/login")
async def login(
    request: LoginRequest,
    response: Response,
) -> LoginResponse:
    if auth is None:
        raise HTTPException(503, detail="Server not ready yet.")

    max_age = 365 * 24 * 60 * 60

    try:
        token = auth.login(request.id, request.password, expires_in=max_age)
    except ValueError:
        return JSONResponse(
            status_code=401,
            content={
                "message": "Login failed.",
            },
        )

    response.set_cookie(
        "session",
        token,
        httponly=True,
        max_age=max_age,
        path="/",
        samesite="strict",
        secure=True,
    )

    return {
        "message": "Success",
    }


@app.get("/api/user")
async def get_user(user: User = Depends(userinfo)) -> User:
    return user


class EventsResponse(BaseModel):
    events: list[event.EventDict]


@app.post("/api/events")
async def post_events(
    request: Request, user: User = Depends(userinfo)
) -> EventsResponse:
    if thread_manager is None:
        raise HTTPException(503, detail="Server not ready yet.")

    content_type = request.headers.get("content-type")
    if content_type is None or content_type.split(";")[0] != "text/plain":
        raise HTTPException(400, detail="The content type must be text/plain.")

    content = (await request.body()).decode("utf-8")

    if len(content) == 0:
        raise HTTPException(400, detail="The content must not be empty.")

    async def collect_messages(thread: Thread) -> list[event.EventDict]:
        messages: list[event.EventDict] = []
        async for ev in thread.stream():
            match ev:
                case event.Status(generating=False):
                    return messages
                case event.Assistant() | event.FunctionCall() | event.FunctionOutput() | event.Error() if not ev.delta:
                    messages.append(ev.as_dict())
        return messages

    thread = thread_manager.get(user)

    messages, _ = await asyncio.gather(
        collect_messages(thread),
        thread.send_message(content),
    )

    return {
        "events": messages,
    }


@app.get("/api/events", response_model=EventsResponse)
async def get_events(
    limit: int = 20,
    since: int = 0,
    until: int | None = None,
    stream: bool = False,
    user: User = Depends(userinfo),
) -> EventsResponse | StreamingResponse:
    if thread_manager is None or history is None:
        raise HTTPException(503, detail="Server not ready yet.")

    if stream:
        thread = thread_manager.get(user)

        async def stream_events() -> AsyncIterator[str]:
            for r in reversed(list(history.load(user.id, limit=limit, order="DESC"))):
                yield f"data: {r.event.as_json()}\n\n"

            with thread.stream() as stream:
                while True:
                    try:
                        ev = await asyncio.wait_for(
                            asyncio.shield(stream.get()), timeout=60
                        )
                        yield f"data: {ev.as_json()}\n\n"
                    except asyncio.TimeoutError:
                        yield "event: heartbeat\n\n"

        return StreamingResponse(stream_events(), media_type="text/event-stream")
    else:
        return {
            "events": [
                x.event.as_dict()
                for x in history.load(
                    user.id,
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
