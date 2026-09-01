"""The five assessment cases as pass/fail. Offline and deterministic."""
import json
from pathlib import Path

import pytest

from app.config import FIXTURES_DIR
from app.workflowagent import Agent

EXPECTED = {
    "FIN-001": "APPROVE_FOR_POSTING",
    "FIN-002": "REJECT_DUPLICATE",
    "FIN-003": "ESCALATE_CONTROL_REVIEW",
    "FIN-004": "HOLD_FOR_INFORMATION",
    "FIN-005": "APPROVE_FOR_POSTING",
}


def payload(cid):
    cases = json.loads((Path(FIXTURES_DIR) / "cases.json").read_text())
    return {k: v for k, v in cases[cid].items() if not k.startswith("_")}


@pytest.fixture
def agent(tmp_path):
    return Agent(db_path=str(tmp_path / "t.sqlite"))


@pytest.mark.parametrize("cid,expected", EXPECTED.items())
def test_case_outcome(agent, cid, expected):
    run = agent.start(payload(cid), run_id=f"e-{cid}")
    assert run["result"]["outcome"] == expected


def test_all_cases_pass(agent):
    res = agent.run_cases()
    assert res["passed"] == res["total"] == 5
