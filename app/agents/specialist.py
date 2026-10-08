"""A domain agent = system prompt + allow-listed tools + a tool-calling (ReAct-style) loop."""
from __future__ import annotations

import json
import logging
from datetime import date

from ..bank.errors import BankError
from ..bank.models import Customer
from ..bank.money import to_jsonable
from ..llm.base import LlmClient, LlmMessage, ToolCall
from ..tools.toolkit import Tool, ToolContext
from .memory import Turn
from .trace import AgentTrace
from .types import AgentType

log = logging.getLogger(__name__)


class SpecialistAgent:
    def __init__(self, type_: AgentType, system_prompt: str, tools: list[Tool], llm: LlmClient,
                 max_iterations: int = 6) -> None:
        self.type = type_
        self.system_prompt = system_prompt
        self.tools = {t.name: t for t in tools}
        self.llm = llm
        self.max_iterations = max_iterations

    @property
    def tool_names(self) -> list[str]:
        return list(self.tools)

    def run(self, task: str, history: list[Turn], customer: Customer, ctx: ToolContext, trace: AgentTrace) -> str:
        system = self.system_prompt + (
            "\nSession context:\n"
            f"- Authenticated customer: {customer.name} (customer id {customer.id}, {customer.segment}, {customer.city})\n"
            f"- Today's date: {date.today().isoformat()}\n")
        messages: list[LlmMessage] = []
        for t in history:
            messages += [LlmMessage.user(t.user), LlmMessage.assistant(t.assistant)]
        messages.append(LlmMessage.user(task))
        specs = [t.spec for t in self.tools.values()]
        trace.add("AGENT_START", self.type.value, f"{self.type.label} agent started",
                  {"task": task, "tools": self.tool_names})

        for _ in range(self.max_iterations):
            res = self.llm.chat(system, messages, specs)
            if not res.has_tool_calls:
                answer = res.text or "I couldn't produce an answer for that - please rephrase."
                trace.add("AGENT_RESPONSE", self.type.value, f"{self.type.label} agent finished", {"response": answer})
                return answer
            if res.text:
                trace.add("THOUGHT", self.type.value, "Reasoning", {"text": res.text})
            messages.append(LlmMessage.assistant(res.text, res.tool_calls))
            for call in res.tool_calls:
                messages.append(LlmMessage.tool_result(call.id, call.name, self._execute(call, ctx, trace)))

        trace.add("AGENT_RESPONSE", self.type.value, "Iteration budget exhausted")
        return "I wasn't able to finish this request automatically. A relationship manager will follow up."

    def _execute(self, call: ToolCall, ctx: ToolContext, trace: AgentTrace) -> str:
        trace.add("TOOL_CALL", self.type.value, call.name, call.arguments)
        tool = self.tools.get(call.name)
        error = True
        if tool is None:  # least privilege: an agent can only call tools it was granted
            result = {"error": f"Tool '{call.name}' is not available to the {self.type.label} agent"}
        else:
            try:
                result, error = to_jsonable(tool.handler(ctx, call.arguments or {})), False
            except (BankError, ValueError) as e:
                result = {"error": str(e)}
            except Exception:  # noqa: BLE001 - never leak internals to the model
                log.exception("Tool %s failed", call.name)
                result = {"error": f"Internal error while calling {call.name}"}
        trace.add("TOOL_ERROR" if error else "TOOL_RESULT", self.type.value, call.name, result)
        return json.dumps(result, ensure_ascii=False)
