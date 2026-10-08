from decimal import Decimal

import pytest

from app.bank.credit import CreditEngine, emi
from app.bank.errors import BankError
from app.bank.models import CreditProfile
from app.bank.money import inr
from app.bank.service import CoreBankingService


@pytest.fixture
def bank():
    return CoreBankingService()


def test_emi_matches_standard_formula():
    # 1,00,000 at 12% p.a. for 12 months = 8,884.88
    assert emi(Decimal("100000"), 12.0, 12) == Decimal("8884.88")


def test_card_testing_pattern_is_high_risk(bank):
    risk = bank.assess_transaction("CUST1001", "TXN-1001-14")
    assert risk.level == "HIGH"
    assert any("International" in s for s in risk.signals)
    assert any("velocity" in s for s in risk.signals)


def test_regular_grocery_payment_is_low_risk(bank):
    assert bank.assess_transaction("CUST1001", "TXN-1001-08").level == "LOW"


def test_anomaly_scan_finds_the_three_fraud_charges(bank):
    ids = [m["transaction"].id for m in bank.scan_for_anomalies("CUST1001") if m["risk"].level == "HIGH"]
    assert set(ids) == {"TXN-1001-12", "TXN-1001-13", "TXN-1001-14"}


def test_high_foir_customer_is_declined_with_alternatives(bank):
    r = bank.check_eligibility("CUST1002", "PERSONAL", Decimal("1000000"), 36)
    assert r["eligible"] is False
    assert r["max_eligible_amount_at_this_tenure"] == Decimal("563000")
    assert any("5,63,000" in s for s in r["suggestions"])


def test_low_credit_score_is_rejected():
    p = CreditProfile("X", 610, "CIBIL", Decimal("80000"), Decimal("0"), "SALARIED", 3, 0)
    assert CreditEngine().assess(p, "PERSONAL", Decimal("100000"), 24)["eligible"] is False


def test_transfer_needs_sufficient_funds(bank):
    with pytest.raises(BankError, match="Insufficient funds"):
        bank.transfer("CUST1003", None, "ACC12345678", Decimal("50000"), None, confirmed=False)


def test_preview_does_not_move_money_and_confirm_does(bank):
    before = bank.primary_account("CUST1001").balance
    assert bank.transfer("CUST1001", "Amma", None, Decimal("5000"), None, False)["status"] == "PREVIEW"
    assert bank.primary_account("CUST1001").balance == before
    assert bank.transfer("CUST1001", "Amma", None, Decimal("5000"), None, True)["status"] == "COMPLETED"
    assert bank.primary_account("CUST1001").balance == before - 5000


def test_risky_transfer_is_held_and_not_debited(bank):
    before = bank.primary_account("CUST1001").balance
    r = bank.transfer("CUST1001", None, "ACC99887766", Decimal("120000"), None, True)
    assert r["status"] == "ON_HOLD"
    assert bank.primary_account("CUST1001").balance == before


def test_indian_number_formatting():
    assert inr(1234567) == "12,34,567"
    assert inr(999) == "999"
    assert inr(100000) == "1,00,000"
