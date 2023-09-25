import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Self
from collections.abc import Callable, Awaitable
from zoneinfo import ZoneInfo
import asyncio

import openai

from note import Note, NoteDB
from history import HistoryDB, Message, FunctionCall
import event
from coderunner import CodeRunner


TERMS = {
    "a day": 1,
    "a month": 30,
    "a year": 365,
    "forever": 1000 * 365,
}

EventHandler = Callable[[event.Event], Awaitable[None]]


class ThreadManager:
    __singleton: Self | None = None

    def __new__(cls, *args, **kwargs) -> "ThreadManager":
        if cls.__singleton is None:
            cls.__singleton = super().__new__(cls)

        return cls.__singleton

    def __init__(self, history: HistoryDB, notes: NoteDB) -> None:
        super().__init__()

        self.threads: dict[str, Thread] = {}
        self.history = history
        self.notes = notes

    def get(self, user_id: str) -> "Thread":
        if user_id not in self.threads:
            self.threads[user_id] = Thread(
                user_id,
                self.history,
                self.notes,
            )
        return self.threads[user_id]

    async def shutdown(self) -> None:
        await asyncio.gather(*[thread.shutdown() for thread in self.threads.values()])


class Thread:
    user_id: str
    history: HistoryDB
    notes: NoteDB
    event_handlers: list[EventHandler]
    timezone: ZoneInfo
    runners: dict[str, CodeRunner]

    def __init__(
        self,
        user_id: str,
        history: HistoryDB,
        notes: NoteDB,
        timezone: ZoneInfo = ZoneInfo("UTC"),
    ) -> None:
        self.user_id = user_id
        self.history = history
        self.notes = notes
        self.event_handlers = []
        self.timezone = timezone
        self.runners = {}

    async def shutdown(self) -> None:
        for runner in self.runners.values():
            await runner.shutdown()

    async def __event(self, event: event.Event) -> None:
        await asyncio.gather(*[handler(event) for handler in self.event_handlers])

    def subscribe(self, handler: EventHandler) -> Callable[[], None]:
        self.event_handlers.append(handler)

        def unsubscribe() -> None:
            self.event_handlers.remove(handler)

        return unsubscribe

    async def send_message(self, message: str) -> None:
        """Send a message to the thread.

        :param message: User message to send.
        """

        msg = Message(
            role="user",
            content=message,
        )

        self.history.put(self.user_id, msg)
        await self.__event(
            event.User(
                id=msg.id,
                content=message,
                complete=True,
                created_at=msg.created_at,
            )
        )

        await self.invoke()

    async def invoke(self) -> None:
        """Invoke AI using messages so far."""

        msg = Message(
            role="assistant",
        )

        last_user_msg = self.history.last_user_message(self.user_id)
        notes = []
        if last_user_msg is not None and last_user_msg.content is not None:
            notes = self.notes.query(
                self.user_id,
                last_user_msg.content,
            )
            n_tokens = 0
            for i, note in enumerate(notes):
                n_tokens += note.n_tokens
                if n_tokens > 1024:
                    notes = notes[:i]
                    break

        system_prompt = "\n".join(
            [
                "You are Hexe, a faithful AI assistant, and also a world-class programmer who can complete anything by executing code.",
                "",
                "If user changes the topic, write a note what you two talked about in the previous topic, and then respond to the new topic.",
                "Or if you learned new things, write it to notes to remember it.",
                "Too many notes are better than too few notes.",
                "",
                "If user asks you to do something, you write a plan first, and then execute it.",
                "Always recap progress and your plan between each step.",
                "You have only very short term memory, so you need to recap the plan to retain it.",
                "",
                "Keep each steps in the plan as short as possible, because simple steps are easier to achieve.",
                "Do write a shorter code, and test it more often.",
                "",
                "",
                f"Current datetime: {datetime.now(self.timezone).isoformat()}",
                "",
                "==========",
                "Notes:",
                (
                    "\n---\n".join(
                        [
                            f"{note.content} ({note.created_at.astimezone(self.timezone).isoformat()})"
                            for note in notes
                        ]
                    )
                    if len(notes) > 0
                    else "(Notes related to the topic are not found)"
                ),
            ]
        )

        completion = await openai.ChatCompletion.acreate(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                *(
                    msg.as_dict()
                    for msg in reversed([*self.history.load(self.user_id, 2 * 1024)])
                ),
            ],
            functions=[
                {
                    "name": "save_notes",
                    "description": "Save notes to remember it later.",
                    "parameters": {
                        "type": "object",
                        "required": ["notes"],
                        "properties": {
                            "notes": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "required": ["content", "available_term"],
                                    "properties": {
                                        "content": {
                                            "desctiption": "The content to save. Follow 5W1H method to write each note.",
                                            "type": "string",
                                        },
                                        "available_term": {
                                            "description": "How long the information is meaningful and useful.",
                                            "type": "string",
                                            "enum": list(TERMS.keys()),
                                        },
                                    },
                                },
                                "minItems": 1,
                            },
                        },
                    },
                },
                {
                    "name": "search_notes",
                    "description": "Search notes that you saved. The result include IDs, created timestamps, and note contents.",
                    "parameters": {
                        "type": "object",
                        "required": ["query"],
                        "properties": {
                            "query": {
                                "type": "string",
                            },
                        },
                    },
                },
                {
                    "name": "delete_notes",
                    "description": "Delete notes that you saved.",
                    "parameters": {
                        "type": "object",
                        "required": ["ids"],
                        "properties": {
                            "ids": {
                                "type": "array",
                                "items": {
                                    "type": "string",
                                },
                                "minItems": 1,
                            },
                        },
                    },
                },
                {
                    "name": "run_code",
                    "description": "Run code in a Jupyter environment, and returns the output and the result. To install packages, you can use `!pip install <package>` for Python, and `apt-get install <package>` for Bash.",
                    "parameters": {
                        "type": "object",
                        "required": ["language", "code"],
                        "properties": {
                            "language": {
                                "type": "string",
                                "enum": ["python", "bash"],
                            },
                            "code": {
                                "type": "string",
                            },
                        },
                    },
                },
                # {
                #    "name": "generate_image",
                # },
            ],
            user=self.user_id,
            stream=True,
        )

        async for chunk in completion:
            delta = chunk.choices[0].delta

            if "content" in delta:
                if msg.content is None:
                    msg.content = delta.content
                else:
                    msg.content += delta.content

                await self.__event(
                    event.Assistant(
                        id=msg.id,
                        content=delta.content,
                        created_at=msg.created_at,
                        complete=False,
                    )
                )

            if "function_call" in delta:
                if msg.function_call is None:
                    msg.function_call = FunctionCall(
                        name=delta.function_call.name,
                        arguments=delta.function_call.arguments,
                    )
                else:
                    msg.function_call.arguments += delta.function_call.arguments

                await self.__event(
                    event.FunctionCall(
                        id=msg.id,
                        name=msg.function_call.name,
                        arguments=delta.function_call.arguments,
                        created_at=msg.created_at,
                        complete=False,
                    )
                )

            if chunk.choices[0].get("finish_reason") is not None:
                self.history.put(self.user_id, msg)

                if chunk.choices[0].finish_reason == "length":
                    await self.__event(
                        event.Error(
                            id=msg.id,
                            content="Max tokens exceeded",
                        )
                    )
                elif chunk.choices[0].finish_reason == "function_call":
                    if msg.function_call is None:
                        await self.__event(
                            event.Error(
                                type="error",
                                id=msg.id,
                                content="Function call is not specified",
                            )
                        )
                        return

                    if msg.content is not None:
                        await self.__event(
                            event.Assistant(
                                id=msg.id,
                                content=msg.content,
                                complete=True,
                                created_at=msg.created_at,
                            )
                        )

                    await self.__event(
                        event.FunctionCall(
                            id=msg.id,
                            name=msg.function_call.name,
                            arguments=msg.function_call.arguments,
                            complete=True,
                            created_at=msg.created_at,
                        )
                    )

                    await self.call_function(
                        msg.id,
                        msg.function_call.name,
                        msg.function_call.arguments,
                    )
                    await self.invoke()
                elif chunk.choices[0].finish_reason == "stop":
                    if msg.content is not None:
                        await self.__event(
                            event.Assistant(
                                id=msg.id,
                                content=msg.content,
                                complete=True,
                                created_at=msg.created_at,
                            )
                        )

                    if msg.function_call is not None:
                        await self.__event(
                            event.FunctionCall(
                                id=msg.id,
                                name=msg.function_call.name,
                                arguments=msg.function_call.arguments,
                                complete=True,
                                created_at=msg.created_at,
                            )
                        )

    async def call_function(self, source: uuid.UUID, name: str, arguments: str) -> None:
        """Call a function and put the result to the history."""

        try:
            args = json.loads(arguments)
        except Exception as err:
            self.history.put(
                self.user_id,
                Message(
                    role="system",
                    content=f"Failed to parse arguments to call function `{name}`.\n> {err}\n\nGiven arguments:\n```json\n{arguments}\n```\n\nPlease fix the syntax and call `{name}` again.",
                ),
            )
            return

        msg: Message | None = Message(
            role="function",
            name=name,
            content="",
        )

        if name == "save_notes":
            msg = await self.call_save_notes(source, args)
        elif name == "search_notes":
            msg = await self.call_search_notes(source, args)
        elif name == "delete_notes":
            msg = await self.call_delete_notes(source, args)
        elif name == "run_code":
            msg = await self.call_run_code(source, args)
        # elif name == "generate_image":
        else:
            self.history.put(
                self.user_id,
                Message(
                    role="system",
                    content=f"Unknown function: `{name}`\nPlease use only given functions.",
                ),
            )
            return

        if msg is not None:
            self.history.put(self.user_id, msg)
            await self.__event(
                event.FunctionOutput(
                    id=msg.id,
                    name=name,
                    content="```json\n"
                    + (msg.content if msg.content is not None else "{}")
                    + "\n```",
                    source=source,
                    created_at=msg.created_at,
                    complete=True,
                )
            )

    async def call_save_notes(self, _: uuid.UUID, arguments: dict) -> Message | None:
        msg = Message(
            role="function",
            name="save_notes",
        )

        if not isinstance(arguments.get("notes"), list) or any(
            [not isinstance(note, dict) for note in arguments["notes"]]
        ):
            msg.content = (
                '{"error": "`notes` argument must be a non-empty list of objects."}'
            )
            return msg

        if any(
            [not isinstance(note.get("content"), str) for note in arguments["notes"]]
        ):
            msg.content = '{"error": "`content` property of `notes` argument must be a non-empty string."}'
            return msg

        if any(
            [
                note.get("available_term", "forever") not in TERMS
                for note in arguments["notes"]
            ]
        ):
            msg.content = '{"error": "`available_term` property of `notes` argument must be one of `a day`, `a month`, `a year`, or `forever`."}'
            return msg

        now = datetime.now(timezone.utc)
        notes = [
            Note(
                content=note["content"].strip(),
                created_at=now,
                expires_at=now
                + timedelta(days=TERMS[note.get("available_term", "forever")]),
            )
            for note in arguments["notes"]
            if len(note["content"].strip()) > 0
        ]

        if len(notes) == 0:
            msg.content = (
                '{"error": "`notes` argument must be a non-empty list of objects."}'
            )
            return msg

        try:
            self.notes.save(self.user_id, notes)
        except Exception as err:
            msg.content = json.dumps({"error": str(err)})
            return msg
        else:
            msg.content = json.dumps({"result": "succeed", "saved_notes": len(notes)})
            return msg

    async def call_search_notes(self, _: uuid.UUID, arguments: dict) -> Message | None:
        msg = Message(
            role="function",
            name="search_notes",
        )

        if "query" not in arguments:
            msg.content = '{"error": "`query` argument is required."}'
            return msg

        if not isinstance(arguments["query"], str):
            msg.content = '{"error": "`query` argument must be a non-empty string."}'
            return msg

        query = arguments["query"].strip()

        if len(query) == 0:
            msg.content = '{"error": "`query` argument must be a non-empty string."}'
            return msg

        try:
            all_result = self.notes.query(
                self.user_id, query, n_results=100, threshold=0.2
            )
        except Exception as err:
            msg.content = json.dumps({"error": str(err)})
            return msg

        if len(all_result) == 0:
            msg.content = '{"error": "No such notes found.", "rule": "Before report it to user, try again with different query at least 3 times."}'
            return msg

        n_tokens = 0
        for i, note in enumerate(all_result):
            n_tokens += note.n_tokens
            if n_tokens > 2048:
                limited_result = all_result[:i]
                break

        msg.content = (
            f'{{\n  "result": "Found {len(all_result)} notes."\n  "notes": [\n'
        )
        msg.content += "\n".join(
            [
                "  "
                + json.dumps(
                    {
                        "id": str(note.id),
                        "created_at": note.created_at.astimezone(
                            self.timezone
                        ).isoformat(),
                        "content": note.content,
                    }
                )
                for note in limited_result
            ]
        )
        msg.content += "\n  ]\n}"
        return msg

    async def call_delete_notes(self, _: uuid.UUID, arguments: dict) -> Message | None:
        msg = Message(
            role="function",
            name="delete_notes",
        )

        if "ids" not in arguments:
            msg.content = '{"error": "`ids` argument is required."}'
            return msg

        if not isinstance(arguments["ids"], list):
            msg.content = '{"error": "`ids` argument must be a non-empty list."}'
            return msg

        try:
            ids = [uuid.UUID(id) for id in arguments["ids"]]
        except Exception as err:
            msg.content = f'{{"error": "invalid `ids` argument: {err}"}}'
            return msg

        try:
            self.notes.delete(self.user_id, ids)
        except Exception as err:
            msg.content = json.dumps({"error": str(err)})
            return msg
        else:
            msg.content = json.dumps({"result": "succeed", "deleted_notes": len(ids)})
            return msg

    async def call_run_code(self, source: uuid.UUID, arguments: dict) -> Message | None:
        msg = Message(
            role="function",
            name="run_code",
        )

        supported_languages = ["python", "bash"]
        if (
            "language" not in arguments
            or arguments.get("language") not in supported_languages
        ):
            msg.content = f'{{"error": "`language` argument must be one of {supported_languages}."}}'
            return msg

        if (
            "code" not in arguments
            or not isinstance(arguments["code"], str)
            or len(arguments["code"].strip()) == 0
        ):
            msg.content = '{"error": "`code` argument must be a string."}'
            return msg

        language = arguments["language"]
        code = arguments["code"].strip()

        if language not in self.runners:
            self.runners[language] = CodeRunner("hexe_" + language)
            await self.runners[language].start()

        runner = self.runners[language]

        async for ev in runner.execute(source, code):
            await self.__event(ev)

            if ev.complete and (
                isinstance(ev, event.Error) or isinstance(ev, event.FunctionOutput)
            ):
                self.history.put(
                    self.user_id,
                    Message(
                        id=ev.id,
                        role="function",
                        name="run_code",
                        content=ev.content,
                        created_at=ev.created_at,
                    ),
                )

        return None
