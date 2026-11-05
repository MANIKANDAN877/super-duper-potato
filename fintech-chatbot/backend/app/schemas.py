from datetime import datetime

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=2, max_length=500)


class ChartItem(BaseModel):
    label: str
    value: int
    color: str


class ChartData(BaseModel):
    title: str
    items: list[ChartItem]


class ChatResponse(BaseModel):
    question: str
    answer: str
    category: str
    source_url: str | None = None
    confidence: int = 0
    match_found: bool = True
    chart: ChartData | None = None


class PaymentRequest(BaseModel):
    amount: str | float = Field(..., description="Payment amount")
    currency: str = Field("USD", min_length=3, max_length=3)
    description: str | None = None


class PaymentOrderResponse(BaseModel):
    status: str
    order_id: str
    amount: str
    currency: str
    mode: str
    message: str
    approval_url: str | None = None


class PaymentCaptureRequest(BaseModel):
    order_id: str = Field(..., min_length=1)
    payer_id: str | None = None


class PaymentCaptureResponse(BaseModel):
    status: str
    order_id: str
    captured: bool
    message: str


class TransactionRecord(BaseModel):
    id: int
    account_id: int
    transaction_type: str
    amount: float
    description: str
    counterparty: str | None = None
    transaction_status: str = "normal"
    is_demo: bool = False
    source_type: str = "manual"
    source_reference: str | None = None
    occurred_at: datetime | str | None = None


class FraudAlertRecord(BaseModel):
    id: int
    account_id: int
    transaction_id: int | None = None
    alert_type: str
    severity: str = "medium"
    status: str = "new"
    message: str
    risk_score: int = 0
    created_at: datetime | str | None = None


class AccountSummary(BaseModel):
    id: int
    account_name: str
    account_number: str
    currency: str
    balance: float
    last_updated: datetime | str | None = None


class DashboardSummary(BaseModel):
    balance: float
    total_credits: float
    total_debits: float
    transactions_count: int
    alerts_count: int


class RiskAssessment(BaseModel):
    transaction_id: str | int
    account_id: int | None = None
    risk_score: int = 0
    risk_level: str = "LOW"
    review_status: str = "not_required"
    reasons: list[str] = Field(default_factory=list)
    analyzed_at: datetime | str | None = None


class FraudSummary(BaseModel):
    total_transactions: int = 0
    high_risk_transactions: int = 0
    medium_risk_transactions: int = 0
    suspicious_transactions: int = 0
    pending_reviews: int = 0
    risk_distribution: dict[str, int] = Field(default_factory=dict)
    risk_analysis: list[RiskAssessment] = Field(default_factory=list)


class DashboardResponse(BaseModel):
    account: AccountSummary
    summary: DashboardSummary
    transactions: list[TransactionRecord]
    alerts: list[FraudAlertRecord]
    fraud_summary: FraudSummary = Field(default_factory=FraudSummary)
    risk_analysis: list[RiskAssessment] = Field(default_factory=list)


class PayPalBalanceEntry(BaseModel):
    currency: str
    available_balance: float
    total_balance: float
    last_refresh_time: datetime | str | None = None
    is_primary: bool = False


class PayPalTransactionEntry(BaseModel):
    transaction_id: str
    transaction_date: datetime | str | None = None
    amount: float
    currency: str
    status: str
    direction: str = "credit"


class PayPalBalanceResponse(BaseModel):
    status: str
    balances: list[PayPalBalanceEntry]
    message: str
    reporting_delay_notice: str | None = None


class PayPalTransactionResponse(BaseModel):
    status: str
    transactions: list[PayPalTransactionEntry]
    message: str
    reporting_delay_notice: str | None = None
