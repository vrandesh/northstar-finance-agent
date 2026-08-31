from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

class Outcome(StrEnum):
    APPROVE_FOR_POSTING = "APPROVE_FOR_POSTING"
    HOLD_FOR_INFORMATION = "HOLD_FOR_INFORMATION"
    REJECT_DUPLICATE = "REJECT_DUPLICATE"
    REJECT_INVALID = "REJECT_INVALID"
    ESCALATE_CONTROL_REVIEW = "ESCALATE_CONTROL_REVIEW"

class ToolStatus(StrEnum):
    OK = "OK"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"
    NOT_FOUND = "NOT_FOUND"
    
class ToolResult(BaseModel):
    tool: str
    status: ToolStatus
    duration_ms: int
    attempts: int = 1
    data: Any | None = None
    error: str | None = None
    
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
    
class Citation(BaseModel):
    doc_id: str
    version: str
    section: str

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