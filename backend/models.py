from enum import Enum
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class SignupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: str
    name: str
    email: str


# ---------------------------------------------------------------------------
# Reconciliation domain
# ---------------------------------------------------------------------------

class DiscrepancyCategory(str, Enum):
    MATCHED = "MATCHED"
    AMOUNT_MISMATCH = "AMOUNT_MISMATCH"
    MISSING_PAYMENT = "MISSING_PAYMENT"
    UNKNOWN_PAYMENT = "UNKNOWN_PAYMENT"
    DUPLICATE_ORDER = "DUPLICATE_ORDER"
    DUPLICATE_PAYMENT = "DUPLICATE_PAYMENT"
    CURRENCY_MISMATCH = "CURRENCY_MISMATCH"
    REFUND_CHARGE_ISSUE = "REFUND_CHARGE_ISSUE"
    ROUNDING_DIFFERENCE = "ROUNDING_DIFFERENCE"


class Priority(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NONE = "NONE"  # used for MATCHED rows


class DiscrepancyStatus(str, Enum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"


class DatasetUploadResponse(BaseModel):
    reconciliation_id: str
    orders_imported: int
    payments_imported: int


class DiscrepancySummaryItem(BaseModel):
    category: DiscrepancyCategory
    count: int
    financial_impact: float


class PriorityBreakdownItem(BaseModel):
    priority: Priority
    count: int


class ReconciliationSummary(BaseModel):
    reconciliation_id: str
    total_orders: int
    total_payments: int
    total_order_value: float
    total_payment_value: float
    matched_value: float
    disputed_value: float
    money_at_risk: float
    matched_count: int
    discrepancy_count: int
    discrepancies_by_type: list[DiscrepancySummaryItem]
    priority_breakdown: list[PriorityBreakdownItem]
    currency_breakdown: dict[str, int]


class DiscrepancyListItem(BaseModel):
    id: str
    order_id: Optional[str]
    payment_id: Optional[str]
    category: DiscrepancyCategory
    priority: Priority
    status: DiscrepancyStatus
    order_amount: Optional[float]
    payment_amount: Optional[float]
    difference: Optional[float]
    currency: Optional[str]
    reason: str


class DiscrepancyListResponse(BaseModel):
    items: list[DiscrepancyListItem]
    total: int
    page: int
    page_size: int


class DiscrepancyDetailResponse(BaseModel):
    id: str
    order: Optional[dict]
    payment: Optional[dict]
    category: DiscrepancyCategory
    priority: Priority
    status: DiscrepancyStatus
    difference: Optional[float]
    order_currency: Optional[str]
    payment_currency: Optional[str]
    reason: str
    financial_impact: float


# ---------------------------------------------------------------------------
# AI
# ---------------------------------------------------------------------------

class AIExplanation(BaseModel):
    what_happened: str
    likely_cause: str
    recommended_action: str
    is_fallback: bool = False


class AnalyzeRequest(BaseModel):
    discrepancy_ids: list[str] = Field(min_length=1, max_length=200)


class AIAnalysisResponse(BaseModel):
    selected_count: int
    total_financial_impact: float
    summary: str
    recommended_actions: list[str]
    is_fallback: bool = False
