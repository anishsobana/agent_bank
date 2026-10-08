"""Banking domain models. Money is always Decimal; transaction amounts are positive with a direction."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True)
class Customer:
    id: str
    name: str
    email: str
    phone: str
    city: str
    segment: str
    customer_since: date
    kyc_status: str


@dataclass(frozen=True)
class Account:
    account_number: str
    customer_id: str
    type: str
    branch: str
    balance: Decimal
    currency: str
    status: str

    def with_balance(self, balance: Decimal) -> "Account":
        return replace(self, balance=balance)


@dataclass(frozen=True)
class Card:
    card_id: str
    customer_id: str
    type: str
    network: str
    last4: str
    status: str
    daily_limit: Decimal
    linked_account: str

    def with_status(self, status: str) -> "Card":
        return replace(self, status=status)


@dataclass(frozen=True)
class Transaction:
    id: str
    account_number: str
    timestamp: datetime
    description: str
    merchant: str
    category: str
    amount: Decimal
    direction: str  # DEBIT | CREDIT
    channel: str
    location: str
    country: str
    card_id: str | None
    status: str = "POSTED"

    @property
    def is_debit(self) -> bool:
        return self.direction == "DEBIT"


@dataclass(frozen=True)
class Beneficiary:
    name: str
    account_number: str
    bank: str
    relationship: str


@dataclass(frozen=True)
class CreditProfile:
    customer_id: str
    credit_score: int
    bureau: str
    monthly_income: Decimal
    existing_monthly_emi: Decimal
    employment_type: str
    employment_years: int
    missed_payments_last_12m: int


@dataclass(frozen=True)
class Loan:
    loan_id: str
    customer_id: str
    type: str
    principal: Decimal
    outstanding: Decimal
    annual_rate: float
    tenure_months: int
    emi: Decimal
    status: str
    next_due_date: date


@dataclass(frozen=True)
class LoanApplication:
    application_id: str
    customer_id: str
    loan_type: str
    amount: Decimal
    tenure_months: int
    offered_rate: float
    emi: Decimal
    status: str
    notes: list[str]
    submitted_at: datetime


@dataclass(frozen=True)
class Dispute:
    dispute_id: str
    customer_id: str
    transaction_id: str
    amount: Decimal
    reason: str
    status: str
    created_at: datetime
    expected_resolution: str


@dataclass(frozen=True)
class RiskAssessment:
    """Output of the rule-based risk engine: score 0-100, level LOW / MEDIUM / HIGH."""
    subject: str
    score: int
    level: str
    signals: list[str] = field(default_factory=list)
    recommendation: str = ""
