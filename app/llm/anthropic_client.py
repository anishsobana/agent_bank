"""Claude via the Anthropic Messages API (native tool use), using plain HTTP."""
from __future__ import annotations

from typing import Any

from ..config import LlmSettings
from .base import LlmMessage, LlmResponse, ToolCall, ToolSpec
from .http import post_json


class AnthropicClient:
    def __init__(self, s: LlmSettings) -> None:
        if not s.api_key:
            raise ValueError("LLM_API_KEY is required for the anthropic provider")
        self.model = s.model or "claude-sonnet-5-5"
        self.url = (s.base_url or "https://api.anthropic.com").rstrip("/") + "/v1/messages"
        self.s = s

    def chat(self, system: str, messages: list[LlmMessage], tools: list[ToolSpec]) -> LlmResponse:
        body: dict[str, Any] = {"model": self.model, "max_tokens": self.s.max_tokens,
                                "temperature": self.s.temperature, "system": system,
                                "messages": self._wire(messages)}
        if tools:
            body["tools"] = [{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in tools]
        res = post_json(self.url, {"x-api-key": self.s.api_key, "anthropic-version": "2023-06-01"}, body, self.s.timeout)
        text, calls = [], []
        for block in res.get("content", []):
            if block.get("type") == "text":
                text.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                calls.append(ToolCall(block["id"], block["name"], block.get("input") or {}))
        return LlmResponse("".join(text).strip(), calls)

    @staticmethod
    def _wire(messages: list[LlmMessage]) -> list[dict]:
        """Anthropic expects consecutive tool results as tool_result blocks inside one user turn."""
        out: list[dict] = []
        pending: list[dict] = []
        for m in messages:
            if m.role == "tool":
                pending.append({"type": "tool_result", "tool_use_id": m.tool_call_id, "content": m.text})
                continue
            if pending:
                out.append({"role": "user", "content": pending})
                pending = []
            if m.role == "user":
                out.append({"role": "user", "content": m.text})
            else:
                content: list[dict] = []
                if m.text.strip():
                    content.append({"type": "text", "text": m.text})
                content += [{"type": "tool_use", "id": c.id, "name": c.name, "input": c.arguments} for c in m.tool_calls]
                out.append({"role": "assistant", "content": content or [{"type": "text", "text": "(no content)"}]})
        if pending:
            out.append({"role": "user", "content": pending})
        return out

    def describe(self) -> str:
        return f"anthropic / {self.model}"
