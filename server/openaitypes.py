from typing import Literal, TypedDict


class UserMessage(TypedDict):
    role: Literal["user"]
    content: str


class AssistantMessage(TypedDict):
    role: Literal["assistant"]
    content: str


class FunctionCall(TypedDict):
    name: str
    arguments: str


class FunctionCallMessage(TypedDict):
    role: Literal["assistant"]
    content: str | None
    function_call: FunctionCall


class FunctionOutputMessage(TypedDict):
    role: Literal["function"]
    name: str
    content: str


class SystemMessage(TypedDict):
    role: Literal["system"]
    content: str


Message = (
    UserMessage
    | AssistantMessage
    | FunctionCallMessage
    | FunctionOutputMessage
    | SystemMessage
)
