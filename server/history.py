import json
import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterator

from tokenizer import Tokenizer


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


@dataclass
class Message:
    id: uuid.UUID
    role: str
    _content: str | None
    name: str | None
    _function_call: FunctionCall | None
    _n_tokens: int
    created_at: datetime

    def __init__(
        self,
        role: str,
        content: str | None = None,
        id: uuid.UUID | None = None,
        name: str | None = None,
        function_call: FunctionCall | None = None,
        n_tokens: int | None = None,
        created_at: datetime | None = None,
    ) -> None:
        if role not in ["system", "assistant", "user", "function"]:
            raise ValueError(f"Invalid role: {role}")

        if role != "function" and name is not None:
            raise ValueError("name must be specified only when role is function")
        if role == "function" and name is None:
            raise ValueError("name must be specified when role is function")

        if id is None:
            self.id = uuid.uuid4()
        else:
            self.id = id

        self.role = role
        self._content = content
        self.name = name
        self._function_call = function_call

        if n_tokens is not None:
            self._n_tokens = n_tokens
        else:
            self.__update_n_tokens()

        if created_at is None:
            self.created_at = datetime.now(timezone.utc)
        else:
            self.created_at = created_at

    def __update_n_tokens(self) -> None:
        self._n_tokens = 0
        if self._content is not None:
            self._n_tokens += Tokenizer().count(self._content)
        if self._function_call is not None:
            self._n_tokens += Tokenizer().count(self._function_call.as_json())

    @property
    def content(self) -> str | None:
        return self._content

    @content.setter
    def content(self, value: str | None) -> None:
        self._content = value
        self.__update_n_tokens()

    @property
    def function_call(self) -> FunctionCall | None:
        return self._function_call

    @function_call.setter
    def function_call(self, value: FunctionCall | None) -> None:
        self._function_call = value
        self.__update_n_tokens()

    @property
    def n_tokens(self) -> int:
        return self._n_tokens

    def trim(self) -> "Message":
        """Remove unnecessary information for AI from the function output.
        If the message is not from function, or the message is short enough,
        the message is returned as-is.
        """

        if self.role != "function" or self.n_tokens <= 512 or self.content is None:
            return self

        m = re.match(
            r'^<(?<tag>img|video) src="data:(image|video)/[-+_a-zA-Z0-9]+;base64,[^"]+" (controls="controls" )?alt="(?P<alt>[^"]+)" />$',
            self.content,
        )
        if m is not None:
            return Message(
                role="function",
                content=f'<{m.group("tag")} alt="{m.group("alt")}" src="/*The media has shown, but the URL in the chat history has omitted.*/" />',
                name=self.name,
                function_call=self.function_call,
                created_at=self.created_at,
            )

        return self

    def as_dict(self) -> dict[str, str | None | dict[str, str]]:
        """Convert the message to a dictionary that can used in OpenAI library."""

        if self.content is None and self.function_call is None:
            raise ValueError("Either content or function_call must be specified")

        result: dict[str, str | None | dict[str, str]] = {
            "role": self.role,
            "content": self.content,
        }

        if self.name is not None:
            result["name"] = self.name

        if self.function_call is not None:
            result["function_call"] = self.function_call.as_dict()

        return result


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
                CREATE TABLE IF NOT EXISTS history (
                    id TEXT PRIMARY KEY NOT NULL,
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT,
                    name TEXT,
                    function_call TEXT,
                    n_tokens INTEGER NOT NULL,
                    created_at REAL NOT NULL
                )
            """
            )

    def put(self, user_id: str, message: Message) -> None:
        """Save a message to the database."""

        with self.__conn as conn:
            conn.execute(
                """
                INSERT INTO history (
                    id,
                    user_id,
                    role,
                    content,
                    name,
                    function_call,
                    n_tokens,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    str(message.id),
                    user_id,
                    message.role,
                    message.content,
                    message.name,
                    (
                        message.function_call.as_json()
                        if message.function_call is not None
                        else None
                    ),
                    message.n_tokens,
                    message.created_at.timestamp(),
                ),
            )

    def load_n(
        self, user_id: str, n: int, until: datetime | None = None
    ) -> Iterator[Message]:
        """Load chat history of the user, limit by number of messages."""

        if until is None:
            until = datetime.now()

        cursor = self.__conn.cursor()
        cursor.execute(
            """
            SELECT id, role, content, name, function_call, n_tokens, created_at
            FROM history
            WHERE user_id = ? AND created_at < ?
            ORDER BY created_at DESC
            LIMIT ?
        """,
            (user_id, until.timestamp(), n),
        )

        for id_, role, content, name, function_call, n_tokens, created_at in cursor:
            yield Message(
                id=uuid.UUID(id_),
                role=role,
                content=content,
                name=name,
                function_call=FunctionCall.from_json(function_call)
                if function_call is not None
                else None,
                n_tokens=n_tokens,
                created_at=datetime.fromtimestamp(created_at, timezone.utc),
            )

    def load(self, user_id: str, tokens_limit: int) -> Iterator[Message]:
        """Load chat history of the user, limit by total number of tokens."""

        n_tokens = 0
        until = None

        while n_tokens < tokens_limit:
            itr = self.load_n(user_id, 10, until)

            n = 0
            for msg in itr:
                if n_tokens + msg.n_tokens > tokens_limit:
                    break

                n_tokens += msg.n_tokens
                until = msg.created_at
                yield msg

                n += 1

            if n == 0:
                break

    def last_user_message(self, user_id: str) -> Message | None:
        """Get the last message of the user."""

        with self.__conn as conn:
            result = conn.execute(
                """
                SELECT id, content, created_at, n_tokens
                FROM history
                WHERE user_id = ? AND role = 'user'
                ORDER BY created_at DESC
                LIMIT 1
            """,
                (user_id,),
            ).fetchone()

        if result is None:
            return None

        return Message(
            id=uuid.UUID(result[0]),
            role="user",
            content=result[1],
            created_at=datetime.fromtimestamp(result[2], timezone.utc),
            n_tokens=result[3],
        )
