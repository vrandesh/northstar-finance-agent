from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

# Utility Functions
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

# Enums
class Outcome(StrEnum):
    APPROVE_FOR_POSTING = "APPROVE_FOR_POSTING"
    HOLD_FOR_INFORMATION = "HOLD_FOR_INFORMATION"
    REJECT_DUPLICATE = "REJECT_DUPLICATE"
    REJECT_INVALID = "REJECT_INVALID"
    ESCALATE_CONTROL_REVIEW = "ESCALATE_CONTROL_REVIEW"

# Enums Schema for Exception Category    
class ExceptionCategory(StrEnum):
    VALIDATION = "VALIDATION"
    BUSINESS_RULE = "BUSINESS_RULE"
    SYSTEM = "SYSTEM"
    MISSING_PO = "MISSION_PO"
    MISSING_RECEIPT = "MISSING_RECEIPT"
    DUPLICATE_RISK = "DUPLICATE_RISK"
    VENDOR_BLOCK = "VENDOR_BLOCK"
    OTHER = "OTHER"
# Enums in Schema to check the tool status and output ----------------------------------- #
class ToolStatus(StrEnum):
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
    def validate_amount(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("Amount must be greater than zero/positive")
        return value
    
    @field_validator("currency")
    @classmethod
    def validate_currency_uppercase(cls, value: str ) -> str:
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
    
    
# ---- llm + approval ------------------------------------------------------------------- #
class Explanation(BaseModel):
    summary: str
    key_points: list[str] = Field(default_factory=list)
    confidence: float = 0.5

class Action(BaseModel):
    tool: str
    idempotency_key: str
    posting_ref: str | None = None
    applied: bool = False
    replayed: bool = False
    at: str = Field(default_factory=now_iso)

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
