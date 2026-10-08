"""FastAPI application: chat API used by the UI, simulated banking REST APIs, and the static UI."""
from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from .agents.orchestrator import Orchestrator
from .bank.errors import BankError
from .bank.money import to_jsonable
from .bank.service import CoreBankingService
from .llm.base import LlmError
from .llm.factory import create_llm_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("agentbank")

STATIC = Path(__file__).parent / "static"


class ChatRequest(BaseModel):
    session_id: str = Field(default_factory=lambda: uuid.uuid4().hex, min_length=1, max_length=100)
    customer_id: str = Field(min_length=1, max_length=20)
    message: str = Field(min_length=1, max_length=2000)


class ResetRequest(BaseModel):
    session_id: str
    customer_id: str


def create_app(orchestrator: Orchestrator | None = None) -> FastAPI:
    orch = orchestrator or Orchestrator(create_llm_client())
    bank: CoreBankingService = orch.bank
    log.info("AgentBank LLM provider: %s", orch.llm.describe())

    app = FastAPI(title="AgentBank", version="0.1.0",
                  description="Multi-agent banking assistant MVP: Supervisor + Customer Service, Fraud & Risk, "
                              "Credit & Loans agents over simulated banking APIs.")
    app.state.orchestrator = orch

    @app.exception_handler(BankError)
    async def bank_error(_: Request, e: BankError):
        return JSONResponse(status_code=400, content={"error": str(e)})

    @app.exception_handler(RequestValidationError)
    async def invalid(_: Request, e: RequestValidationError):
        return JSONResponse(status_code=422, content={
            "error": "Invalid request: customer_id and a message (1-2000 characters) are required",
            "details": to_jsonable(e.errors())})

    @app.exception_handler(LlmError)
    async def llm_error(_: Request, e: LlmError):
        return JSONResponse(status_code=502, content={"error": f"The AI model could not be reached: {e}"})

    # ------------------------------------------------------------------ UI
    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC / "index.html")

    # ------------------------------------------------------------------ chat
    @app.post("/api/chat", tags=["chat"])
    def chat(req: ChatRequest):
        r = orch.handle(req.session_id, req.customer_id, req.message.strip())
        return to_jsonable({"reply": r.reply, "agents": r.agents, "trace": r.trace,
                            "elapsed_ms": r.elapsed_ms, "model": orch.llm.describe()})

    @app.post("/api/chat/reset", tags=["chat"])
    def reset(req: ResetRequest):
        orch.reset(req.session_id, req.customer_id)
        return {"status": "cleared"}

    @app.get("/api/customers", tags=["chat"])
    def customers():
        """Demo personas for the UI's customer switcher (simulates an authenticated login)."""
        return to_jsonable([{"id": c.id, "name": c.name, "segment": c.segment, "city": c.city,
                             "accounts": bank.get_accounts(c.id)} for c in bank.list_customers()])

    @app.get("/api/meta", tags=["chat"])
    def meta():
        return {"model": orch.llm.describe(),
                "agents": {t.value: {"label": t.label, "tools": a.tool_names} for t, a in orch.agents.items()}}

    # ------------------------------------------------------------------ simulated banking APIs
    # Agents call the same CoreBankingService in-process through tools; these endpoints let the "bank" be
    # inspected and tested independently (curl / Swagger UI at /docs).
    @app.get("/api/bank/customers", tags=["bank"])
    def bank_customers():
        return to_jsonable(bank.list_customers())

    @app.get("/api/bank/customers/{cid}", tags=["bank"])
    def bank_customer(cid: str):
        return to_jsonable(bank.get_customer(cid))

    @app.get("/api/bank/customers/{cid}/accounts", tags=["bank"])
    def bank_accounts(cid: str):
        return to_jsonable(bank.get_accounts(cid))

    @app.get("/api/bank/customers/{cid}/transactions", tags=["bank"])
    def bank_transactions(cid: str, limit: int = 20, days: int = 30, category: str | None = None):
        return to_jsonable(bank.recent_transactions(cid, limit, category, days))

    @app.get("/api/bank/customers/{cid}/cards", tags=["bank"])
    def bank_cards(cid: str):
        return to_jsonable(bank.get_cards(cid))

    @app.get("/api/bank/customers/{cid}/risk/anomalies", tags=["bank"])
    def bank_anomalies(cid: str, days: int = 30):
        return to_jsonable(bank.scan_for_anomalies(cid, days))

    @app.get("/api/bank/customers/{cid}/risk/transactions/{txn_id}", tags=["bank"])
    def bank_txn_risk(cid: str, txn_id: str):
        return to_jsonable(bank.assess_transaction(cid, txn_id))

    @app.get("/api/bank/customers/{cid}/credit-profile", tags=["bank"])
    def bank_credit(cid: str):
        return to_jsonable(bank.get_credit_profile(cid))

    @app.get("/api/bank/customers/{cid}/loans", tags=["bank"])
    def bank_loans(cid: str):
        return to_jsonable(bank.get_loans(cid))

    @app.get("/api/bank/customers/{cid}/loans/eligibility", tags=["bank"])
    def bank_eligibility(cid: str, amount: Decimal = Query(gt=0), type: str = "PERSONAL", tenure_months: int = 36):
        return to_jsonable(bank.check_eligibility(cid, type, amount, tenure_months))

    return app


app = create_app()
