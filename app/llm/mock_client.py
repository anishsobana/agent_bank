"""Offline stand-in for an LLM, so the whole multi-agent pipeline (routing, tool calls, tracing) can be demoed and
tested without an API key. It picks tools with keyword rules and returns raw tool output; a real model is needed
for natural-language answers. Select a real provider with LLM_PROVIDER."""
from __future__ import annotations

import json
import re
import uuid
from decimal import Decimal

from ..agents import prompts
from ..agents.router import is_confirmation, keyword_route
from ..agents.types import AgentType
from .base import LlmMessage, LlmResponse, ToolCall, ToolSpec

TXN = re.compile(r"\bTXN-[A-Z0-9-]+", re.I)
CARD = re.compile(r"\bCARD-[A-Z0-9-]+|(?<![\d-])\d{4}(?!\d)", re.I)
ACCOUNT = re.compile(r"\bACC\d{6,}", re.I)
TENURE = re.compile(r"(\d+)\s*(years?|yrs?|months?|mos?)\b", re.I)
AMOUNT = re.compile(r"(?<![A-Za-z0-9-])(₹|rs\.?\s*|inr\s*)?(\d[\d,]*(?:\.\d+)?)\s*(lakhs?|lacs?|l|crores?|cr|k)?(?![A-Za-z0-9])", re.I)
NOT_AMOUNT_SUFFIX = re.compile(r"^\s*(days?|months?|mos?|years?|yrs?|transactions?|txns?|times)\b", re.I)


def parse_amount(text: str) -> Decimal | None:
    """'₹1,20,000' -> 120000, '5 lakh' -> 500000, '10k' -> 10000; ignores '30 days', '8.5%'."""
    fallback = None
    for m in AMOUNT.finditer(text):
        rest = text[m.end():]
        unit = (m.group(3) or "").lower()
        if not unit and NOT_AMOUNT_SUFFIX.match(rest):
            continue
        if rest.startswith("%"):
            continue
        value = Decimal(m.group(2).replace(",", ""))
        if unit.startswith("l"):
            value *= 100_000
        elif unit.startswith("c"):
            value *= 10_000_000
        elif unit == "k":
            value *= 1_000
        if m.group(1) or unit:
            return value  # explicit currency or unit wins
        if fallback is None and value >= 100:
            fallback = value
    return fallback


def parse_tenure_months(text: str) -> int | None:
    m = TENURE.search(text)
    if not m:
        return None
    n = int(m.group(1))
    return n * 12 if m.group(2).lower().startswith("y") else n


def _between(text: str, start: str, end: str) -> str:
    i = text.find(start)
    if i < 0:
        return text
    s = i + len(start)
    e = text.find(end, s)
    return (text[s:] if e < 0 else text[s:e]).strip()


def _after(text: str, marker: str) -> str:
    i = text.find(marker)
    return text if i < 0 else text[i + len(marker):]


def _any(text: str, *needles: str) -> bool:
    return any(n in text for n in needles)


def _call(name: str, args: dict) -> ToolCall:
    return ToolCall(f"mock_{uuid.uuid4().hex[:8]}", name, args)


class MockLlmClient:
    def chat(self, system: str, messages: list[LlmMessage], tools: list[ToolSpec]) -> LlmResponse:
        last_user = next((m.text for m in reversed(messages) if m.role == "user"), "")
        if prompts.ROUTING_MARKER in system:
            return LlmResponse(self._route(last_user))
        if prompts.SYNTHESIS_MARKER in system:
            return LlmResponse("_(Offline mock mode - findings shown as returned by each agent)_\n\n"
                               + _after(last_user, "\n\n").strip())
        if messages[-1].role == "tool":
            return LlmResponse(self._summarise(messages))
        available = [t.name for t in tools]
        call = self._pick_tool(_between(messages[-1].text, prompts.CUSTOMER_SAID, "\n\n"), available, messages)
        if call is None:
            return LlmResponse("_(Offline mock mode)_ I couldn't map that request to a banking action. "
                               "Try a sample prompt, or configure a real LLM provider for free-form conversation.")
        return LlmResponse("", [call])

    def describe(self) -> str:
        return "mock / offline (no LLM)"

    # ------------------------------------------------------------------ routing / summaries
    def _route(self, prompt: str) -> str:
        latest = _after(prompt, prompts.LATEST_MESSAGE).strip()
        previous = [a for a in (AgentType.parse(x) for x in _between(prompt, prompts.LAST_AGENTS, "\n").split(",")) if a]
        agents = keyword_route(latest, previous)
        return json.dumps({
            "agents": [a.value for a in agents],
            "reason": "Keyword match (mock router)" if agents else "No banking intent detected (mock keyword router)",
            "tasks": {a.value: latest for a in agents},
            "directReply": "" if agents else ("_(Offline mock mode)_ Hi! I can help with balances, transactions, "
                                              "spending, transfers, suspicious activity, card blocking, and loans. "
                                              "Try a sample prompt on the left."),
        })

    @staticmethod
    def _summarise(messages: list[LlmMessage]) -> str:
        results: list[LlmMessage] = []
        for m in reversed(messages):
            if m.role != "tool":
                break
            results.insert(0, m)
        out = ["_(Offline mock mode - raw results from the banking APIs; connect an LLM for a conversational answer)_"]
        for r in results:
            try:
                pretty = json.dumps(json.loads(r.text), indent=2, ensure_ascii=False)
            except ValueError:
                pretty = r.text
            out.append(f"\n**{r.tool_name}**\n```json\n{pretty}\n```")
            if r.tool_name == "transfer_funds" and '"PREVIEW"' in r.text:
                out.append("\nReply **confirm** to execute this transfer.")
        return "\n".join(out)

    # ------------------------------------------------------------------ tool selection
    def _pick_tool(self, text: str, tools: list[str], messages: list[LlmMessage]) -> ToolCall | None:
        t = text.lower()
        has = tools.__contains__
        txn = TXN.search(text)
        txn_id = txn.group().upper() if txn else None

        if has("transfer_funds") and is_confirmation(t):
            original = next((m.text for m in reversed(messages[:-1])
                             if m.role == "user" and re.search(r"transfer|send|pay", m.text, re.I)), None)
            if original:
                return self._transfer(original, confirmed=True)
        if has("block_card") and _any(t, "block", "freeze", "lost", "stolen", "didn't make", "did not make", "not mine"):
            args = {"reason": f"Customer reported: {text}"}
            card = CARD.search(text)
            if card:
                args["card_id"] = card.group()
            return _call("block_card", args)
        if has("raise_dispute") and _any(t, "dispute", "chargeback", "refund"):
            args = {"reason": f"Customer reported: {text}"}
            if txn_id:
                args["transaction_id"] = txn_id
            return _call("raise_dispute", args)
        if has("analyze_transaction_risk") and txn_id:
            return _call("analyze_transaction_risk", {"transaction_id": txn_id})
        if has("scan_account_for_anomalies") and _any(t, "suspicious", "fraud", "unusual", "strange", "unknown",
                                                       "recogni", "scan", "safe", "risk", "weird", "hack"):
            return _call("scan_account_for_anomalies", {})
        if has("transfer_funds") and _any(t, "transfer", "send ", "pay "):
            return self._transfer(text, confirmed=False)
        if has("apply_for_loan") and "apply" in t:
            return _call("apply_for_loan", {**self._loan_args(text), "purpose": "Applied via chat"})
        if has("get_existing_loans") and _any(t, "status", "application", "my loan", "existing loan", "outstanding", "due"):
            return _call("get_existing_loans", {})
        if has("check_loan_eligibility") and _any(t, "eligib", "qualify", "can i get", "how much loan", "afford", "loan"):
            if "emi" in t and not _any(t, "eligib", "qualify", "can i get", "afford"):
                return _call("calculate_emi", self._emi_args(text))
            return _call("check_loan_eligibility", self._loan_args(text))
        if has("calculate_emi") and "emi" in t:
            return _call("calculate_emi", self._emi_args(text))
        if has("get_credit_profile") and _any(t, "credit score", "cibil", "score"):
            return _call("get_credit_profile", {})
        if has("get_spending_summary") and _any(t, "spend", "spent", "category", "where did", "budget"):
            return _call("get_spending_summary", {})
        if has("get_recent_transactions") and _any(t, "transaction", "statement", "history", "debit", "charge"):
            return _call("get_recent_transactions", {"limit": 10})
        if has("list_beneficiaries") and _any(t, "beneficiar", "payee"):
            return _call("list_beneficiaries", {})
        if has("get_account_balances") and _any(t, "balance", "how much money", "account"):
            return _call("get_account_balances", {})
        if has("get_customer_profile") and _any(t, "profile", "details", "kyc", "email", "phone"):
            return _call("get_customer_profile", {})
        first = tools[0] if tools else None  # default: the agent's "overview" tool
        return None if first in (None, "transfer_funds", "apply_for_loan") else _call(first, {})

    @staticmethod
    def _transfer(text: str, confirmed: bool) -> ToolCall:
        args: dict = {"confirmed": confirmed}
        amount = parse_amount(text)
        if amount is not None:
            args["amount"] = float(amount)
        acc = ACCOUNT.search(text)
        if acc:
            args["to_account"] = acc.group().upper()
        name = re.search(r"\bto\s+(?!acc)([a-z]+)", text, re.I)
        if name:
            args["beneficiary_name"] = name.group(1)
        return _call("transfer_funds", args)

    @staticmethod
    def _loan_args(text: str) -> dict:
        t = text.lower()
        kind = ("HOME" if _any(t, "home", "house") else "CAR" if _any(t, "car", "vehicle")
                else "EDUCATION" if _any(t, "education", "study") else "BUSINESS" if "business" in t else "PERSONAL")
        amount = parse_amount(text)
        args = {"loan_type": kind, "amount": float(amount) if amount is not None else 500000}
        tenure = parse_tenure_months(text)
        if tenure:
            args["tenure_months"] = tenure
        return args

    def _emi_args(self, text: str) -> dict:
        args = self._loan_args(text)
        args["principal"] = args.pop("amount")
        args.setdefault("tenure_months", 36)
        rate = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
        if rate:
            args["annual_rate"] = float(rate.group(1))
        return args
