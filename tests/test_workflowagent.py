"""Workflow safety + reliability tests: approval gate, idempotency, resume,
injection resistance, malformed model, optimistic concurrency, revalidation."""
import json
from pathlib import Path

import pytest

from app.config import FIXTURES_DIR
from app.model import FakeModel
from app.schemas import ToolResult, ToolStatus
from app.store import Store, mask
from app.tools import submit_decision
from app.workflowagent import Agent


def payload(cid):
    cases = json.loads((Path(FIXTURES_DIR) / "cases.json").read_text())
    return {k: v for k, v in cases[cid].items() if not k.startswith("_")}


@pytest.fixture
def agent(tmp_path):
    return Agent(db_path=str(tmp_path / "t.sqlite"))


def test_stops_before_posting(agent):
    run = agent.start(payload("FIN-001"), run_id="r1")
    assert run["status"] == "AWAITING_APPROVAL"
    assert not run["result"]["actions_taken"]        # nothing posted yet


def test_approve_then_submit_once(agent):
    run = agent.start(payload("FIN-001"), run_id="r2")
    done = agent.approve("r2", "approve", "cfo@x", "Chief Financial Officer", run["version"])
    assert done["status"] == "COMPLETED"
    assert len(done["result"]["actions_taken"]) == 1


def test_submit_deny_by_default(tmp_path):
    store = Store(str(tmp_path / "s.sqlite"))
    r = submit_decision(store, "r", "APPROVE_FOR_POSTING", "d", approved=False, approver="x")
    assert r.status is ToolStatus.ERROR


def test_submit_idempotent(tmp_path):
    store = Store(str(tmp_path / "s.sqlite"))
    a = submit_decision(store, "r", "APPROVE_FOR_POSTING", "same", approved=True, approver="x")
    b = submit_decision(store, "r", "APPROVE_FOR_POSTING", "same", approved=True, approver="x")
    assert a.data["replayed"] is False and b.data["replayed"] is True
    assert a.data["posting_ref"] == b.data["posting_ref"]


def test_duplicate_approval_one_effect(agent):
    run = agent.start(payload("FIN-005"), run_id="r3")
    v = run["version"]
    r1 = agent.approve("r3", "approve", "cfo@x", "Chief Financial Officer", v)
    r2 = agent.approve("r3", "approve", "cfo@x", "Chief Financial Officer", v)
    assert len(r1["result"]["actions_taken"]) == 1
    assert len(r2["result"]["actions_taken"]) == 1


def test_restart_resume(tmp_path):
    db = str(tmp_path / "r.sqlite")
    a1 = Agent(db_path=db)
    run = a1.start(payload("FIN-001"), run_id="r4")
    del a1                                             # simulate process death
    a2 = Agent(db_path=db)
    assert a2.get("r4")["status"] == "AWAITING_APPROVAL"
    done = a2.approve("r4", "approve", "cfo@x", "Chief Financial Officer", run["version"])
    assert done["status"] == "COMPLETED" and done["result"]["actions_taken"]


def test_optimistic_concurrency(agent):
    run = agent.start(payload("FIN-001"), run_id="r5")
    stale = agent.approve("r5", "approve", "cfo@x", "Chief Financial Officer", run["version"] + 5)
    assert stale.get("conflict") is True and stale["status"] == "AWAITING_APPROVAL"
    ok = agent.approve("r5", "approve", "cfo@x", "Chief Financial Officer", run["version"])
    assert ok["status"] == "COMPLETED"


def test_revalidation_blocks_stale_vendor(agent, monkeypatch):
    run = agent.start(payload("FIN-001"), run_id="r6")
    blocked = ToolResult(tool="get_vendor_record", status=ToolStatus.OK, duration_ms=1,
                         data={"vendor_id": "V-1001", "legal_name": "X", "status": "BLOCKED",
                               "risk_flags": [], "bank_last4": "1234", "bank_country": "AU",
                               "created_at": "2020-01-01", "last_updated": "2026-08-31"})
    monkeypatch.setattr("app.tools.get_vendor_record", lambda vid: blocked)
    done = agent.approve("r6", "approve", "cfo@x", "Chief Financial Officer", run["version"])
    assert done["result"]["outcome"] == "ESCALATE_CONTROL_REVIEW"
    assert not done["result"]["actions_taken"]


def test_injection_cannot_pay(tmp_path):
    agent = Agent(db_path=str(tmp_path / "i.sqlite"), llm=FakeModel(adversarial=True))
    run = agent.start(payload("FIN-003"), run_id="r7")
    assert run["result"]["outcome"] == "ESCALATE_CONTROL_REVIEW"
    assert run["result"]["actions_taken"] == []


def test_malformed_model_degrades(tmp_path):
    class Junk:
        def complete(self, system, user):
            return "not json"
    agent = Agent(db_path=str(tmp_path / "m.sqlite"), llm=Junk())
    run = agent.start(payload("FIN-001"), run_id="r8")
    assert run["result"]["outcome"] == "APPROVE_FOR_POSTING"   # code decides regardless


def test_invalid_request_rejected(agent):
    run = agent.start({"case_id": "BAD", "invoice_ref": "X", "vendor_id": "V",
                       "amount": "-1", "currency": "AUD"}, run_id="r9")
    assert run["result"]["outcome"] == "REJECT_INVALID"


def test_masking():
    assert mask("acct 123456789") == "acct ****6789"
    assert mask("amount 30000") == "amount 30000"
