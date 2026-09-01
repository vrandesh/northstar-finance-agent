""" Fast API Implementation to support  the following endpoints
    POST /runs
    POST /runs/{run_id}
    POST /runs/{run_id}/approve
    POST /evals 
"""

from decimal import Decimal
from typing import Literal
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from .workflowagent import Agent

app = FastAPI(title="NS AP Agent", version="1.0.0")
_agent: Agent | None = None

def agent() -> Agent:
    global _agent
    if _agent is None:
        _agent = Agent()
    return _agent

class StartBody(BaseModel):
    case_id: str
    invoice_ref: str
    vendor_id: str
    amount: Decimal
    currency: str
    notes: str = ""
    attachment_doc_ids: list[str] = []

class ApproveBody(BaseModel):
    decision: Literal["approve", "reject"]
    approver: str
    approver_role: str
    expected_version: int | None = None


@app.post("/runs")
def start_run(body: StartBody) -> dict:
    return agent().start(body.model_dump(mode="json"))


@app.get("/runs/{run_id}")
def get_run(run_id: str) -> dict:
    run = agent().get(run_id)
    if run.get("status") == "NOT_FOUND":
        raise HTTPException(404, "run not found")
    return run


@app.post("/runs/{run_id}/approve")
def approve(run_id: str, body: ApproveBody) -> dict:
    run = agent().approve(run_id, **body.model_dump())
    if run.get("status") == "NOT_FOUND":
        raise HTTPException(404, "run not found")
    return run


@app.post("/evaluations")
def evaluations() -> dict:
    return agent().run_cases()


@app.get("/healthcheck")
def health() -> dict:
    return {"status": "ok"}