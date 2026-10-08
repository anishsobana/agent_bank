# Demo video script (about 7–8 minutes)

**Setup before recording:** start with a real model (for example `LLM_PROVIDER=anthropic`), open
http://localhost:8000 at 1440px width, and keep your editor open on `app/agents/` in a second window. Restart the app first
so the seed data is fresh.

---

### 0:00 – 0:45 Introduction

> "This is AgentBank, an MVP showing several AI agents working together in a simulated bank. A Supervisor agent
> understands each message and routes it to one of three specialists: Customer Service, Fraud & Risk, and Credit &
> Loans. The specialists don't make up facts. They call simulated banking APIs as tools. On the right, the activity
> panel shows exactly which agent ran and which APIs it called."

Point at: the customer picker, the use-case list, the model name under the header, and the colour legend.

### 0:45 – 1:45 Use case 1: balance and spending (Customer Service)

1. Click **Balance enquiry**. Point at the routing step and the `get_account_balances()` call. Expand it to show the raw JSON.
2. Click **Spending insights**.
   > "The numbers come from the API. The model explains them, for example that rent and one big electronics purchase dominate this month."

### 1:45 – 3:15 Use case 2: fraud investigation and action (Fraud & Risk)

1. Click **Fraud scan**.
   > "The fraud agent called the risk engine. It found a classic card-testing pattern: a ₹1 charge, a ₹10 charge, then ₹78,999 at a Dubai merchant at 3 AM. The score is 100/100, and the signals explain why."
2. Click **Block card + dispute**. Show both `block_card` and `raise_dispute` in the timeline, plus the block reference, dispute ID and timelines in the answer.
   > "These are write actions, and only the Fraud agent is allowed to perform them."

### 3:15 – 4:30 Use case 3: transfers with a human in the loop and a real-time risk check

1. Click **Transfer with confirmation** (₹5,000 to Amma). Show the preview and the request to confirm.
2. Type **"yes, go ahead"**.
   > "The Supervisor used the conversation history to send this follow-up back to Customer Service, and the transfer completed."
3. Click **Risky transfer gets held** (₹1,20,000 to an unknown account), then type **"confirm"**.
   > "New payee, more than half the balance, high value, and a fraud event in the last 48 hours. The risk engine scores it HIGH, so the transfer is put ON HOLD instead of executed."

### 4:30 – 5:30 Use case 4: loans (Credit & Loans)

1. Switch the customer to **Arjun Mehta** and click **Declined with alternatives**.
   > "Arjun already pays ₹41,000 a month in EMIs. With this loan his EMIs would be 62% of his income, above the 50% limit. The agent doesn't just say no: it offers about ₹5.6 lakh at this tenure, or more over 60 months."
2. Click **Application status** to show his business loan under review.

### 5:30 – 6:30 Use case 5: one question, two agents

Switch back to **Priya** and click **Two agents, one answer**.
> "This question spans two domains. The Supervisor planned Fraud & Risk first, then Credit & Loans. The loan agent received the fraud findings as context. Finally, the Supervisor merged both into one reply, with security first."

Point at the timeline: route, two agents, their tool calls, the synthesis step.

### 6:30 – 7:45 Architecture in the code (editor)

Show briefly:
- `agents/supervisor.py` + `prompts.SUPERVISOR`: the JSON routing contract and the keyword fallback.
- `agents/specialist.py`, `run()`: the tool-calling loop (about 25 lines, the same class for all agents).
- `agents/orchestrator.py`, `build_agents()`: each agent's least-privilege tool list.
- `tools/toolkit.py`: the customer id comes from the session (`ToolContext`), never from the model.
- `bank/risk.py` / `bank/credit.py`: deterministic, explainable numbers.
- `llm/`: one interface and three clients; switch models with an environment variable.
- Optionally run `pytest -q` (23 tests, under a second) and show the Swagger UI at `/docs`.

> "Design principle: the LLM decides *what* to do and *explains* results, while deterministic code *computes*
> anything that matters, such as scores, EMIs and eligibility. That keeps the system auditable, which a bank needs."

### 7:45 – 8:15 Close

> "In production, the in-memory store becomes the core banking APIs, the rules become fraud models fed by a
> real-time transaction stream, and the trace becomes an audit log. Thanks for watching."

---

**Tips:** Do one full dry run first, because LLM wording varies. Keep the activity panel visible throughout, since
it's the clearest evidence of the multi-agent behaviour. If a step answers oddly, click **New conversation** and retry.
