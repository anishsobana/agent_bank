"""Simulated banking APIs.

Every method takes the authenticated customer_id first, so an agent can never reach another customer's
data: the tool layer injects this id from the session, never from the model.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal

from .credit import CreditEngine
from .errors import BankError
from .models import (Account, Beneficiary, Card, CreditProfile, Customer, Dispute, LoanApplication,
                     RiskAssessment, Transaction)
from .money import inr
from .risk import HIGH, MEDIUM, RiskEngine
from .store import BankDataStore

DAILY_TRANSFER_LIMIT = Decimal("200000")


class CoreBankingService:
    def __init__(self, store: BankDataStore | None = None, risk: RiskEngine | None = None,
                 credit: CreditEngine | None = None) -> None:
        self.store = store or BankDataStore()
        self.risk = risk or RiskEngine()
        self.credit = credit or CreditEngine()

    # ------------------------------------------------------------------ customer & accounts
    def list_customers(self) -> list[Customer]:
        return list(self.store.customers.values())

    def get_customer(self, customer_id: str) -> Customer:
        c = self.store.customers.get(customer_id)
        if c is None:
            raise BankError(f"Unknown customer {customer_id}")
        return c

    def get_accounts(self, customer_id: str) -> list[Account]:
        self.get_customer(customer_id)
        return sorted((a for a in self.store.accounts.values() if a.customer_id == customer_id),
                      key=lambda a: a.account_number)

    def primary_account(self, customer_id: str) -> Account:
        for a in self.get_accounts(customer_id):
            if a.type != "FIXED_DEPOSIT":
                return a
        raise BankError("No operative account")

    def all_transactions(self, customer_id: str) -> list[Transaction]:
        txns = [t for a in self.get_accounts(customer_id) for t in self.store.transactions.get(a.account_number, [])]
        return sorted(txns, key=lambda t: t.timestamp, reverse=True)

    def recent_transactions(self, customer_id: str, limit: int = 10, category: str | None = None,
                            days: int = 30) -> list[Transaction]:
        since = datetime.now() - timedelta(days=days if days > 0 else 30)
        limit = 10 if limit <= 0 else min(limit, 50)
        out = [t for t in self.all_transactions(customer_id)
               if t.timestamp > since and (not category or t.category.lower() == category.lower())]
        return out[:limit]

    def get_transaction(self, customer_id: str, transaction_id: str) -> Transaction:
        tid = (transaction_id or "").strip().upper()
        for t in self.all_transactions(customer_id):
            if t.id.upper() == tid:
                return t
        raise BankError(f"Transaction {transaction_id} not found for this customer")

    def spending_summary(self, customer_id: str, days: int = 30) -> dict:
        window = days if days > 0 else 30
        txns = self.recent_transactions(customer_id, 50, None, window)
        by_cat: dict[str, Decimal] = defaultdict(Decimal)
        for t in txns:
            if t.is_debit:
                by_cat[t.category] += t.amount
        spent = sum(by_cat.values(), Decimal(0))
        received = sum((t.amount for t in txns if not t.is_debit), Decimal(0))
        categories = [{"category": k, "amount": v,
                       "share_percent": round(float(v / spent * 100), 1) if spent else 0}
                      for k, v in sorted(by_cat.items(), key=lambda kv: kv[1], reverse=True)]
        return {"period_days": window, "total_spent": spent, "total_received": received,
                "net": received - spent, "by_category": categories}

    def get_cards(self, customer_id: str) -> list[Card]:
        self.get_customer(customer_id)
        return sorted((c for c in self.store.cards.values() if c.customer_id == customer_id), key=lambda c: c.card_id)

    def get_beneficiaries(self, customer_id: str) -> list[Beneficiary]:
        self.get_customer(customer_id)
        return list(self.store.beneficiaries.get(customer_id, []))

    # ------------------------------------------------------------------ transfers (with risk check)
    def transfer(self, customer_id: str, beneficiary_name: str | None, to_account: str | None,
                 amount: Decimal | None, note: str | None, confirmed: bool) -> dict:
        if amount is None or amount <= 0:
            raise BankError("Transfer amount must be positive")
        src = self.primary_account(customer_id)
        payee = self._resolve_payee(customer_id, beneficiary_name, to_account)
        payee_account = payee.account_number if payee else to_account
        if not payee_account:
            names = [b.name for b in self.get_beneficiaries(customer_id)]
            raise BankError(f"Payee not found. Registered beneficiaries: {names}. "
                            "Provide a beneficiary name or account number.")
        payee_label = payee.name if payee else payee_account
        if amount > src.balance:
            raise BankError(f"Insufficient funds: available balance is ₹{inr(src.balance)}")
        if amount > DAILY_TRANSFER_LIMIT:
            raise BankError(f"Amount exceeds the daily transfer limit of ₹{inr(DAILY_TRANSFER_LIMIT)}")

        assessment = self.risk.score_transfer(payee_label, amount, src.balance, payee is not None,
                                              self._recent_high_risk_activity(customer_id), datetime.now())
        out: dict = {"from_account": src.account_number, "payee": payee_label, "payee_account": payee_account,
                     "registered_beneficiary": payee is not None, "amount": amount, "fee": Decimal(0),
                     "risk_check": assessment}
        if not confirmed:
            out["status"] = "PREVIEW"
            out["balance_after_transfer"] = src.balance - amount
            out["next_step"] = ("Warn the customer this transfer will be held for security review if they proceed; ask them to confirm."
                                if assessment.level == "HIGH"
                                else "Show this preview and ask the customer to explicitly confirm the transfer.")
            return out

        ref = self.store.next_id("TRF")
        desc = f"Transfer to {payee_label}" + (f" - {note}" if note else "")
        with self.store.lock:
            current = self.store.accounts[src.account_number]
            if assessment.level == "HIGH":
                self.store.transactions[src.account_number].append(Transaction(
                    ref, src.account_number, datetime.now(), desc, payee_label, "TRANSFER", amount, "DEBIT",
                    "IMPS", "Online", "IN", None, "ON_HOLD"))
                out.update(status="ON_HOLD", reference=ref,
                           message="Transfer held for manual security review; funds have not left the account. "
                                   "The customer will be contacted within 2 working hours.")
                return out
            if amount > current.balance:
                raise BankError("Insufficient funds")
            self.store.accounts[src.account_number] = current.with_balance(current.balance - amount)
            self.store.transactions[src.account_number].append(Transaction(
                ref, src.account_number, datetime.now(), desc, payee_label, "TRANSFER", amount, "DEBIT",
                "IMPS", "Online", "IN", None, "POSTED"))
        out.update(status="COMPLETED", reference=ref, new_balance=self.store.accounts[src.account_number].balance)
        return out

    def _resolve_payee(self, customer_id: str, name: str | None, account: str | None) -> Beneficiary | None:
        bens = self.get_beneficiaries(customer_id)
        if account:
            for b in bens:
                if b.account_number.upper() == account.strip().upper():
                    return b
        if name:
            n = name.strip().lower()
            for b in bens:
                if n in b.name.lower() or b.name.lower().split()[0] in n or b.relationship.lower() == n:
                    return b
        return None

    # ------------------------------------------------------------------ fraud & risk
    def _score(self, t: Transaction) -> RiskAssessment:
        return self.risk.score_transaction(t, self.store.transactions.get(t.account_number, []))

    def assess_transaction(self, customer_id: str, transaction_id: str) -> RiskAssessment:
        return self._score(self.get_transaction(customer_id, transaction_id))

    def scan_for_anomalies(self, customer_id: str, days: int = 30) -> list[dict]:
        flagged = []
        for t in self.recent_transactions(customer_id, 50, None, days if days > 0 else 30):
            if t.status != "POSTED":  # the customer's own held transfers are not anomalies
                continue
            a = self._score(t)
            if a.score >= MEDIUM:
                flagged.append({"transaction": t, "risk": a})
        return sorted(flagged, key=lambda m: -m["risk"].score)

    def _recent_high_risk_activity(self, customer_id: str) -> bool:
        since = datetime.now() - timedelta(hours=48)
        return any(t.timestamp > since and t.card_id and self._score(t).score >= HIGH
                   for t in self.all_transactions(customer_id))

    def block_card(self, customer_id: str, card_ref: str | None, reason: str | None) -> dict:
        card = self._resolve_card(customer_id, card_ref)
        if card.status == "BLOCKED":
            return {"card_id": card.card_id, "status": "BLOCKED", "message": "Card was already blocked."}
        self.store.cards[card.card_id] = card.with_status("BLOCKED")
        return {"card_id": card.card_id, "card": f"{card.network} {card.type} ending {card.last4}",
                "status": "BLOCKED", "reason": reason or "Customer request",
                "block_reference": self.store.next_id("BLK"),
                "replacement_card": "A replacement card will be dispatched to the registered address within 5-7 working days."}

    def _resolve_card(self, customer_id: str, card_ref: str | None) -> Card:
        """Accepts a card id, last-4 digits, or nothing (= card used in the most recent high-risk transaction)."""
        cards = self.get_cards(customer_id)
        listing = [f"{c.card_id} ({c.type} ending {c.last4})" for c in cards]
        if card_ref and card_ref.strip():
            ref = card_ref.strip()
            for c in cards:
                if c.card_id.upper() == ref.upper() or ref.endswith(c.last4):
                    return c
            raise BankError(f"Card '{ref}' not found. Customer cards: {listing}")
        for m in self.scan_for_anomalies(customer_id, 7):
            t: Transaction = m["transaction"]
            if t.card_id:
                for c in cards:
                    if c.card_id == t.card_id:
                        return c
        raise BankError(f"Specify which card to block: {listing}")

    def raise_dispute(self, customer_id: str, transaction_id: str | None, reason: str | None) -> Dispute:
        if transaction_id and transaction_id.strip():
            t = self.get_transaction(customer_id, transaction_id)
        else:
            flagged = self.scan_for_anomalies(customer_id, 7)
            if not flagged:
                raise BankError("Specify the transaction id to dispute")
            t = flagged[0]["transaction"]
        if not t.is_debit:
            raise BankError("Only debit transactions can be disputed")
        d = Dispute(self.store.next_id("DSP"), customer_id, t.id, t.amount, reason or "Unauthorised transaction",
                    "OPEN", datetime.now(),
                    "Provisional credit within 10 working days; final resolution within 45 days (RBI timelines).")
        self.store.disputes.setdefault(customer_id, []).append(d)
        return d

    # ------------------------------------------------------------------ credit & loans
    def get_credit_profile(self, customer_id: str) -> CreditProfile:
        self.get_customer(customer_id)
        return self.store.credit_profiles[customer_id]

    def get_loans(self, customer_id: str) -> dict:
        self.get_customer(customer_id)
        return {"active_loans": self.store.loans.get(customer_id, []),
                "applications": self.store.loan_applications.get(customer_id, [])}

    def check_eligibility(self, customer_id: str, loan_type: str | None, amount: Decimal | None, tenure_months: int) -> dict:
        if amount is None or amount <= 0:
            raise BankError("Loan amount must be positive")
        return self.credit.assess(self.get_credit_profile(customer_id), loan_type, amount, tenure_months)

    def calculate_emi(self, customer_id: str, loan_type: str | None, principal: Decimal | None,
                      annual_rate: float | None, tenure_months: int) -> dict:
        if principal is None or principal <= 0:
            raise BankError("Principal must be positive")
        if tenure_months <= 0:
            raise BankError("Tenure (months) must be positive")
        explicit = annual_rate is not None and annual_rate > 0
        rate = annual_rate if explicit else self.credit.rate_for(loan_type, self.get_credit_profile(customer_id))
        out = self.credit.emi_breakdown(principal, rate, tenure_months)
        if not explicit:
            out["rate_source"] = f"Customer's indicative rate for {self.credit.normalise_type(loan_type)}"
        return out

    def apply_for_loan(self, customer_id: str, loan_type: str | None, amount: Decimal | None,
                       tenure_months: int, purpose: str | None) -> LoanApplication:
        a = self.check_eligibility(customer_id, loan_type, amount, tenure_months)
        status = "REJECTED" if not a["eligible"] else "PRE_APPROVED" if a["credit_score"] >= 750 else "UNDER_REVIEW"
        notes = list(a["reasons"])
        if purpose:
            notes.append(f"Purpose: {purpose}")
        if status == "PRE_APPROVED":
            notes.append("Disbursal after e-sign of the loan agreement (typically 24 hours)")
        if status == "UNDER_REVIEW":
            notes.append("An underwriter will review income documents within 2 working days")
        app_ = LoanApplication(self.store.next_id("LAPP"), customer_id, a["loan_type"], amount, a["tenure_months"],
                               a["offered_annual_rate_percent"], a["emi_for_requested_amount"], status, notes,
                               datetime.now())
        self.store.loan_applications.setdefault(customer_id, []).append(app_)
        return app_
