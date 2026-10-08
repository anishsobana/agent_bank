from __future__ import annotations

from ..config import LlmSettings
from .base import LlmClient


def create_llm_client(s: LlmSettings | None = None) -> LlmClient:
    s = s or LlmSettings.from_env()
    if s.provider in ("anthropic", "claude"):
        from .anthropic_client import AnthropicClient
        return AnthropicClient(s)
    if s.provider in ("openai", "openai-compatible", "gemini", "groq", "ollama"):
        from .openai_client import OpenAICompatibleClient
        return OpenAICompatibleClient(s)
    if s.provider in ("mock", "offline"):
        from .mock_client import MockLlmClient
        return MockLlmClient()
    raise ValueError(f"Unknown LLM_PROVIDER '{s.provider}' (expected mock | anthropic | openai)")
