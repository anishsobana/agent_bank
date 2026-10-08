"""Deterministic fallback router.

Used by the offline mock model, and by the Supervisor when the LLM's routing output can't be parsed,
so a model hiccup degrades gracefully instead of failing the request.
"""
from __future__ import annotations

import re

from .types import AgentType

FRAUD = re.compile(r"fraud|suspicious|unauthori[sz]ed|didn'?t make|did not make|don'?t recogni[sz]e|not recogni[sz]e"
                   r"|unknown (charge|transaction|debit)|block|freeze|stolen|lost (my )?card|dispute|chargeback|scam"
                   r"|hack|strange|unusual|risk|safe\b")
LOAN = re.compile(r"loan|emi|credit score|cibil|borrow|eligib|mortgage|interest rate|tenure|afford")
CUSTOMER = re.compile(r"balance|transaction|statement|spend|spent|transfer|send\b|pay\b|account|profile|beneficiar"
                      r"|money|salary")
CONFIRM = re.compile(r"^\s*(yes|yeah|yep|ok|okay|sure|confirm|confirmed|go ahead|proceed|do it|please do)\b")


def is_confirmation(message: str | None) -> bool:
    return bool(message and CONFIRM.match(message.lower()))


def keyword_route(message: str, previous: list[AgentType] | None = None) -> list[AgentType]:
    m = (message or "").lower()
    if is_confirmation(m) and previous:
        return [previous[-1]]
    out: list[AgentType] = []
    if FRAUD.search(m):
        out.append(AgentType.FRAUD_RISK)
    money_movement = "transfer" in m or "balance" in m
    if CUSTOMER.search(m) and (AgentType.FRAUD_RISK not in out or money_movement):
        out.append(AgentType.CUSTOMER_SERVICE)
    if LOAN.search(m):
        if AgentType.CUSTOMER_SERVICE in out and not money_movement:
            out.remove(AgentType.CUSTOMER_SERVICE)  # loan questions mention "account"/"salary" incidentally
        out.append(AgentType.CREDIT_LOAN)
    return out
