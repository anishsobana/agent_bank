"""Configuration from environment variables (a local .env file is loaded if present)."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _optional_float(name: str, default: str) -> float | None:
    """Blank or 'none' disables the setting (the parameter is then not sent at all)."""
    raw = os.getenv(name, default).strip().lower()
    return None if raw in ("", "none", "off") else float(raw)


GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
GEMINI_DEFAULT_MODEL = "gemini-3.8-flash"


def _is_gemini(base_url: str) -> bool:
    return "generativelanguage.googleapis.com" in base_url


@dataclass(frozen=True)
class LlmSettings:
    provider: str = "openai"         # openai (any OpenAI-compatible API, incl. Gemini) | gemini | anthropic | mock
    model: str = ""
    api_key: str = ""
    base_url: str = ""
    max_tokens: int = 4096
    temperature: float | None = 0.2  # skipped automatically for gemini-3.x models
    timeout: float = 120.0
    max_retries: int = 3
    reasoning_effort: str = ""       # low | medium | high (blank = not sent)

    @staticmethod
    def from_env() -> "LlmSettings":
        provider = os.getenv("LLM_PROVIDER", "openai").strip().lower() or "openai"
        openai_like = provider not in ("anthropic", "claude", "mock", "offline")
        base_url = os.getenv("LLM_BASE_URL", GEMINI_BASE_URL if openai_like else "").strip()
        on_gemini = openai_like and _is_gemini(base_url or GEMINI_BASE_URL)
        effort = os.getenv("LLM_REASONING_EFFORT", "low" if on_gemini else "").strip().lower()
        return LlmSettings(
            provider=provider,
            model=os.getenv("LLM_MODEL", GEMINI_DEFAULT_MODEL if on_gemini else "").strip(),
            api_key=os.getenv("LLM_API_KEY", "").strip(),
            base_url=base_url,
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", "4096")),
            temperature=_optional_float("LLM_TEMPERATURE", "0.2"),
            timeout=float(os.getenv("LLM_TIMEOUT_SECONDS", "120")),
            max_retries=max(0, int(os.getenv("LLM_MAX_RETRIES", "3"))),
            reasoning_effort="" if effort in ("none", "off") else effort,
        )


MAX_TOOL_ITERATIONS = int(os.getenv("AGENT_MAX_TOOL_ITERATIONS", "6"))
HISTORY_TURNS = int(os.getenv("AGENT_HISTORY_TURNS", "6"))