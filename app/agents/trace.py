"""Execution trace: every routing decision, tool call and result, shown in the UI's activity panel."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TraceEvent:
    type: str
    agent: str
    title: str
    detail: Any
    elapsed_ms: int


class AgentTrace:
    def __init__(self) -> None:
        self._start = time.monotonic()
        self._events: list[TraceEvent] = []
        self._lock = threading.Lock()

    def add(self, type_: str, agent: str, title: str, detail: Any = None) -> None:
        with self._lock:
            self._events.append(TraceEvent(type_, agent, title, detail if detail is not None else {}, self.elapsed_ms))

    @property
    def events(self) -> list[TraceEvent]:
        return list(self._events)

    @property
    def elapsed_ms(self) -> int:
        return int((time.monotonic() - self._start) * 1000)
