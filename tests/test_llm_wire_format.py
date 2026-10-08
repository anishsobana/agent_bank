"""Validates the Anthropic and OpenAI-compatible wire formats over a full tool round trip, without a network."""
import json

from app.agents.orchestrator import Orchestrator
from app.config import LlmSettings
from app.llm import anthropic_client, openai_client
from app.llm.anthropic_client import AnthropicClient
from app.llm.openai_client import OpenAICompatibleClient


def test_anthropic_tool_round_trip(monkeypatch):
    requests = []

    def fake_post(url, headers, body, timeout):
        requests.append(body)
        assert headers["x-api-key"] == "k" and url.endswith("/v1/messages")
        last = body["messages"][-1]
        if "ROUTING_TASK" in body["system"]:  # router answers with JSON inside markdown fences
            return {"content": [{"type": "text", "text": '```json\n{"agents":["fraud_risk"],"tasks":{}}\n```'}]}
        if isinstance(last["content"], list) and last["content"][0]["type"] == "tool_result":
            return {"content": [{"type": "text", "text": "Found a HIGH risk charge."}]}
        return {"content": [{"type": "text", "text": "Scanning."},
                            {"type": "tool_use", "id": "tu_1", "name": "scan_account_for_anomalies", "input": {"days": 7}}]}

    monkeypatch.setattr(anthropic_client, "post_json", fake_post)
    o = Orchestrator(AnthropicClient(LlmSettings(provider="anthropic", api_key="k")))
    r = o.handle("s", "CUST1001", "Anything suspicious?")
    assert r.reply == "Found a HIGH risk charge."
    msgs = requests[-1]["messages"]
    assert msgs[-2]["content"][1] == {"type": "tool_use", "id": "tu_1", "name": "scan_account_for_anomalies",
                                      "input": {"days": 7}}
    result = msgs[-1]["content"][0]
    assert result["tool_use_id"] == "tu_1" and "TXN-1001-14" in result["content"]
    assert requests[-1]["tools"][0]["input_schema"]["type"] == "object"


def test_openai_compatible_tool_round_trip_with_string_amount(monkeypatch):
    requests = []

    def fake_post(url, headers, body, timeout):
        requests.append(body)
        assert url == "http://localhost:11434/v1/chat/completions" and "Authorization" not in headers
        msgs = body["messages"]
        if "ROUTING_TASK" in msgs[0]["content"]:
            return {"choices": [{"message": {"content": '{"agents":["CREDIT_LOAN"]}'}}]}
        if msgs[-1]["role"] == "tool":
            return {"choices": [{"message": {"content": "You are eligible."}}]}
        args = json.dumps({"loan_type": "PERSONAL", "amount": "3,00,000"})  # models often send strings
        return {"choices": [{"message": {"content": None, "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "check_loan_eligibility", "arguments": args}}]}}]}

    monkeypatch.setattr(openai_client, "post_json", fake_post)
    client = OpenAICompatibleClient(LlmSettings(provider="openai", base_url="http://localhost:11434/v1/"))
    r = Orchestrator(client).handle("s", "CUST1001", "Can I get a 3 lakh personal loan?")
    assert r.reply == "You are eligible."
    tool_msg = requests[-1]["messages"][-1]
    assert tool_msg["tool_call_id"] == "c1"
    assert json.loads(tool_msg["content"])["eligible"] is True
    assert requests[-1]["messages"][-2]["tool_calls"][0]["function"]["name"] == "check_loan_eligibility"
