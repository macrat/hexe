import json
import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterator, Literal

from tokenizer import Tokenizer
import event


@dataclass
class FunctionCall:
    name: str
    arguments: str

    @staticmethod
    def from_json(s: str) -> "FunctionCall":
        """Create a FunctionCall from JSON string."""

        x = json.loads(s)
        return FunctionCall(
            name=x["name"],
            arguments=x.get("arguments", ""),
        )

    def as_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "arguments": self.arguments,
        }

    def as_json(self) -> str:
        return json.dumps(self.as_dict())


@dataclass(frozen=True)
class EventRecord:
    event: event.Event
    n_tokens: int


class HistoryDB:
    """Database for storing chat history."""

    def __init__(self, path: str) -> None:
        """Initialize the database.

        :param path: Path to the database. `:memory:` for in-memory database.
        """

        self.__conn = sqlite3.connect(path)

        with self.__conn as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    user_id TEXT NOT NULL,
                    id TEXT NOT NULL,
                    source TEXT,
                    created_at REAL NOT NULL,
                    type TEXT NOT NULL,
                    content TEXT,
                    function_name TEXT,
                    function_arguments TEXT,
                    PRIMARY KEY (id, user_id)
                )
            """
            )

    def put(self, user_id: str, ev: event.Event) -> None:
        """Save a message to the database."""

        if isinstance(ev, event.Status):
            return

        with self.__conn as conn:
            match ev:
                case event.User():
                    conn.execute(
                        """
                            REPLACE INTO events (user_id, id, created_at, type, content)
                            VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            user_id,
                            str(ev.id),
                            ev.created_at.timestamp(),
                            ev.type,
                            ev.content,
                        ),
                    )
                case event.Assistant():
                    conn.execute(
                        """
                            REPLACE INTO events (user_id, id, source, created_at, type, content)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            user_id,
                            str(ev.id),
                            str(ev.source),
                            ev.created_at.timestamp(),
                            ev.type,
                            ev.content,
                        ),
                    )
                case event.FunctionCall():
                    conn.execute(
                        """
                            REPLACE INTO events (user_id, id, source, created_at, type, function_name, function_arguments)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            user_id,
                            str(ev.id),
                            str(ev.source),
                            ev.created_at.timestamp(),
                            ev.type,
                            ev.name,
                            ev.arguments,
                        ),
                    )
                case event.FunctionOutput():
                    conn.execute(
                        """
                            REPLACE INTO events (user_id, id, source, created_at, type, function_name, content)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            user_id,
                            str(ev.id),
                            str(ev.source),
                            ev.created_at.timestamp(),
                            ev.type,
                            ev.name,
                            ev.content,
                        ),
                    )
                case event.Error():
                    conn.execute(
                        """
                            REPLACE INTO events (user_id, id, source, created_at, type, content)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            user_id,
                            str(ev.id),
                            str(ev.source),
                            ev.created_at.timestamp(),
                            ev.type,
                            ev.content,
                        ),
                    )
                case _:
                    print(f"Unknown event type: {ev.type}")

    def load(
        self,
        user_id: str,
        limit: int,
        since: datetime | None = None,
        until: datetime | None = None,
        order: Literal["ASC", "DESC"] = "ASC",
    ) -> Iterator[EventRecord]:
        """Load chat history of the user, limit by number of messages."""

        if since is None:
            since = datetime.fromtimestamp(0, timezone.utc)

        if until is None:
            until = datetime.now()

        cursor = self.__conn.cursor()
        cursor.execute(
            f"""
                SELECT id, created_at, type, content, function_name, function_arguments, source
                FROM events
                WHERE user_id = ? AND ? <= created_at AND created_at < ?
                ORDER BY created_at {order}
                LIMIT ?
            """,
            (user_id, since.timestamp(), until.timestamp(), limit),
        )

        for (
            id,
            created_at,
            type,
            content,
            function_name,
            function_arguments,
            source,
        ) in cursor:
            ev: event.Event | None = None
            n_tokens: int = 0

            if content is not None:
                content = str(content)
            if function_name is not None:
                function_name = str(function_name)
            if function_arguments is not None:
                function_arguments = str(function_arguments)

            match type:
                case "user":
                    ev = event.User(
                        id=uuid.UUID(id),
                        created_at=datetime.fromtimestamp(created_at, timezone.utc),
                        content=content,
                    )
                    n_tokens = Tokenizer().count(content)
                case "assistant":
                    ev = event.Assistant(
                        id=uuid.UUID(id),
                        created_at=datetime.fromtimestamp(created_at, timezone.utc),
                        content=content,
                        source=uuid.UUID(source),
                    )
                    n_tokens = Tokenizer().count(content)
                case "function_call":
                    ev = event.FunctionCall(
                        id=uuid.UUID(id),
                        created_at=datetime.fromtimestamp(created_at, timezone.utc),
                        name=function_name,
                        arguments=function_arguments,
                        source=uuid.UUID(source),
                    )
                    n_tokens = Tokenizer().count(
                        json.dumps(
                            {
                                "name": function_name,
                                "arguments": function_arguments,
                            }
                        )
                    )
                case "function_output":
                    ev = event.FunctionOutput(
                        id=uuid.UUID(id),
                        created_at=datetime.fromtimestamp(created_at, timezone.utc),
                        name=function_name,
                        content=content,
                        source=uuid.UUID(source),
                    )
                    n_tokens = Tokenizer().count(content)
                case "error":
                    ev = event.Error(
                        id=uuid.UUID(id),
                        created_at=datetime.fromtimestamp(created_at, timezone.utc),
                        content=content,
                        source=uuid.UUID(source),
                    )
                    n_tokens = Tokenizer().count(content)
                case _:
                    continue

            yield EventRecord(
                event=ev,
                n_tokens=n_tokens,
            )

    def load_by_tokens(self, user_id: str, tokens_limit: int) -> Iterator[EventRecord]:
        """Load chat history of the user, limit by total number of tokens."""

        n_tokens = 0
        until = None

        while n_tokens < tokens_limit:
            itr = self.load(user_id, limit=10, until=until, order="DESC")

            n = 0
            for rec in itr:
                if n_tokens + rec.n_tokens > tokens_limit:
                    break

                n_tokens += rec.n_tokens
                until = rec.event.created_at
                yield rec

                n += 1

            if n == 0:
                break

    def last_user_event(self, user_id: str) -> event.User | None:
        """Get the last event from the user."""

        with self.__conn as conn:
            result = conn.execute(
                """
                SELECT id, content, created_at
                FROM events
                WHERE user_id = ? AND type = 'user'
                ORDER BY created_at DESC
                LIMIT 1
            """,
                (user_id,),
            ).fetchone()

        if result is None:
            return None

        return event.User(
            id=uuid.UUID(result[0]),
            content=result[1],
            created_at=datetime.fromtimestamp(result[2], timezone.utc),
        )

    def last_user_message(self, user_id: str) -> str | None:
        """Get the last message from the user."""

        ev = self.last_user_event(user_id)
        if ev is None:
            return None

        return ev.content
