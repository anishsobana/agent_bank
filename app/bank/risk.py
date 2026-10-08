"""Deterministic, explainable rule-based risk scoring (stands in for a real fraud model).

The LLM never computes risk itself: it calls this engine and explains the signals it returns.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from .models import RiskAssessment, Transaction
from .money import inr

HIGH = 60
MEDIUM = 30


def level(score: int) -> str:
    return "HIGH" if score >= HIGH else "MEDIUM" if score >= MEDIUM else "LOW"


def _near(a: datetime, b: datetime, minutes: int) -> bool:
    return abs((a - b).total_seconds()) <= minutes * 60


class RiskEngine:
    def score_transaction(self, t: Transaction, full_history: list[Transaction]) -> RiskAssessment:
        if not t.is_debit:
            return RiskAssessment(t.id, 0, "LOW", ["Incoming credit"], "No action needed.")
        # only settled transactions form the behavioural baseline (held / pending transfers excluded)
        history = [o for o in full_history if o.status == "POSTED"]
        signals: list[str] = []
        score = 0

        other_debits = [o for o in history if o.is_debit and o.id != t.id]
        avg = sum(float(o.amount) for o in other_debits) / len(other_debits) if other_debits else 0.0
        amount = float(t.amount)
        if avg > 0 and amount > 5 * avg:
            score += 35
            signals.append(f"Amount is {amount / avg:.0f}x the customer's average debit (avg ₹{inr(avg)})")
        if t.country and t.country.upper() != "IN":
            score += 25
            signals.append(f"International transaction ({t.location}, {t.country})")
        if t.timestamp.hour < 5:
            score += 15
            signals.append(f"Odd-hour transaction at {t.timestamp:%H:%M}")
        seen_before = any(o.timestamp < t.timestamp and o.id != t.id and o.merchant
                          and o.merchant.lower() == t.merchant.lower() and not _near(o.timestamp, t.timestamp, 60)
                          for o in history)
        if not seen_before:
            score += 10
            signals.append(f"First transaction with merchant '{t.merchant}'")
        if amount <= 10:
            score += 10
            signals.append("Micro-value charge (≤ ₹10) - a common card-testing probe")
        if t.card_id:
            burst = sum(1 for o in history if o.id != t.id and o.card_id == t.card_id and _near(o.timestamp, t.timestamp, 30))
            if burst >= 1:
                score += 20
                signals.append(f"{burst} other charge(s) on the same card within 30 minutes (velocity)")
            if t.channel == "ONLINE":
                score += 5
                signals.append("Card-not-present (online) payment")
        score = min(score, 100)
        if score >= HIGH:
            rec = "Likely fraudulent. Confirm with the customer; if not recognised, block the card and raise a dispute."
        elif score >= MEDIUM:
            rec = "Unusual. Verify with the customer before taking action."
        else:
            rec = "Consistent with normal behaviour."
        return RiskAssessment(t.id, score, level(score), signals, rec)

    def score_transfer(self, payee: str, amount: Decimal, balance: Decimal, registered_payee: bool,
                       recent_high_risk_activity: bool, when: datetime) -> RiskAssessment:
        signals: list[str] = []
        score = 0
        if not registered_payee:
            score += 35
            signals.append(f"Payee '{payee}' is not a registered beneficiary")
        if balance > 0 and amount / balance > Decimal("0.5"):
            score += 20
            signals.append("Transfer exceeds 50% of the available balance")
        if amount >= Decimal("100000"):
            score += 20
            signals.append("High-value transfer (≥ ₹1,00,000)")
        if when.hour < 5:
            score += 15
            signals.append("Odd-hour transfer request")
        if recent_high_risk_activity:
            score += 25
            signals.append("High-risk card activity detected on this account in the last 48 hours")
        score = min(score, 100)
        if not signals:
            signals.append("No risk signals - registered payee, normal amount")
        rec = ("Hold the transfer for manual security review." if score >= HIGH
               else "Allow, but confirm the payee details with the customer." if score >= MEDIUM else "Allow.")
        return RiskAssessment("TRANSFER", score, level(score), signals, rec)
