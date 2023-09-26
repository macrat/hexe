import uuid
import json
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Literal
from abc import abstractmethod


EventType = Literal[
    "user", "assistant", "function_call", "function_output", "status", "error"
]

EventDict = dict[str, str | float | bool]


@dataclass(init=False)
class Event:
    id: uuid.UUID
    created_at: datetime
    complete: bool

    def __init__(
        self,
        id: uuid.UUID,
        created_at: datetime | None = None,
        complete: bool = False,
    ) -> None:
        self.id = id
        self.complete = complete

        if created_at is None:
            self.created_at = datetime.now(timezone.utc)
        else:
            self.created_at = created_at

    @property
    @abstractmethod
    def type(self) -> EventType:
        ...

    def as_dict(self) -> EventDict:
        return {
            "type": self.type,
            "id": str(self.id),
            "created_at": self.created_at.timestamp(),
            "complete": self.complete,
        }

    def as_json(self) -> str:
        return json.dumps(self.as_dict())


@dataclass
class User(Event):
    content: str
    type: Literal["user"] = "user"

    def as_dict(self) -> EventDict:
        return {
            **super().as_dict(),
            "content": self.content,
        }


@dataclass
class Assistant(Event):
    content: str
    type: Literal["assistant"] = "assistant"

    def as_dict(self) -> EventDict:
        return {
            **super().as_dict(),
            "content": self.content,
        }


@dataclass
class FunctionCall(Event):
    name: str
    arguments: str
    type: Literal["function_call"] = "function_call"

    def as_dict(self) -> EventDict:
        return {
            **super().as_dict(),
            "name": self.name,
            "arguments": self.arguments,
        }


@dataclass
class FunctionOutput(Event):
    name: str
    content: str
    source: uuid.UUID
    type: Literal["function_output"] = "function_output"

    def as_dict(self) -> EventDict:
        return {
            **super().as_dict(),
            "name": self.name,
            "content": self.content,
            "source": str(self.source),
        }


@dataclass
class Status(Event):
    source: uuid.UUID | None
    generating: bool
    type: Literal["status"] = "status"

    def __init__(
        self,
        *args,
        id: uuid.UUID | None = None,
        source: uuid.UUID | None = None,
        generating: bool = False,
        **kwargs
    ) -> None:
        self.source = source
        self.generating = generating

        if id is None:
            id = uuid.uuid4()

        super().__init__(
            *args,
            **{
                **kwargs,
                "id": id,
                "complete": True,
            }
        )

    def as_dict(self) -> EventDict:
        return {
            **super().as_dict(),
            "source": str(self.source),
            "generating": self.generating,
        }


@dataclass
class Error(Event):
    content: str
    source: uuid.UUID | None
    type: Literal["error"] = "error"

    def __init__(
        self, *args, content: str = "", source: uuid.UUID | None = None, **kwargs
    ) -> None:
        self.content = content
        self.source = source
        super().__init__(
            *args,
            **{
                **kwargs,
                "complete": True,
            }
        )
        self.source = source

    def as_dict(self) -> EventDict:
        return {
            **super().as_dict(),
            "source": str(self.source),
            "content": self.content,
        }
