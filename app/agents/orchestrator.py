"""Entry point for a chat turn: Supervisor routes -> specialists run sequentially (each sees earlier findings)
-> Supervisor synthesises -> turn stored in conversation memory. Returns the reply plus a full trace."""
from __future__ import annotations

from dataclasses import dataclass

from ..bank.service import CoreBankingService
from ..config import HISTORY_TURNS, MAX_TOOL_ITERATIONS
from ..llm.base import LlmClient
from ..tools.toolkit import BankingToolkit, ToolContext
from . import prompts
from .memory import ConversationStore, Turn
from .specialist import SpecialistAgent
from .supervisor import SupervisorAgent
from .trace import AgentTrace, TraceEvent
from .types import AgentType


@dataclass(frozen=True)
class ChatResult:
    reply: str
    agents: list[AgentType]
    trace: list[TraceEvent]
    elapsed_ms: int


def build_agents(toolkit: BankingToolkit, llm: LlmClient, max_iter: int) -> dict[AgentType, SpecialistAgent]:
    """Wires each specialist with its prompt and its least-privilege tool set."""
    return {
        AgentType.CUSTOMER_SERVICE: SpecialistAgent(AgentType.CUSTOMER_SERVICE, prompts.CUSTOMER_SERVICE, toolkit.subset(
            "get_customer_profile", "get_account_balances", "get_recent_transactions", "get_spending_summary",
            "list_beneficiaries", "transfer_funds"), llm, max_iter),
        AgentType.FRAUD_RISK: SpecialistAgent(AgentType.FRAUD_RISK, prompts.FRAUD_RISK, toolkit.subset(
            "scan_account_for_anomalies", "get_recent_transactions", "analyze_transaction_risk", "list_cards",
            "block_card", "raise_dispute"), llm, max_iter),
        AgentType.CREDIT_LOAN: SpecialistAgent(AgentType.CREDIT_LOAN, prompts.CREDIT_LOAN, toolkit.subset(
            "get_credit_profile", "get_existing_loans", "check_loan_eligibility", "calculate_emi", "apply_for_loan",
            "get_spending_summary"), llm, max_iter),
    }


class Orchestrator:
    def __init__(self, llm: LlmClient, bank: CoreBankingService | None = None,
                 max_iterations: int = MAX_TOOL_ITERATIONS, history_turns: int = HISTORY_TURNS) -> None:
        self.llm = llm
        self.bank = bank or CoreBankingService()
        self.supervisor = SupervisorAgent(llm)
        self.agents = build_agents(BankingToolkit(self.bank), llm, max_iterations)
        self.memory = ConversationStore(history_turns)

    def handle(self, session_id: str, customer_id: str, message: str) -> ChatResult:
        customer = self.bank.get_customer(customer_id)  # validates the session's customer
        ctx = ToolContext(customer_id, session_id)
        key = f"{session_id}:{customer_id}"
        history = self.memory.history(key)
        trace = AgentTrace()
        trace.add("REQUEST", "SUPERVISOR", "Customer message received", {"message": message, "customer": customer.name})

        decision = self.supervisor.route(message, history, trace)
        if not decision.agents:
            reply = decision.direct_reply
        else:
            findings: dict[AgentType, str] = {}
            for agent_type in decision.agents:
                task = self._task(message, decision.tasks.get(agent_type, message), findings)
                findings[agent_type] = self.agents[agent_type].run(task, history, customer, ctx, trace)
            reply = next(iter(findings.values())) if len(findings) == 1 else \
                self.supervisor.synthesize(message, findings, trace)

        trace.add("DONE", "SUPERVISOR", "Response ready")
        self.memory.append(key, Turn(message, reply, decision.agents))
        return ChatResult(reply, decision.agents, trace.events, trace.elapsed_ms)

    @staticmethod
    def _task(message: str, task: str, findings: dict[AgentType, str]) -> str:
        text = f"{prompts.CUSTOMER_SAID} {message}\n\n{prompts.YOUR_TASK} {task}"
        if findings:
            text += f"\n\n{prompts.PEER_FINDINGS}\n" + "\n".join(f"[{a.label}]\n{f}" for a, f in findings.items())
        return text

    def reset(self, session_id: str, customer_id: str) -> None:
        self.memory.clear(f"{session_id}:{customer_id}")
