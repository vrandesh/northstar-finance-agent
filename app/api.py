""" Fast API Implementation to support  the following endpoints
    POST /runs
    POST /runs/{run_id}
    POST /runs/{run_id}/approve
    POST /evals 
"""


from decimal import Decimal
from app.workflowagent import Agent
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="NS AP Agent", version="1.0.0")
_agent: Agent | None = None

@app.post("/runs")
def create_run():
    if _agent is None:
        raise HTTPException(status_code=404, detail="Agent not initialized")
    return _agent.run_cases()


@app.get("/runs/{run_id}")
def get_run(run_id: str):
    if _agent is None:
        raise HTTPException(status_code=404, detail="Agent not initialized")
    return _agent.run_cases()


@app.post("/runs/{run_id}/approve")
def approve_run(run_id: str):
    if _agent is None:
        raise HTTPException(status_code=404, detail="Agent not initialized")
    return _agent.run_cases()

@app.post("/evals")
def evaluate():
    if _agent is None:
        raise HTTPException(status_code=404, detail="Agent not initialized")
    return _agent.run_cases()

@app.get("/healthcheck")
def health() -> dict:
    return {"status": "ok"}