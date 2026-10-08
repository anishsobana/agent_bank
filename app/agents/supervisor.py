"""The orchestrator's brain: an LLM call that classifies intent and plans which specialists run, in which order,
with which sub-task. A second call merges findings when more than one specialist ran."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from ..llm.base import LlmClient, LlmError, LlmMessage
from . import prompts
from .memory import Turn
from .router import keyword_route
from .trace import AgentTrace
from .types import AgentType

log = logging.getLogger(__name__)

HELP = ("Hi! I'm AgentBank's assistant. I can check balances and transactions, analyse spending, make transfers, "
        "investigate suspicious activity, block cards, and help with loans and EMIs. What would you like to do?")


@dataclass
class RoutingDecision:
    agents: list[AgentType]
    reason: str = ""
    tasks: dict[AgentType, str] = field(default_factory=dict)
    direct_reply: str = ""
    fallback_used: bool = False


class SupervisorAgent:
    def __init__(self, llm: LlmClient) -> None:
        self.llm = llm

    def route(self, message: str, history: list[Turn], trace: AgentTrace) -> RoutingDecision:
        lines: list[str] = []
        if history:
            lines.append("Conversation so far:")
            for t in history:
                lines += [f"Customer: {t.user}", f"Bank: {t.assistant[:600]}"]
            lines.append("")
        previous = history[-1].agents if history else []
        lines += [f"{prompts.LAST_AGENTS} {','.join(a.value for a in previous)}", "",
                  prompts.LATEST_MESSAGE, message]

        decision: RoutingDecision | None
        try:
            raw = self.llm.chat(prompts.SUPERVISOR, [LlmMessage.user("\n".join(lines))], []).text
            decision = self.parse(raw, message)
        except LlmError as e:
            log.warning("Routing via LLM failed, using keyword fallback: %s", e)
            decision = None
        if decision is None:
            agents = keyword_route(message, previous)
            decision = RoutingDecision(agents, "Keyword fallback routing", {a: message for a in agents},
                                       "" if agents else HELP, fallback_used=True)

        detail = {"agents": decision.agents, "reason": decision.reason, "tasks": decision.tasks}
        if decision.fallback_used:
            detail["note"] = "LLM routing unavailable - deterministic fallback used"
        title = ("Routed to " + " → ".join(a.label for a in decision.agents)) if decision.agents else "Answered directly"
        trace.add("ROUTE", "SUPERVISOR", title, detail)
        return decision

    @staticmethod
    def parse(raw: str | None, message: str) -> RoutingDecision | None:
        if not raw:
            return None
        start, end = raw.find("{"), raw.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            data = json.loads(raw[start:end + 1])
        except ValueError:
            return None
        agents: list[AgentType] = []
        for name in data.get("agents") or []:
            t = AgentType.parse(str(name))
            if t and t not in agents:
                agents.append(t)
        tasks: dict[AgentType, str] = {}
        for k, v in (data.get("tasks") or {}).items():
            t = AgentType.parse(k)
            if t:
                tasks[t] = str(v)
        for a in agents:
            tasks.setdefault(a, message)
        direct = str(data.get("directReply") or "")
        if not agents and not direct.strip():
            direct = HELP
        return RoutingDecision(agents, str(data.get("reason") or ""), tasks, direct)

    def synthesize(self, message: str, findings: dict[AgentType, str], trace: AgentTrace) -> str:
        parts = [f"Customer's request:\n{message}\n"]
        parts += [f"[{a.label} findings]\n{text}\n" for a, text in findings.items()]
        try:
            merged = self.llm.chat(prompts.SYNTHESIS, [LlmMessage.user("\n".join(parts))], []).text
        except LlmError as e:
            log.warning("Synthesis failed, concatenating findings: %s", e)
            merged = ""
        if not merged.strip():
            merged = "\n\n---\n\n".join(findings.values())
        trace.add("SYNTHESIS", "SUPERVISOR", f"Merged {len(findings)} agent responses")
        return merged
