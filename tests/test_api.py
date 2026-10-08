import pytest
from fastapi.testclient import TestClient

from app.agents.orchestrator import Orchestrator
from app.llm.mock_client import MockLlmClient
from app.main import create_app


@pytest.fixture
def client():
    return TestClient(create_app(Orchestrator(MockLlmClient())))


def chat(client, message, customer="CUST1001", session="t"):
    res = client.post("/api/chat", json={"session_id": session, "customer_id": customer, "message": message})
    assert res.status_code == 200, res.text
    return res.json()


def tool_calls(body):
    return [e["title"] for e in body["trace"] if e["type"] == "TOOL_CALL"]


def test_balance_routes_to_customer_service(client):
    body = chat(client, "What's my account balance?")
    assert body["agents"] == ["CUSTOMER_SERVICE"]
    assert tool_calls(body) == ["get_account_balances"]
    assert "ACC10011001" in body["reply"]


def test_fraud_question_routes_to_fraud_agent(client):
    body = chat(client, "I see a charge I don't recognise. Is my account safe?")
    assert body["agents"] == ["FRAUD_RISK"]
    assert "TXN-1001-14" in body["reply"] and "HIGH" in body["reply"]


def test_transfer_confirmation_uses_memory_and_risky_transfer_is_held(client):
    assert "PREVIEW" in chat(client, "Transfer ₹1,20,000 to ACC99887766", session="x")["reply"]
    body = chat(client, "yes, confirm", session="x")
    assert body["agents"] == ["CUSTOMER_SERVICE"]
    assert "ON_HOLD" in body["reply"]


def test_cross_domain_request_uses_two_agents_and_synthesis(client):
    body = chat(client, "There's a suspicious debit on my card, and can I still get a ₹6 lakh car loan?")
    assert body["agents"] == ["FRAUD_RISK", "CREDIT_LOAN"]
    assert any(e["type"] == "SYNTHESIS" for e in body["trace"])


def test_agent_cannot_use_tools_outside_its_allow_list(client):
    agents = client.get("/api/meta").json()["agents"]
    assert "transfer_funds" in agents["CUSTOMER_SERVICE"]["tools"]
    assert "transfer_funds" not in agents["FRAUD_RISK"]["tools"]
    assert "block_card" not in agents["CUSTOMER_SERVICE"]["tools"]


def test_greeting_answered_directly(client):
    assert chat(client, "hello", customer="CUST1002")["agents"] == []


def test_unknown_customer_and_invalid_input(client):
    assert client.post("/api/chat", json={"customer_id": "NOPE", "message": "hi"}).status_code == 400
    assert client.post("/api/chat", json={"customer_id": "CUST1001", "message": ""}).status_code == 422


def test_bank_rest_apis(client):
    assert client.get("/api/bank/customers/CUST1001/risk/transactions/TXN-1001-14").json()["level"] == "HIGH"
    r = client.get("/api/bank/customers/CUST1002/loans/eligibility", params={"amount": 1000000})
    assert r.json()["eligible"] is False
    assert client.get("/").status_code == 200
