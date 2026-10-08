from __future__ import annotations

from enum import Enum


class AgentType(str, Enum):
    CUSTOMER_SERVICE = "CUSTOMER_SERVICE"
    FRAUD_RISK = "FRAUD_RISK"
    CREDIT_LOAN = "CREDIT_LOAN"

    @property
    def label(self) -> str:
        return {"CUSTOMER_SERVICE": "Customer Service", "FRAUD_RISK": "Fraud & Risk",
                "CREDIT_LOAN": "Credit & Loans"}[self.value]

    @staticmethod
    def parse(value: str | None) -> "AgentType | None":
        if not value:
            return None
        n = value.strip().upper().replace(" ", "_").replace("&", "_").replace("__", "_")
        if n in AgentType.__members__:
            return AgentType[n]
        if "FRAUD" in n or "RISK" in n:
            return AgentType.FRAUD_RISK
        if "LOAN" in n or "CREDIT" in n:
            return AgentType.CREDIT_LOAN
        if "CUSTOMER" in n or "BANKING" in n or "ACCOUNT" in n:
            return AgentType.CUSTOMER_SERVICE
        return None
