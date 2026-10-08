# AgentBank: multi-agent banking assistant (MVP)

AgentBank is a working MVP of a **simulated real-time banking assistant** built from cooperating AI agents.
A **Supervisor agent** reads each customer message and routes it to one or more **specialist agents**:

- **Customer Service** handles balances, transactions, spending insights and fund transfers.
- **Fraud & Risk** handles suspicious activity, risk scoring, card blocking and disputes.
- **Credit & Loans** handles credit score, loan eligibility, EMI calculation and applications.

The specialists act through **simulated core-banking APIs**, exposed to them as LLM tools. A web UI shows the
conversation next to a live **agent activity timeline**: which agent handled the request, why, and every API call
with its arguments and response.

Tech stack: **Python 3.10+, FastAPI**, `httpx` for LLM calls (no vendor SDK), vanilla HTML/JS UI, `pytest`.

```
Customer ─▶ Supervisor (LLM router) ─┬─▶ Customer Service agent ─▶ accounts / transactions / transfer APIs
                                     ├─▶ Fraud & Risk agent ──────▶ risk engine / cards / disputes APIs
                                     └─▶ Credit & Loans agent ────▶ credit bureau / eligibility / EMI APIs
                         ◀── Supervisor merges findings when more than one agent ran
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the design and [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) for the video walkthrough.

---

## Quick start

### 1. Install

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Run in offline mode (no API key)

```bash
uvicorn app.main:app --reload
```

Open **http://localhost:8000**. Interactive API docs (Swagger) are at **http://localhost:8000/docs**.

Offline mode uses a deterministic mock model. Routing, agent hand-offs, tool calls and the activity timeline all
work, but answers show raw API results instead of conversational text. Use it to verify the setup, then connect
a real model.

### 3. Run with a real LLM

The provider is chosen with environment variables, or with a `.env` file (copy `.env.example`). Any model with
tool/function calling works.

| Provider | Settings |
|---|---|
| **Claude (Anthropic)** | `LLM_PROVIDER=anthropic` `LLM_API_KEY=sk-ant-...` (optional `LLM_MODEL`, default `claude-sonnet-5-5`) |
| **Google Gemini** (free tier) | `LLM_PROVIDER=openai` `LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai` `LLM_API_KEY=...` `LLM_MODEL=gemini-2.5-flash` |
| **Groq** (free tier) | `LLM_PROVIDER=openai` `LLM_BASE_URL=https://api.groq.com/openai/v1` `LLM_API_KEY=gsk_...` `LLM_MODEL=llama-3.3-70b-versatile` |
| **Ollama** (local, no key) | `LLM_PROVIDER=openai` `LLM_BASE_URL=http://localhost:11434/v1` `LLM_MODEL=qwen2.5:7b` |
| **OpenAI** | `LLM_PROVIDER=openai` `LLM_API_KEY=sk-...` (optional `LLM_MODEL`, default `gpt-4o-mini`) |

Model names change often, so check your provider's current list. Use a model that supports tool calling.

The simplest way is a `.env` file in the project root:
```
LLM_PROVIDER=anthropic
LLM_API_KEY=sk-ant-xxxx
```
Then run `uvicorn app.main:app --reload`. The model in use is shown under the chat header and in the startup log.

### 4. Tests and Docker

```bash
pytest -q                                  # 23 tests, no network or API key needed
docker build -t agentbank . && docker run -p 8000:8000 --env-file .env agentbank
```

---

## Banking use cases

Choose a demo customer in the left panel. Each one is seeded with data that exercises particular scenarios. The
sample prompts appear in the UI.

| # | Use case | Agent(s) | Try (customer) | What it shows |
|---|---|---|---|---|
| 1 | Balance & transaction enquiry | Customer Service | "What's my account balance?" (Priya) | Basic routing + read APIs |
| 2 | Spending insights | Customer Service | "Where did I spend the most this month?" (Priya) | Aggregation API, LLM explanation |
| 3 | Fraud investigation | Fraud & Risk | "I see a charge I don't recognise. Is my account safe?" (Priya) | Rule-based risk engine detects a card-testing pattern (₹1 and ₹10 probes, then ₹78,999 in Dubai at 3 AM) |
| 4 | Block card & raise dispute | Fraud & Risk | "I didn't make the Dubai purchase. Block my card and raise a dispute." (Priya) | Write actions, multi-tool chaining, dispute ID / timelines |
| 5 | Fund transfer with confirmation | Customer Service (+ risk engine) | "Send ₹5,000 to Amma", then "yes, confirm" (Priya) | Human-in-the-loop two-step transfer, conversation memory |
| 6 | Risky transfer held | Customer Service (+ risk engine) | "Transfer ₹1,20,000 to ACC99887766", then "confirm" (Priya) | New payee + high value + recent fraud = transfer **held for review** |
| 7 | Loan eligibility | Credit & Loans | "Can I get a ₹10 lakh personal loan for 3 years?" (Arjun) | FOIR-based decline with concrete alternatives |
| 8 | EMI / loan status / credit score | Credit & Loans | "Calculate EMI for a ₹2 lakh education loan for 2 years" (Kavya) | Calculators, application tracking |
| 9 | Cross-domain request | Fraud & Risk then Credit & Loans | "There's a suspicious debit on my card, and can I still get a ₹6 lakh car loan?" (Priya) | Supervisor plans two agents; the second sees the first's findings; Supervisor merges one answer |

Demo customers:
- **Priya Raman** (CUST1001): healthy finances, a fraud pattern on her credit card, two registered beneficiaries.
- **Arjun Mehta** (CUST1002): self-employed, high existing EMIs (FOIR 34%), a business loan under review.
- **Kavya Iyer** (CUST1003): early-career, low balance, a small international (USD) payment.

Seed data is in-memory and timestamps are relative to startup, so the demo always looks recent. Restart the server
to reset everything.

---

## API reference

Full interactive docs: `/docs`.

### Chat (used by the UI)
| Method | Path | Body / notes |
|---|---|---|
| POST | `/api/chat` | `{"session_id":"s1","customer_id":"CUST1001","message":"What's my balance?"}` returns `reply`, `agents`, `trace[]`, `elapsed_ms`, `model` |
| POST | `/api/chat/reset` | `{"session_id":"s1","customer_id":"CUST1001"}` |
| GET | `/api/customers` | Demo personas with accounts |
| GET | `/api/meta` | Active model and each agent's allowed tools |

### Simulated banking APIs (also what the agents' tools call)
| Method | Path |
|---|---|
| GET | `/api/bank/customers`, `/api/bank/customers/{id}` |
| GET | `/api/bank/customers/{id}/accounts` |
| GET | `/api/bank/customers/{id}/transactions?limit=20&days=30&category=FOOD` |
| GET | `/api/bank/customers/{id}/cards` |
| GET | `/api/bank/customers/{id}/risk/anomalies?days=30` |
| GET | `/api/bank/customers/{id}/risk/transactions/{txn_id}` |
| GET | `/api/bank/customers/{id}/credit-profile` |
| GET | `/api/bank/customers/{id}/loans` |
| GET | `/api/bank/customers/{id}/loans/eligibility?type=PERSONAL&amount=500000&tenure_months=36` |

```bash
curl -s localhost:8000/api/bank/customers/CUST1001/risk/anomalies | python -m json.tool
curl -s -X POST localhost:8000/api/chat -H 'Content-Type: application/json' \
  -d '{"session_id":"demo","customer_id":"CUST1002","message":"Am I eligible for a 10 lakh personal loan?"}'
```

---

## Project structure

```
app/
├── main.py              # FastAPI app: chat API, simulated bank REST API, serves the UI
├── config.py            # settings from environment / .env
├── agents/
│   ├── orchestrator.py  # runs a turn: route -> specialists -> synthesis; build_agents() = tool allow-lists
│   ├── supervisor.py    # LLM routing/planning (JSON) + synthesis, with keyword fallback
│   ├── specialist.py    # generic tool-calling agent loop
│   ├── prompts.py       # Supervisor and specialist prompts
│   ├── router.py        # deterministic keyword router (fallback + offline mode)
│   ├── memory.py        # per-session conversation memory
│   ├── trace.py         # execution trace shown in the UI
│   └── types.py         # AgentType enum
├── tools/toolkit.py     # tool definitions (JSON schema + handler), session-scoped ToolContext
├── bank/
│   ├── service.py       # simulated core-banking APIs (accounts, transfers, fraud, loans)
│   ├── risk.py          # rule-based, explainable risk scoring
│   ├── credit.py        # score cut-off, FOIR, rate card, EMI maths
│   ├── store.py         # in-memory data seeded with 3 demo customers
│   ├── models.py        # dataclasses: Customer, Account, Card, Transaction, Loan, ...
│   └── money.py         # Indian number formatting, JSON conversion
├── llm/
│   ├── base.py          # provider-neutral messages, tool specs, LlmClient protocol
│   ├── anthropic_client.py, openai_client.py, mock_client.py, factory.py
└── static/index.html    # UI (chat + agent activity timeline)
tests/                   # engines, parsing/router, end-to-end API, LLM wire formats
docs/                    # architecture notes, demo video script
```

## Configuration

| Env var | Default | Meaning |
|---|---|---|
| `LLM_PROVIDER` | `mock` | `mock`, `anthropic` or `openai` (any OpenAI-compatible API) |
| `LLM_MODEL` | provider default | Model id |
| `LLM_API_KEY` | (empty) | API key (not needed for mock / Ollama) |
| `LLM_BASE_URL` | provider default | Custom endpoint (Gemini, Groq, Ollama, proxy) |
| `LLM_MAX_TOKENS` / `LLM_TEMPERATURE` / `LLM_TIMEOUT_SECONDS` | `1024` / `0.2` / `90` | Generation settings |
| `AGENT_MAX_TOOL_ITERATIONS` | `6` | Max reasoning/tool rounds per agent per message |
| `AGENT_HISTORY_TURNS` | `6` | Conversation turns kept in short-term memory |

## Troubleshooting

- **"The AI model could not be reached: HTTP 401"**: the API key is missing or wrong for that provider.
- **HTTP 404 / model not found**: the model name isn't valid for that endpoint; set `LLM_MODEL`.
- **Agent ignores tools or answers vaguely**: small local models may not call tools reliably. Try a larger model.
- **Port in use**: `uvicorn app.main:app --port 9000`.

## Scope and limitations

This is an MVP. Data is in-memory, authentication is simulated with a customer picker, the fraud and credit
engines are transparent rule sets rather than trained models, and transactions don't stream from a live core. The
architecture doc explains how each of these would be replaced in production.
