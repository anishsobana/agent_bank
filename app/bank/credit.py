"""Simplified retail-lending rules: score cut-off, FOIR (fixed obligations to income ratio), rate card."""
from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal

from .errors import BankError
from .models import CreditProfile
from .money import inr, money

MIN_SCORE = 650


@dataclass(frozen=True)
class LoanProduct:
    base_rate: float
    max_tenure_months: int
    max_amount: Decimal


PRODUCTS: dict[str, LoanProduct] = {
    "PERSONAL": LoanProduct(11.0, 60, Decimal("2500000")),
    "HOME": LoanProduct(8.5, 300, Decimal("50000000")),
    "CAR": LoanProduct(9.0, 84, Decimal("5000000")),
    "EDUCATION": LoanProduct(9.5, 120, Decimal("4000000")),
    "BUSINESS": LoanProduct(13.0, 60, Decimal("5000000")),
}


def emi(principal: Decimal | float, annual_rate: float, months: int) -> Decimal:
    p = float(principal)
    r = annual_rate / 12 / 100
    value = p / months if r == 0 else p * r * (1 + r) ** months / ((1 + r) ** months - 1)
    return money(value)


def principal_for_emi(target_emi: Decimal | float, annual_rate: float, months: int) -> Decimal:
    e = float(target_emi)
    if e <= 0:
        return Decimal(0)
    r = annual_rate / 12 / 100
    p = e * months if r == 0 else e * ((1 + r) ** months - 1) / (r * (1 + r) ** months)
    return Decimal(math.floor(p / 1000) * 1000)  # banks quote round numbers


class CreditEngine:
    def normalise_type(self, loan_type: str | None) -> str:
        t = (loan_type or "PERSONAL").strip().upper().replace(" LOAN", "")
        if t not in PRODUCTS:
            raise BankError(f"Unsupported loan type '{loan_type}'. Supported: {sorted(PRODUCTS)}")
        return t

    def rate_for(self, loan_type: str | None, p: CreditProfile) -> float:
        rate = PRODUCTS[self.normalise_type(loan_type)].base_rate
        if p.credit_score >= 750:
            rate -= 0.5
        elif p.credit_score < 700:
            rate += 1.5
        if p.missed_payments_last_12m > 0:
            rate += 0.5
        return round(rate, 2)

    def emi_breakdown(self, principal: Decimal, annual_rate: float, months: int) -> dict:
        monthly = emi(principal, annual_rate, months)
        total = money(monthly * months)
        return {
            "principal": money(principal),
            "annual_rate_percent": annual_rate,
            "tenure_months": months,
            "monthly_emi": monthly,
            "total_interest": money(total - principal),
            "total_payable": total,
        }

    def assess(self, p: CreditProfile, loan_type: str | None, amount: Decimal, tenure_months: int) -> dict:
        kind = self.normalise_type(loan_type)
        product = PRODUCTS[kind]
        reasons: list[str] = []
        suggestions: list[str] = []

        tenure = tenure_months if tenure_months > 0 else min(36, product.max_tenure_months)
        if tenure > product.max_tenure_months:
            reasons.append(f"Requested tenure capped at the {kind} maximum of {product.max_tenure_months} months")
            tenure = product.max_tenure_months
        rate = self.rate_for(kind, p)
        foir_cap = 0.55 if p.credit_score >= 750 else 0.50
        income, existing = p.monthly_income, p.existing_monthly_emi
        new_emi = emi(amount, rate, tenure)
        current_foir = float(existing / income) if income else 1.0
        foir_with_loan = float((existing + new_emi) / income) if income else 1.0
        headroom = max(income * Decimal(str(foir_cap)) - existing, Decimal(0))
        max_at_tenure = min(principal_for_emi(headroom, rate, tenure), product.max_amount)
        max_at_max_tenure = min(principal_for_emi(headroom, rate, product.max_tenure_months), product.max_amount)

        eligible = True
        if p.credit_score < MIN_SCORE:
            eligible = False
            reasons.append(f"Credit score {p.credit_score} is below the minimum of {MIN_SCORE}")
            suggestions.append("Improve the credit score (timely repayments, lower card utilisation) and re-apply in 6 months")
        if foir_with_loan > foir_cap:
            eligible = False
            reasons.append(f"EMIs would take {foir_with_loan * 100:.0f}% of monthly income; the limit is {foir_cap * 100:.0f}%")
            if max_at_tenure > 0:
                suggestions.append(f"Reduce the amount to ₹{inr(max_at_tenure)} for {tenure} months")
            if max_at_max_tenure > max_at_tenure and tenure < product.max_tenure_months:
                suggestions.append(f"Or extend tenure to {product.max_tenure_months} months for up to ₹{inr(max_at_max_tenure)}")
            if existing > 0:
                suggestions.append("Pre-closing an existing loan would free up repayment capacity")
        if amount > product.max_amount:
            eligible = False
            reasons.append(f"Amount exceeds the {kind} product maximum of ₹{inr(product.max_amount)}")
        if p.missed_payments_last_12m > 0:
            reasons.append(f"{p.missed_payments_last_12m} missed payment(s) in the last 12 months (+0.5% rate)")
        if eligible:
            reasons.append("Credit score and repayment capacity are within policy")

        return {
            "loan_type": kind,
            "requested_amount": amount,
            "tenure_months": tenure,
            "eligible": eligible,
            "credit_score": p.credit_score,
            "offered_annual_rate_percent": rate,
            "emi_for_requested_amount": new_emi,
            "monthly_income": income,
            "existing_monthly_emi": existing,
            "current_foir_percent": round(current_foir * 100, 1),
            "foir_with_new_loan_percent": round(foir_with_loan * 100, 1),
            "foir_limit_percent": round(foir_cap * 100),
            "max_eligible_amount_at_this_tenure": max_at_tenure,
            "max_eligible_amount_at_max_tenure": max_at_max_tenure,
            "reasons": reasons,
            "suggestions": suggestions,
            "disclaimer": "Indicative only; final sanction subject to document verification.",
        }
