"""Any OpenAI-compatible /chat/completions endpoint with function calling:
OpenAI, Google Gemini (OpenAI compatibility layer), Groq, Ollama, LM Studio, vLLM, OpenRouter..."""
from __future__ import annotations

import json
import uuid
from typing import Any

from ..config import LlmSettings
from .base import LlmMessage, LlmResponse, ToolCall, ToolSpec
from .http import post_json


class OpenAICompatibleClient:
    def __init__(self, s: LlmSettings) -> None:
        self.model = s.model or "gpt-4o-mini"
        self.url = (s.base_url or "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
        self.s = s

    def chat(self, system: str, messages: list[LlmMessage], tools: list[ToolSpec]) -> LlmResponse:
        wire: list[dict[str, Any]] = [{"role": "system", "content": system}]
        for m in messages:
            if m.role == "user":
                wire.append({"role": "user", "content": m.text})
            elif m.role == "tool":
                wire.append({"role": "tool", "tool_call_id": m.tool_call_id, "content": m.text})
            else:
                msg: dict[str, Any] = {"role": "assistant", "content": m.text or ""}
                if m.tool_calls:
                    msg["tool_calls"] = [{**c.extra,"id": c.id, "type": "function",
                                          "function": {"name": c.name, "arguments": json.dumps(c.arguments)}}
                                         for c in m.tool_calls]
                wire.append(msg)
        body: dict[str, Any] = {"model": self.model, "max_tokens": self.s.max_tokens,
                                "temperature": self.s.temperature, "messages": wire}
        if tools:
            body["tools"] = [{"type": "function", "function": {"name": t.name, "description": t.description,
                                                                "parameters": t.input_schema}} for t in tools]
            body["tool_choice"] = "auto"
        headers = {"Authorization": f"Bearer {self.s.api_key}"} if self.s.api_key else {}
        res = post_json(self.url, headers, body, self.s.timeout)
        msg = (res.get("choices") or [{}])[0].get("message", {})
        calls = []
        for c in msg.get("tool_calls") or []:
            fn = c.get("function", {})
            extra = {k: v for k, v in c.items() if k not in ("id", "type", "function", "index")}
            calls.append(ToolCall(c.get("id") or f"call_{uuid.uuid4().hex[:8]}", fn.get("name", ""),
                _parse_args(fn.get("arguments")), extra))
        content = msg.get("content")
        return LlmResponse(content.strip() if isinstance(content, str) else "", calls)

    def describe(self) -> str:
        return f"openai-compatible / {self.model}"


def _parse_args(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError):
        return {}
