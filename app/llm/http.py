from __future__ import annotations

from typing import Any

import httpx

from .base import LlmError


def post_json(url: str, headers: dict[str, str], body: dict[str, Any], timeout: float) -> dict[str, Any]:
    try:
        res = httpx.post(url, headers={"Content-Type": "application/json", **headers}, json=body, timeout=timeout)
    except httpx.HTTPError as e:
        raise LlmError(f"LLM call failed: {e}") from e
    if res.status_code >= 300:
        raise LlmError(f"LLM API returned HTTP {res.status_code}: {res.text[:500]}")
    return res.json()
