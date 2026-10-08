"""All tools available to agents, defined once.

Each tool = JSON-schema contract + handler bound to the simulated banking APIs. Agents are granted subsets
(least privilege): only Customer Service can move money, only Fraud & Risk can block cards.
The customer id comes from ToolContext (the authenticated session), never from model-supplied arguments.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from ..bank.service import CoreBankingService
from ..llm.base import ToolSpec

LOAN_TYPES = ["PERSONAL", "HOME", "CAR", "EDUCATION", "BUSINESS"]


@dataclass(frozen=True)
class ToolContext:
    customer_id: str
    session_id: str


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    schema: dict[str, Any]
    handler: Callable[[ToolContext, dict[str, Any]], Any]

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(self.name, self.description, self.schema)


def schema(properties: dict[str, dict] | None = None, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": properties or {}, "required": required or []}


def prop(type_: str, description: str, enum: list[str] | None = None) -> dict:
    p = {"type": type_, "description": description}
    if enum:
        p["enum"] = enum
    return p


# ---- lenient argument readers (models sometimes send numbers as strings like "₹1,20,000")
def a_str(args: dict, name: str) -> str | None:
    v = args.get(name)
    return None if v is None else str(v).strip()


def a_dec(args: dict, name: str) -> Decimal | None:
    v = args.get(name)
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        raise ValueError(f"'{name}' must be a number")
    if isinstance(v, (int, float)):
        return Decimal(str(v))
    s = str(v).replace("₹", "").replace(",", "").strip()
    for prefix in ("rs.", "rs", "inr"):
        if s.lower().startswith(prefix):
            s = s[len(prefix):].strip()
    try:
        return Decimal(s) if s else None
    except InvalidOperation:
        raise ValueError(f"'{name}' must be a number, got '{v}'")


def a_int(args: dict, name: str, default: int) -> int:
    v = a_dec(args, name)
    return default if v is None else int(v)


def a_bool(args: dict, name: str) -> bool:
    v = args.get(name)
    return v if isinstance(v, bool) else str(v).strip().lower() == "true"


class BankingToolkit:
    def __init__(self, bank: CoreBankingService) -> None:
        b = bank
        tools = [
            # ---------------------------------------------------------- customer / accounts
            Tool("get_customer_profile",
                 "Get the authenticated customer's profile: name, contact details, city, segment, KYC status.",
                 schema(), lambda c, a: b.get_customer(c.customer_id)),
            Tool("get_account_balances",
                 "List the customer's accounts with type, branch, current balance and status.",
                 schema(), lambda c, a: b.get_accounts(c.customer_id)),
            Tool("get_recent_transactions",
                 "Get recent transactions (newest first) with id, date, merchant, category, amount, direction, "
                 "channel, location and card used.",
                 schema({"limit": prop("integer", "Max transactions to return (default 10, max 50)"),
                         "days": prop("integer", "Look-back window in days (default 30)"),
                         "category": prop("string", "Optional category filter, e.g. FOOD, SHOPPING, RENT, EMI, TRANSFER")}),
                 lambda c, a: b.recent_transactions(c.customer_id, a_int(a, "limit", 10), a_str(a, "category"),
                                                    a_int(a, "days", 30))),
            Tool("get_spending_summary",
                 "Summarise spending by category, total spent, total received and net cash flow for a period.",
                 schema({"days": prop("integer", "Look-back window in days (default 30)")}),
                 lambda c, a: b.spending_summary(c.customer_id, a_int(a, "days", 30))),
            Tool("list_beneficiaries", "List the customer's registered payees (beneficiaries) for fund transfers.",
                 schema(), lambda c, a: b.get_beneficiaries(c.customer_id)),
            Tool("transfer_funds",
                 "Transfer money (IMPS) from the customer's primary account. Two-step: call with confirmed=false for a "
                 "preview that includes a fraud-risk check; only call with confirmed=true after the customer has "
                 "explicitly confirmed in a later message. HIGH-risk transfers are held for review.",
                 schema({"beneficiary_name": prop("string", "Registered beneficiary name or relationship (e.g. 'Amma', 'Karthik')"),
                         "to_account": prop("string", "Payee account number if not a registered beneficiary"),
                         "amount": prop("number", "Amount in INR"),
                         "note": prop("string", "Optional remark"),
                         "confirmed": prop("boolean", "false = preview only, true = execute (requires explicit customer confirmation)")},
                        ["amount", "confirmed"]),
                 lambda c, a: b.transfer(c.customer_id, a_str(a, "beneficiary_name"), a_str(a, "to_account"),
                                         a_dec(a, "amount"), a_str(a, "note"), a_bool(a, "confirmed"))),
            # ---------------------------------------------------------- fraud / risk
            Tool("list_cards", "List the customer's debit and credit cards with card id, network, last 4 digits and status.",
                 schema(), lambda c, a: b.get_cards(c.customer_id)),
            Tool("scan_account_for_anomalies",
                 "Run the fraud rules over recent transactions and return those with MEDIUM or HIGH risk, with signals.",
                 schema({"days": prop("integer", "Look-back window in days (default 30)")}),
                 lambda c, a: b.scan_for_anomalies(c.customer_id, a_int(a, "days", 30))),
            Tool("analyze_transaction_risk",
                 "Score one transaction (0-100) and return the risk level, the signals that triggered, and a recommendation.",
                 schema({"transaction_id": prop("string", "Transaction id, e.g. TXN-1001-14")}, ["transaction_id"]),
                 lambda c, a: b.assess_transaction(c.customer_id, a_str(a, "transaction_id") or "")),
            Tool("block_card",
                 "Immediately block a card. card_id accepts a card id or last 4 digits; if omitted, blocks the card "
                 "used in the most recent high-risk transaction.",
                 schema({"card_id": prop("string", "Card id (e.g. CARD-1001-C) or last 4 digits"),
                         "reason": prop("string", "Why the card is being blocked")}, ["reason"]),
                 lambda c, a: b.block_card(c.customer_id, a_str(a, "card_id"), a_str(a, "reason"))),
            Tool("raise_dispute",
                 "Raise a dispute / chargeback for an unauthorised debit. If transaction_id is omitted, disputes the "
                 "highest-risk recent transaction.",
                 schema({"transaction_id": prop("string", "Transaction id to dispute"),
                         "reason": prop("string", "Customer's reason")}, ["reason"]),
                 lambda c, a: b.raise_dispute(c.customer_id, a_str(a, "transaction_id"), a_str(a, "reason"))),
            # ---------------------------------------------------------- credit / loans
            Tool("get_credit_profile",
                 "Get the customer's credit bureau score, monthly income, existing EMIs, employment and repayment history.",
                 schema(), lambda c, a: b.get_credit_profile(c.customer_id)),
            Tool("get_existing_loans",
                 "List active loans (outstanding, rate, EMI, next due date) and loan applications with status.",
                 schema(), lambda c, a: b.get_loans(c.customer_id)),
            Tool("check_loan_eligibility",
                 "Check eligibility for a loan using bank policy (min score 650, FOIR limits). Returns the offered rate, "
                 "EMI, FOIR, maximum eligible amount, reasons and suggestions.",
                 schema({"loan_type": prop("string", "Loan product", LOAN_TYPES),
                         "amount": prop("number", "Requested amount in INR"),
                         "tenure_months": prop("integer", "Requested tenure in months (default 36)")},
                        ["loan_type", "amount"]),
                 lambda c, a: b.check_eligibility(c.customer_id, a_str(a, "loan_type"), a_dec(a, "amount"),
                                                  a_int(a, "tenure_months", 36))),
            Tool("calculate_emi",
                 "Calculate EMI, total interest and total payable. If annual_rate is omitted, uses the customer's "
                 "indicative rate for loan_type.",
                 schema({"principal": prop("number", "Loan amount in INR"),
                         "tenure_months": prop("integer", "Tenure in months"),
                         "annual_rate": prop("number", "Annual interest rate in percent (optional)"),
                         "loan_type": prop("string", "Loan product (used when annual_rate is omitted)", LOAN_TYPES)},
                        ["principal", "tenure_months"]),
                 lambda c, a: b.calculate_emi(c.customer_id, a_str(a, "loan_type"), a_dec(a, "principal"),
                                              float(a_dec(a, "annual_rate")) if a_dec(a, "annual_rate") else None,
                                              a_int(a, "tenure_months", 0))),
            Tool("apply_for_loan",
                 "Submit a loan application. Only call when the customer explicitly asks to apply. Returns application id and decision.",
                 schema({"loan_type": prop("string", "Loan product", LOAN_TYPES),
                         "amount": prop("number", "Amount in INR"),
                         "tenure_months": prop("integer", "Tenure in months"),
                         "purpose": prop("string", "Purpose of the loan")},
                        ["loan_type", "amount", "tenure_months"]),
                 lambda c, a: b.apply_for_loan(c.customer_id, a_str(a, "loan_type"), a_dec(a, "amount"),
                                               a_int(a, "tenure_months", 36), a_str(a, "purpose"))),
        ]
        self._tools = {t.name: t for t in tools}

    def subset(self, *names: str) -> list[Tool]:
        missing = [n for n in names if n not in self._tools]
        if missing:
            raise KeyError(f"Unknown tools: {missing}")
        return [self._tools[n] for n in names]
