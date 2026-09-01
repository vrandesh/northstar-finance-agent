"""_summary_
    Purpose of this control engine is to read the reference file and type it block by block.
    
    Returns: Returns duplicate -> injection/bank-change -> vendor status -> missing Purchase order -> 
    currency -> receipts -> tolerance -> Purchase Order Approved -> Approved
"""

import re
from dataclasses import dataclass, field
from decimal import Decimal

from .config import AUTHORITY_MATRIX
from .retrieval import load_corpus
from .schemas import (Calc, CaseRequest, Citation, ExceptionCategory, ExceptionItem,
                      Fact, Outcome, PolicyFinding, ToolResult, ToolStatus)

TOLERANCE_CAP = Decimal("50")

# words that try to override our controls - Note : Used help from AI to get this refactored in the right manner 
_OVERRIDE = [r"ignore (all )?(previous|prior|above)", r"skip (the )?(duplicate|check|approval)",
             r"release (the )?payment (now|immediately)", r"do not (ask|contact|notify)",
             r"already (been )?approved (confidential|privately)", r"bypass"]
_SOFT = {"urgency": r"\b(urgent|immediately|asap)\b", "bank_hint": r"\b(new account|updated bank|bank .*changed)\b"}


# ------------------------------------Policy Class--------------------------------------- #
class Policy:
    """This class takes the document name, section number and then finds the exact matching citation
    from the stored policy documents. Intent for this is to act like a small lookup helper forpolicy references"""

    def __init__(self) -> None:
        self._docs: dict[str, dict] = {}
        for c in load_corpus():
            entry = self._docs.setdefault(c.doc_id, {"version": c.version, "sections": {}})
            num = c.section.split(" ", 1)[0].lstrip("§")
            if num.isdigit():
                entry["sections"][int(num)] = c.section

    def cite(self, doc: str, section: int) -> Citation:
        d = self._docs.get(doc, {"version": "?", "sections": {}})
        return Citation(doc_id=doc, version=d["version"], section=d["sections"].get(section, f"§{section}"))


def scan_for_injection(texts: list[str]) -> tuple[bool, list[str]]:
    """method checks input text and notes for suspicious instructions then return
    * whether something risky was found 
    * a list of warning signs it noticed
    """
    blob = "\n".join(t for t in texts if t).lower()
    signals: list[str] = []
    attacked = any(re.search(p, blob) for p in _OVERRIDE)
    if attacked:
        signals.append("instruction_override")
    for name, pat in _SOFT.items():
        if re.search(pat, blob):
            signals.append(name)
    return attacked, signals


def role_for_amount(amount: Decimal) -> str:
    for role, limit in AUTHORITY_MATRIX:
        if amount <= Decimal(limit):
            return role
    return "Chief Executive Officer"


# --------------------------------------------------------------------------- #
@dataclass
class Decision:
    outcome: Outcome
    control: str
    required_role: str = ""
    facts: list[Fact] = field(default_factory=list)
    calculations: list[Calc] = field(default_factory=list)
    policy_findings: list[PolicyFinding] = field(default_factory=list)
    exceptions: list[ExceptionItem] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    confidence: float = 0.0

    def context(self) -> dict:
        return {"case_id": self._case_id, "outcome": self.outcome.value,
                "exceptions": [e.category.value for e in self.exceptions]}

    _case_id: str = ""


def reconcile(case: CaseRequest, *, vendor: ToolResult, po: ToolResult,
              history: ToolResult, injection: tuple[bool, list[str]],
              policy: Policy | None = None) -> Decision:
    policy = policy or Policy()
    attacked, signals = injection
    v = vendor.data if vendor.status == ToolStatus.OK else None
    p = po.data if po.status == ToolStatus.OK else None

    facts: list[Fact] = []
    calcs: list[Calc] = []
    findings: list[PolicyFinding] = []
    exceptions: list[ExceptionItem] = []
    unknowns: list[str] = []

    def finding(doc, sec, passed, detail):
        findings.append(PolicyFinding(rule=f"{doc} {policy.cite(doc, sec).section}",
                                      citation=policy.cite(doc, sec), passed=passed, detail=detail))

    def exception(cat, rule, expected, observed, owner):
        exceptions.append(ExceptionItem(category=cat, rule=rule, expected=expected,
                                        observed=observed, owner=owner))

    def decide(outcome, control, role=""):
        conf = max(0.1, min(1.0, 1.0 - 0.2 * len(exceptions) - 0.3 * len(unknowns)))
        d = Decision(outcome=outcome, control=control, required_role=role, facts=facts,
                     calculations=calcs, policy_findings=findings, exceptions=exceptions,
                     unknowns=unknowns, confidence=round(conf, 2))
        d._case_id = case.case_id
        return d

    # 1. Duplicate of an already-paid invoice
    if history.status == ToolStatus.OK and history.data:
        paid = [m for m in history.data if m["status"] in ("paid", "posted")]
        if paid:
            exception(ExceptionCategory.DUPLICATE_RISK, "FIN-POL-005 §1", "no prior paid invoice",
                      f"exact match {paid[0]['ref']}", "Financial Crime and Controls")
            finding("FIN-POL-005", 2, False, "Exact match to a paid invoice.")
            facts.append(Fact(statement="An exact duplicate of a paid invoice must be rejected.",
                              citation=policy.cite("FIN-POL-005", 2)))
            return decide(Outcome.REJECT_DUPLICATE, "duplicate")
    finding("FIN-POL-005", 1, True, "No exact duplicate found.")

    # 2. Injection or a changed/overseas bank => escalate, do not act on the text
    bank_risk = bool(v) and ("bank_changed" in v.get("risk_flags", []))
    if attacked or bank_risk:
        if attacked:
            exception(ExceptionCategory.SUSPECTED_INJECTION, "FIN-POL-005 §4",
                      "documents treated as evidence only", f"override text: {signals}",
                      "Financial Crime and Controls")
            finding("FIN-POL-005", 4, False, "Injected instructions detected; treated as risk.")
            facts.append(Fact(statement="Text telling the agent to disable checks is a risk signal, not an instruction.",
                              citation=policy.cite("FIN-POL-005", 4)))
        if bank_risk:
            exception(ExceptionCategory.BANK_CHANGE, "FIN-POL-004 §2", "verified bank change",
                      "unverified bank change on file", "Vendor Governance")
            finding("FIN-POL-004", 2, False, "Bank change must be verified independently.")
        return decide(Outcome.ESCALATE_CONTROL_REVIEW, "injection_or_bank_change")

    # 3. Vendor must be active
    if v is None:
        unknowns.append(f"vendor record unavailable ({vendor.status.value})")
    elif v["status"] != "ACTIVE":
        exception(ExceptionCategory.VENDOR_BLOCK, "FIN-POL-004 §4", "vendor ACTIVE",
                  f"vendor status {v['status']}", "Vendor Governance")
        finding("FIN-POL-004", 4, False, "Vendor not ACTIVE.")
        return decide(Outcome.HOLD_FOR_INFORMATION, "vendor_blocked")
    else:
        finding("FIN-POL-004", 4, True, "Vendor is ACTIVE.")
        facts.append(Fact(statement=f"Vendor {case.vendor_id} is ACTIVE.", citation=policy.cite("FIN-POL-004", 4)))

    # 4. We need the purchase order to match against
    if p is None:
        unknowns.append(f"purchase order unavailable ({po.status.value})")
        exception(ExceptionCategory.MISSING_PO, "FIN-POL-002 §1", "PO retrievable",
                  f"PO tool returned {po.status.value}", "Requester")
        finding("FIN-POL-002", 4, False, "Required PO/receipt evidence missing.")
        facts.append(Fact(statement="An invoice without required evidence cannot be approved for payment.",
                          citation=policy.cite("FIN-POL-002", 4)))
        return decide(Outcome.HOLD_FOR_INFORMATION, "missing_po")

    # 5a. Currency must match
    if p["currency"].upper() != case.currency.upper():
        exception(ExceptionCategory.PRICE_VARIANCE, "FIN-POL-009 §1", f"PO currency {p['currency']}",
                  f"invoice currency {case.currency}", "Treasury")
        finding("FIN-POL-009", 1, False, "Invoice/PO currency mismatch.")
        return decide(Outcome.HOLD_FOR_INFORMATION, "currency_mismatch")

    # 5b. Each line must have been received
    received = {r["line_id"]: Decimal(str(r["received_quantity"])) for r in p.get("receipts", [])}
    for line in p["lines"]:
        got = received.get(line["line_id"], Decimal("0"))
        if got < Decimal(str(line["quantity"])):
            exception(ExceptionCategory.MISSING_RECEIPT, "FIN-POL-002 §4",
                      f"received >= {line['quantity']}", f"received {got}", "Receipter")
    if any(e.category is ExceptionCategory.MISSING_RECEIPT for e in exceptions):
        finding("FIN-POL-002", 4, False, "Receipt missing or short.")
        return decide(Outcome.HOLD_FOR_INFORMATION, "missing_receipt")

    # 5c. Invoice total must match the PO within tolerance
    po_total = Decimal(str(p["total"]))
    variance = (case.amount - po_total).copy_abs().quantize(Decimal("0.01"))
    tolerance = min(TOLERANCE_CAP, po_total * Decimal("0.01")).quantize(Decimal("0.01"))
    calcs.append(Calc(name="three_way_match",
                      inputs={"invoice": str(case.amount), "po_total": str(po_total), "tolerance": str(tolerance)},
                      formula="abs(invoice - po_total) <= min(50, 1% of po_total)",
                      result=f"variance={variance} within_tolerance={variance <= tolerance}"))
    if variance > tolerance:
        exception(ExceptionCategory.PRICE_VARIANCE, "FIN-POL-002 §2", f"variance <= {tolerance}",
                  f"variance {variance}", "Requester")
        finding("FIN-POL-002", 3, False, "Total variance outside tolerance.")
        return decide(Outcome.HOLD_FOR_INFORMATION, "price_variance")
    finding("FIN-POL-002", 2, True, "Invoice, PO and receipt agree within tolerance.")
    facts.append(Fact(statement="Invoice, PO and receipt agree within tolerance (three-way match).",
                      citation=policy.cite("FIN-POL-002", 1)))

    # 6. The PO itself must be approved
    if p["approval_status"] != "approved":
        exception(ExceptionCategory.AUTHORITY_GAP, "FIN-POL-003 §5", "approved PO",
                  f"PO status {p['approval_status']}", "Financial Control")
        finding("FIN-POL-003", 5, False, "PO not approved.")
        return decide(Outcome.HOLD_FOR_INFORMATION, "po_not_approved")

    # 7. Everything passed — approve and name the required approver
    role = role_for_amount(case.amount)
    calcs.append(Calc(name="approval_authority", inputs={"amount": str(case.amount)},
                      formula="lowest role whose limit >= amount (FIN-POL-003 v4.0)",
                      result=f"required_role={role}"))
    finding("FIN-POL-003", 2, True, f"Requires approval by {role}.")
    facts.append(Fact(statement=f"Commitment of AUD {case.amount} requires approval by {role}.",
                      citation=policy.cite("FIN-POL-003", 2)))
    return decide(Outcome.APPROVE_FOR_POSTING, "approved", role)


def revalidate_vendor(vendor: ToolResult) -> tuple[bool, str]:
    """Re-check the vendor at approval time in case it changed while we waited"""
    if vendor.status != ToolStatus.OK or not vendor.data:
        return False, "vendor record unavailable at approval time"
    if vendor.data["status"] != "ACTIVE":
        return False, f"vendor became {vendor.data['status']}"
    if "bank_changed" in vendor.data.get("risk_flags", []):
        return False, "unverified bank change at approval time"
    return True, "ok"