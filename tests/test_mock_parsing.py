from decimal import Decimal

from app.agents.router import keyword_route
from app.agents.types import AgentType
from app.llm.mock_client import parse_amount, parse_tenure_months


def test_parses_indian_amount_formats():
    assert parse_amount("send ₹1,20,000 to Karthik") == Decimal("120000")
    assert parse_amount("a 5 lakh personal loan for 3 years") == Decimal("500000")
    assert parse_amount("transfer 5000 to Amma") == Decimal("5000")
    assert parse_amount("EMI for 25 lakh at 8.5% for 20 years") == Decimal("2500000")
    assert parse_amount("show 30 days") is None


def test_parses_tenure():
    assert parse_tenure_months("for 3 years") == 36
    assert parse_tenure_months("over 18 months") == 18


def test_keyword_router():
    assert keyword_route("what's my balance?") == [AgentType.CUSTOMER_SERVICE]
    assert keyword_route("is my account safe?") == [AgentType.FRAUD_RISK]
    assert keyword_route("suspicious debit, and can I get a car loan?") == [AgentType.FRAUD_RISK, AgentType.CREDIT_LOAN]
    assert keyword_route("yes, go ahead", [AgentType.CUSTOMER_SERVICE]) == [AgentType.CUSTOMER_SERVICE]
    assert keyword_route("hello") == []
