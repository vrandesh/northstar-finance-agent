""" 
Workflow implementation for the Northstar Finance Agent.

Utilizes LangGraph for orchestrating the workflow logic.

Strategy/Design: 
1. Nodes run in the following order
 - Intake
 - Retrieve
 - gather
 - Reconcile
 - Explain
2. Then the graph either finishes successfully at a human in loop approval gate or encounters an error at any of the nodes.
3. On Approval, it resumes and submits exactly once
4. LangGraph manages the execution flow and ensures that each node is executed according to the defined strategy.
5. Exception Checkpointer is provided by the LangGraph that ensures a run survives a restart and the interrupted execution can resume from the last checkpoint.
6. Safety Guardrails enforced within the code
"""

import sqlite3
import uuid
from typing import Any, Dict, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from pydantic import ValidationError

from . import config, model, tools
from .reconcile import Decision, Policy, reconcile, revalidate_vendor, scan_for_injection
from .retrieval import Retriever
from .schemas import (Action, ApprovalRequest, CaseRequest, Fact, Inference, Outcome,
                      Recommendation, ToolResult, ToolStatus)
from .store import Store

class State(TypedDict, total=False):
    run_id: str
    raw_case: dict
    case: dict
    retrieved: list
    untrusted_texts: list
    tools: dict
    injection: dict
    recon: dict
    outcome: str
    recommendation: dict
    decision: dict
    status: str
    

# --------------------------------------------------------------------------- #
class Agent:

    def __init__(self, db_path: str | None = None, llm=None) -> None:
        self.db_path = db_path or config.DB_PATH
        self.store = Store(self.db_path)
        self.retriever = Retriever()
        self.policy = Policy()
        self.model = llm or model.get_model(config.LLM_PROVIDER, config.LLM_MODEL)
        self.graph = self._build()

    def _cfg(self, run_id: str) -> dict:
        return {"configurable": {"thread_id": run_id}, "recursion_limit": config.MAX_STEPS + 10}

    def _build(self):
        saver = SqliteSaver(sqlite3.connect(self.db_path, check_same_thread=False))
        g = StateGraph(State)
        g.add_node("intake", self.intake)
        g.add_node("retrieve", self.retrieve)
        g.add_node("gather", self.gather)
        g.add_node("reconcile", self.reconcile)
        g.add_node("explain", self.explain)
        g.add_node("approval_gate", self.approval_gate)
        g.add_node("submit", self.submit)
        g.add_node("finalize", self.finalize)
        g.add_edge(START, "intake")
        g.add_conditional_edges("intake", lambda s: "finalize" if s.get("status") == "COMPLETED" else "retrieve",
                                {"retrieve": "retrieve", "finalize": "finalize"})
        g.add_edge("retrieve", "gather")
        g.add_edge("gather", "reconcile")
        g.add_edge("reconcile", "explain")
        g.add_conditional_edges("explain", self._route_after_explain,
                                {"approval_gate": "approval_gate", "finalize": "finalize"})
        g.add_conditional_edges("approval_gate", self._route_after_gate,
                                {"submit": "submit", "finalize": "finalize"})
        g.add_edge("submit", "finalize")
        g.add_edge("finalize", END)
        return g.compile(checkpointer=saver)

    # ----------------------------------------- nodes ------------------------------------- #
    def intake(self, s: State) -> dict:
        try:
            case = CaseRequest.model_validate(s["raw_case"])
        except ValidationError as e:
            self.store.log(s["run_id"], "intake", "invalid", "REJECT_INVALID", {"errors": e.errors(include_url=False)})
            rec = Recommendation(run_id=s["run_id"], case_id=str(s["raw_case"].get("case_id", "?")),
                                 outcome=Outcome.REJECT_INVALID, summary="Rejected: invalid request.",
                                 unknowns=["request failed validation"])
            return {"status": "COMPLETED", "outcome": rec.outcome.value, "recommendation": rec.model_dump(mode="json")}
        self.store.log(s["run_id"], "intake", "validated", detail={"case_id": case.case_id})
        return {"case": case.model_dump(mode="json"), "status": "RUNNING"}

    def retrieve(self, s: State) -> dict:
        case = CaseRequest.model_validate(s["case"])
        query = f"{case.notes} duplicate invoice three-way match tolerance authority vendor bank change"
        r = self.retriever.search(query, k=config.RETRIEVE_K, force_include=case.attachment_doc_ids)
        self.store.log(s["run_id"], "retrieve", "done", detail={
            "retrieved": [c.doc_id for c in r.retrieved],
            "untrusted": [c.doc_id for c in r.retrieved if not c.trusted]})
        return {"retrieved": [c.model_dump(mode="json") for c in r.retrieved],
                "untrusted_texts": [c.text for c in r.retrieved if not c.trusted]}

    def gather(self, s: State) -> dict:
        case = CaseRequest.model_validate(s["case"])
        po_ref = tools.resolve_po_ref(case.invoice_ref)
        results = {
            "vendor": tools.get_vendor_record(case.vendor_id),
            "history": tools.check_invoice_history(case.vendor_id, case.invoice_ref, case.currency, str(case.amount)),
            "po": (tools.get_purchase_order(po_ref) if po_ref
                   else ToolResult(tool="get_purchase_order", status=ToolStatus.NOT_FOUND, duration_ms=0)),
        }
        for r in results.values():
            self.store.log(s["run_id"], "gather", r.tool, r.status.value, {"attempts": r.attempts})
        attacked, signals = scan_for_injection([case.notes] + s.get("untrusted_texts", []))
        if attacked:
            self.store.log(s["run_id"], "gather", "injection", "SUSPECTED", {"signals": signals})
        return {"tools": {k: v.model_dump(mode="json") for k, v in results.items()},
                "injection": {"attacked": attacked, "signals": signals}}

    def reconcile(self, s: State) -> dict:
        case = CaseRequest.model_validate(s["case"])
        t = {k: ToolResult.model_validate(v) for k, v in s["tools"].items()}
        d = reconcile(case, vendor=t["vendor"], po=t["po"], history=t["history"],
                      injection=(s["injection"]["attacked"], s["injection"]["signals"]), policy=self.policy)
        self.store.log(s["run_id"], "reconcile", "decided", d.outcome.value,
                       {"control": d.control, "required_role": d.required_role})
        return {"recon": _dump(d), "outcome": d.outcome.value}

    def explain(self, s: State) -> dict:
        case = CaseRequest.model_validate(s["case"])
        d = s["recon"]
        inferences = []
        try:
            ex = model.explain(self.model, d["context"])
            summary = ex.summary
            inferences.append(Inference(statement="model wrote an explanation (no outcome authority)",
                                        confidence=ex.confidence))
        except ValueError:
            summary = f"[deterministic] Control engine determined {s['outcome']}."
            self.store.log(s["run_id"], "explain", "degraded", s["outcome"])
        rec = Recommendation(run_id=s["run_id"], case_id=case.case_id, outcome=Outcome(s["outcome"]),
                             summary=summary, required_role=d["required_role"], confidence=d["confidence"],
                             sourced_facts=[Fact.model_validate(f) for f in d["facts"]],
                             calculations=d["calculations"], inferences=inferences,
                             unknowns=d["unknowns"], policy_findings=d["policy_findings"],
                             exceptions=d["exceptions"])
        self.store.log(s["run_id"], "explain", "drafted", s["outcome"])
        return {"recommendation": rec.model_dump(mode="json")}

    def approval_gate(self, s: State) -> dict:
        case = CaseRequest.model_validate(s["case"])
        # keep this idempotent: LangGraph re-runs the code before interrupt on resume
        existing = self.store.get_approval(s["run_id"])
        if not existing or existing["status"] == "pending":
            version = self.store.save_run(s["run_id"], case.case_id, "AWAITING_APPROVAL",
                                          result=s.get("recommendation"))
            req = ApprovalRequest(run_id=s["run_id"], case_id=case.case_id, amount=case.amount,
                                  currency=case.currency, vendor_id=case.vendor_id,
                                  required_role=s["recon"]["required_role"], expected_version=version,
                                  citations=[Fact.model_validate(f).citation for f in s["recon"]["facts"]])
            self.store.set_approval(s["run_id"], request=req.model_dump(mode="json"), status="pending")
            self.store.log(s["run_id"], "approval_gate", "paused", "AWAITING_APPROVAL",
                           {"required_role": req.required_role, "expected_version": version})
        decision = interrupt({"run_id": s["run_id"]})
        return {"decision": decision}

    def submit(self, s: State) -> dict:
        rec = Recommendation.model_validate(s["recommendation"])
        digest = tools.action_digest(rec.case_id, s["outcome"],
                                     [f.model_dump(mode="json") for f in rec.sourced_facts],
                                     [c.model_dump(mode="json") for c in rec.calculations])
        res = tools.submit_decision(self.store, s["run_id"], s["outcome"], digest,
                                    approved=True, approver=s["decision"].get("approver", "?"))
        self.store.log(s["run_id"], "submit", "posted", res.status.value,
                       {"posting_ref": (res.data or {}).get("posting_ref"),
                        "replayed": (res.data or {}).get("replayed")})
        if res.status == ToolStatus.OK:
            rec.actions_taken.append(Action(tool="submit_decision", idempotency_key=digest,
                                            posting_ref=res.data["posting_ref"], applied=True,
                                            replayed=res.data.get("replayed", False)))
        return {"recommendation": rec.model_dump(mode="json")}

    def finalize(self, s: State) -> dict:
        case_id = (s.get("case") or s.get("raw_case") or {}).get("case_id", "?")
        self.store.save_run(s["run_id"], case_id, "COMPLETED", result=s.get("recommendation"))
        self.store.log(s["run_id"], "finalize", "completed", s.get("outcome", ""))
        return {"status": "COMPLETED"}

    # ---- routing ----
    @staticmethod
    def _route_after_explain(s: State) -> str:
        return "approval_gate" if s.get("outcome") == Outcome.APPROVE_FOR_POSTING.value else "finalize"

    @staticmethod
    def _route_after_gate(s: State) -> str:
        return "submit" if s.get("decision", {}).get("decision") == "approve" else "finalize"

    # ---- public API (start / get / approve) ----
    def start(self, case: dict, run_id: str | None = None) -> dict:
        run_id = run_id or f"run-{uuid.uuid4().hex[:12]}"
        self.store.save_run(run_id, str(case.get("case_id", "?")), "RUNNING", bump=False)
        try:
            self.graph.invoke({"run_id": run_id, "raw_case": case}, self._cfg(run_id))
        except GraphRecursionError:
            self.store.save_run(run_id, str(case.get("case_id", "?")), "FAILED")
        return self.get(run_id)

    def get(self, run_id: str) -> dict:
        run = self.store.get_run(run_id)
        if not run:
            return {"run_id": run_id, "status": "NOT_FOUND"}
        run["approval"] = self.store.get_approval(run_id)
        run["events"] = self.store.events(run_id)
        return run

    def approve(self, run_id: str, decision: str, approver: str, approver_role: str,
                expected_version: int | None = None) -> dict:
        run = self.store.get_run(run_id)
        if not run:
            return {"run_id": run_id, "status": "NOT_FOUND"}
        approval = self.store.get_approval(run_id)
        if not approval or approval["status"] != "pending":
            self.store.log(run_id, "approve", "duplicate_ignored", (approval or {}).get("status", "none"))
            return self.get(run_id)                                   # replay-safe
        if expected_version is not None and expected_version != run["version"]:
            self.store.log(run_id, "approve", "stale_version", detail={"expected": expected_version, "actual": run["version"]})
            return {**self.get(run_id), "conflict": True}
        if decision == "reject":
            self.store.set_approval(run_id, status="rejected", decision={"decision": "reject", "approver": approver})
            self._resume(run_id, {"decision": "reject", "approver": approver})
            return self.get(run_id)
        # approve: check the role covers the amount, then revalidate the vendor
        req = approval["request"]
        if not self._role_ok(approver_role, req["required_role"]):
            return {**self.get(run_id), "error": f"{approver_role} cannot approve; needs {req['required_role']}"}
        ok, reason = revalidate_vendor(tools.get_vendor_record(req["vendor_id"]))
        if not ok:
            self.store.set_approval(run_id, status="revalidation_failed", decision={"reason": reason})
            self._resume(run_id, {"decision": "reject", "approver": approver})
            self._escalate(run_id, run["case_id"], reason)
            return self.get(run_id)
        self.store.set_approval(run_id, status="approved",
                                decision={"decision": "approve", "approver": approver, "role": approver_role})
        self._resume(run_id, {"decision": "approve", "approver": approver})
        return self.get(run_id)

    def run_cases(self) -> dict:
        import json
        from pathlib import Path
        cases = json.loads((Path(config.FIXTURES_DIR) / "cases.json").read_text())
        results, passed = [], 0
        for cid, case in cases.items():
            expected = case.get("_expected")
            payload = {k: v for k, v in case.items() if not k.startswith("_")}
            run = self.start(payload, run_id=f"eval-{cid}-{uuid.uuid4().hex[:6]}")
            got = (run.get("result") or {}).get("outcome")
            if got == "APPROVE_FOR_POSTING":
                self.approve(run["run_id"], "approve", "cfo@northstar", "Chief Financial Officer",
                             expected_version=run["version"])
                run = self.get(run["run_id"])
            ok = got == expected
            passed += ok
            results.append({"case": cid, "expected": expected, "got": got, "pass": ok})
        return {"passed": passed, "total": len(cases), "results": results}

    # ---- helpers ----
    def _resume(self, run_id: str, payload: dict) -> None:
        try:
            self.graph.invoke(Command(resume=payload), self._cfg(run_id))
        except GraphRecursionError:
            self.store.save_run(run_id, "?", "FAILED")

    def _escalate(self, run_id: str, case_id: str, reason: str) -> None:
        run = self.store.get_run(run_id)
        rec = (run or {}).get("result") or {}
        rec["outcome"] = Outcome.ESCALATE_CONTROL_REVIEW.value
        rec["actions_taken"] = []
        rec.setdefault("unknowns", []).append(f"revalidation failed: {reason}")
        self.store.save_run(run_id, case_id, "COMPLETED", result=rec)

    @staticmethod
    def _role_ok(approver_role: str, required_role: str) -> bool:
        limits = {role: limit for role, limit in config.AUTHORITY_MATRIX}
        return limits.get(approver_role, 0) >= limits.get(required_role, 10 ** 12)


def _dump(d: Decision) -> dict:
    return {"outcome": d.outcome.value, "control": d.control, "required_role": d.required_role,
            "confidence": d.confidence, "unknowns": d.unknowns, "context": d.context(),
            "facts": [f.model_dump(mode="json") for f in d.facts],
            "calculations": [c.model_dump(mode="json") for c in d.calculations],
            "policy_findings": [p.model_dump(mode="json") for p in d.policy_findings],
            "exceptions": [e.model_dump(mode="json") for e in d.exceptions]}