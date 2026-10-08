"""Short-term conversational memory per chat session (in-memory; Redis with TTL in production)."""
from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass

from .types import AgentType


@dataclass(frozen=True)
class Turn:
    user: str
    assistant: str
    agents: list[AgentType]


class ConversationStore:
    def __init__(self, max_turns: int = 6) -> None:
        self._max = max_turns
        self._sessions: dict[str, deque[Turn]] = {}
        self._lock = threading.Lock()

    def history(self, key: str) -> list[Turn]:
        with self._lock:
            return list(self._sessions.get(key, ()))

    def append(self, key: str, turn: Turn) -> None:
        with self._lock:
            self._sessions.setdefault(key, deque(maxlen=self._max)).append(turn)

    def clear(self, key: str) -> None:
        with self._lock:
            self._sessions.pop(key, None)
