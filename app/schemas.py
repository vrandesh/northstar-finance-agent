from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

# Utility Functions
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

# Enums
class Outcome(str, Enum):
    APPROVE_FOR_POSTING = "APPROVE_FOR_POSTING"
    HOLD_FOR_INFORMATION = "HOLD_FOR_INFORMATION"
    REJECT_DUPLICATE = "REJECT_DUPLICATE"
    REJECT_INVALID = "REJECT_INVALID"
    ESCALATE_CONTROL_REVIEW = "ESCALATE_CONTROL_REVIEW"

# Enums Schema for Exception Category    
class ExceptionCategory(str, Enum):
    MISSING_PO = "MISSING_PO"
    MISSING_RECEIPT = "MISSING_RECEIPT"
    PRICE_VARIANCE = "PRICE_VARIANCE"
    QUANTITY_VARIANCE = "QUANTITY_VARIANCE"
    DUPLICATE_RISK = "DUPLICATE_RISK"
    VENDOR_BLOCK = "VENDOR_BLOCK"
    BANK_CHANGE = "BANK_CHANGE"
    AUTHORITY_GAP = "AUTHORITY_GAP"
    SUSPECTED_INJECTION = "SUSPECTED_INJECTION"
    CONTROL_RISK = "CONTROL_RISK"
# Enums in Schema to check the tool status and output ----------------------------------- #
class ToolStatus(str, Enum):
    OK = "OK"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"
    NOT_FOUND = "NOT_FOUND"
    
# Schema required for Tool Outputs
class ToolResult(BaseModel):
    tool: str
    status: ToolStatus
    duration_ms: int
    attempts: int = 1
    data: Any | None = None
    error: str | None = None

class VendorRecord(BaseModel):
    vendor_id: str
    legal_name: str
    status: str
    risk_flags: list[str] = Field(default_factory=list)
    bank_last4: str
    bank_country: str
    created_at: str
    last_updated: str

class POLine(BaseModel):
    line_id: str
    quantity: Decimal
    line_total: Decimal

class Receipt(BaseModel):
    line_id: str
    received_quantity: Decimal

class PurchaseOrder(BaseModel):
    po_ref: str
    vendor_id: str
    currency: str
    approval_status: str
    total: Decimal
    lines: list[POLine]
    receipts: list[Receipt] = Field(default_factory=list)

class HistoryMatch(BaseModel):
    ref: str
    status: str                     # paid | posted | held | rejected
    match_type: str                 # exact | fuzzy


# ---- Case Request Schema --------------------------------------------------------------- #
class CaseRequest(BaseModel):
    case_id: str
    invoice_ref: str
    vendor_id: str
    amount: Decimal
    currency: str
    notes: str = ""
    attachment_doc_ids: list[str] = Field(default_factory=list)
    
    @field_validator("amount")
    def positive(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("Amount must be greater than zero/positive")
        return value
    
    @field_validator("currency")
    @classmethod
    def upper(cls, value: str ) -> str:
        if len(value) != 3:
            raise ValueError("Currency must be a 3-letter code")
        return value.upper()
    
# ---Policy Retrieval and Evaluation ----------------------------------------------------- #
class Citation(BaseModel):
    doc_id: str
    version: str
    section: str
    
class RetrievedChunk(BaseModel):
    doc_id: str
    version: str
    status: str                     # current | superseded | untrusted
    section: str
    text: str
    relevance: float
    trusted: bool                   # True only for current, verified policy
    citation: Citation

    
# Recommendation Parts ------------------------------------------------------------------- #
class Fact(BaseModel):
    statement: str
    citation: Citation

class PolicyFinding(BaseModel):
    rule_id: str
    citation: Citation
    detail: str
    result: Literal["pass", "fail", "not_applicable"]

class Calculation(BaseModel):
    name: str
    inputs: dict[str, str]
    formula: str
    result: str

class Inference(BaseModel):
    statement: str
    confidence: float = 0.0

class ExceptionItem(BaseModel):
    category: str
    failed_rule: str
    expected: str
    observed: str
    owner: str
    
class Action(BaseModel):
    tool: str
    idempotency_key: str
    posting_ref: str | None = None
    applied: bool = False
    replayed: bool = False
    at: str = Field(default_factory=now_iso)
class Recommendation(BaseModel):
    run_id: str
    case_id: str
    outcome: Outcome
    policy_findings: list[PolicyFinding] = Field(default_factory=list)
    calculations: list[Calculation] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    exceptions: list[ExceptionItem] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    required_approvals: list[str] = Field(default_factory=list)
    summary: str = ""
    required_role: str = ""
    confidence: float = 0.0
    sourced_facts: list[Fact] = Field(default_factory=list)
    inferences: list[Inference] = Field(default_factory=list)
    actions_taken: list[Action] = Field(default_factory=list)
    
    
# ---- llm + approval ------------------------------------------------------------------- #
class Explanation(BaseModel):
    summary: str
    key_points: list[str] = Field(default_factory=list)
    confidence: float = 0.5

class ApprovalRequest(BaseModel):
    run_id: str
    case_id: str
    amount: Decimal
    currency: str
    vendor_id: str
    required_role: str
    expected_version: int
    citations: list[Citation] = Field(default_factory=list)
    created_at: str = Field(default_factory=now_iso)


class ApprovalDecision(BaseModel):
    decision: Literal["approve", "reject"]
    approver: str
    approver_role: str
    expected_version: int
