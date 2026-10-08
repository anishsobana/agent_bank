"""Provider-neutral chat + tool-calling types. Each client converts these to its own wire format."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

Role = Literal["user", "assistant", "tool"]

@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]
    # Provider-specific fields that must be echoed back unchanged on the next request,
    # e.g. Gemini's thought signature ("extra_content"). Never interpreted by our code.
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class LlmMessage:
    role: Role
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None
    tool_name: str | None = None

    @staticmethod
    def user(text: str) -> "LlmMessage":
        return LlmMessage("user", text)

    @staticmethod
    def assistant(text: str, tool_calls: list[ToolCall] | None = None) -> "LlmMessage":
        return LlmMessage("assistant", text or "", list(tool_calls or []))

    @staticmethod
    def tool_result(call_id: str, name: str, result_json: str) -> "LlmMessage":
        return LlmMessage("tool", result_json, tool_call_id=call_id, tool_name=name)


@dataclass(frozen=True)
class LlmResponse:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


class LlmError(RuntimeError):
    pass


class LlmClient(Protocol):
    def chat(self, system: str, messages: list[LlmMessage], tools: list[ToolSpec]) -> LlmResponse: ...

    def describe(self) -> str: ...
