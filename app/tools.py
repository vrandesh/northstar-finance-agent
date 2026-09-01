"""
Finance Tools

Get Vendor Record
Get Purchase Order
Check Invoice History
Get Approver Record
Submit Finance Decision
"""

import hashlib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from decimal import Decimal
from pathlib import Path
from typing import Callable

from .config import FIXTURES_DIR, TIMEOUT_PO_REFS, TOOL_MAX_ATTEMPTS, TOOL_TIMEOUT_MS
from .schemas import ToolResult, ToolStatus

_POOL = ThreadPoolExecutor(max_workers=4)

class ToolTimeout(Exception):
    pass


class ToolMissing(Exception):
    pass

def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _load(name: str):
    return json.loads((Path(FIXTURES_DIR) / name).read_text(encoding="utf-8"))


def run_tool(name: str, fn: Callable, timeout_ms: int = TOOL_TIMEOUT_MS,
             max_attempts: int = TOOL_MAX_ATTEMPTS) -> ToolResult:
    """Run a tool with a real wall-clock timeout and bounded retry. Expected
    failures come back as a typed result, not an exception."""
    started = time.perf_counter()
    for attempt in range(1, max_attempts + 1):
        try:
            future = _POOL.submit(fn)
            try:
                data = future.result(timeout=timeout_ms / 1000)
            except FutureTimeout:
                raise ToolTimeout(f"{name} timed out")
            return ToolResult(tool=name, status=ToolStatus.OK, data=data,
                              attempts=attempt, duration_ms=_ms(started))
        except ToolMissing as e:
            return ToolResult(tool=name, status=ToolStatus.NOT_FOUND, error=str(e),
                              attempts=attempt, duration_ms=_ms(started))
        except ToolTimeout as e:
            if attempt == max_attempts:
                return ToolResult(tool=name, status=ToolStatus.TIMEOUT, error=str(e),
                                  attempts=attempt, duration_ms=_ms(started))
    return ToolResult(tool=name, status=ToolStatus.ERROR, duration_ms=_ms(started))

# ---- read tools ------------------------------------------------------------ #
def get_vendor_record(vendor_id: str) -> ToolResult:
    def fn():
        vendor = _load("vendors.json").get(vendor_id)
        if vendor is None:
            raise ToolMissing(f"vendor {vendor_id} not found")
        return vendor
    return run_tool("get_vendor_record", fn)


def get_purchase_order(po_ref: str) -> ToolResult:
    def fn():
        if po_ref in TIMEOUT_PO_REFS:
            raise ToolTimeout(f"PO service timed out for {po_ref}")
        pos = _load("purchase_orders.json")
        if po_ref not in pos:
            raise ToolMissing(f"PO {po_ref} not found")
        return pos[po_ref]
    return run_tool("get_purchase_order", fn)


def check_invoice_history(vendor_id: str, invoice_ref: str, currency: str, amount: str) -> ToolResult:
    def fn():
        key = fingerprint(vendor_id, invoice_ref, currency, amount)
        matches = []
        for rec in _load("invoice_history.json"):
            if fingerprint(rec["vendor_id"], rec["invoice_ref"], rec["currency"], rec["amount"]) == key:
                matches.append({"ref": rec["invoice_ref"], "status": rec["status"], "match_type": "exact"})
        return matches
    return run_tool("check_invoice_history", fn)


def resolve_po_ref(invoice_ref: str) -> str | None:
    return _load("invoices.json").get(invoice_ref, {}).get("po_ref")


def fingerprint(vendor_id: str, invoice_ref: str, currency: str, amount: str) -> str:
    norm = re.sub(r"[^a-z0-9]", "", invoice_ref.lower())
    return f"{vendor_id}|{norm}|{currency.upper()}|{Decimal(str(amount))}"


# ---- consequential tool ---------------------------------------------------- #
def action_digest(case_id: str, outcome: str, facts: list, calcs: list) -> str:
    evidence = json.dumps({"facts": facts, "calcs": calcs}, sort_keys=True, default=str)
    ev = hashlib.sha256(evidence.encode()).hexdigest()[:16]
    return hashlib.sha256(f"{case_id}:{outcome}:{ev}".encode()).hexdigest()


def submit_decision(store, run_id: str, outcome: str, digest: str,
                    approved: bool, approver: str) -> ToolResult:
    started = time.perf_counter()
    if not approved:
        return ToolResult(tool="submit_decision", status=ToolStatus.ERROR,
                          error="deny-by-default: approval required", duration_ms=_ms(started))
    posting_ref = f"POST-{run_id[:8].upper()}"
    intended = {"posting_ref": posting_ref, "applied": True, "replayed": False, "approver": approver}
    created, stored = store.remember(digest, intended)      # unique key => idempotent
    if not created:
        return ToolResult(tool="submit_decision", status=ToolStatus.OK,
                          data={**stored, "replayed": True}, duration_ms=_ms(started))
    return ToolResult(tool="submit_decision", status=ToolStatus.OK, data=intended,
                      duration_ms=_ms(started))
