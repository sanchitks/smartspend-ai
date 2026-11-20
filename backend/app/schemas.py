"""Pydantic request/response schemas. Money is a Decimal on the way in and a "450.00" string on the way out."""
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator

from app.core.money import CURRENCIES, MAX_AMOUNT, to_money
from app.core.periods import valid_timezone

Amount = Annotated[Decimal, Field(gt=0, le=MAX_AMOUNT, max_digits=14, decimal_places=2), AfterValidator(to_money)]
NonNegativeAmount = Annotated[Decimal, Field(ge=0, le=MAX_AMOUNT, max_digits=14, decimal_places=2),
                              AfterValidator(to_money)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
TxnType = Literal["income", "expense"]
PaymentMethod = Literal["cash", "upi", "debit_card", "credit_card", "net_banking", "wallet", "other"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- auth & profile


class RegisterIn(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    email: EmailStr
    password: Annotated[str, StringConstraints(min_length=8, max_length=128)]

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.lower()

    @field_validator("password")
    @classmethod
    def _strength(cls, v: str) -> str:
        if v.strip() != v or len(set(v)) < 4:
            raise ValueError("Choose a stronger password: at least 8 characters, not just repeats.")
        return v


class LoginIn(BaseModel):
    email: EmailStr
    password: Annotated[str, StringConstraints(min_length=1, max_length=128)]

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.lower()


class UserOut(ORM):
    id: int
    name: str
    email: str
    currency: str
    timezone: str
    monthly_income: Decimal | None
    onboarded: bool
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime
    user: UserOut


class ProfileUpdate(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)] | None = None
    currency: str | None = None
    timezone: str | None = None
    monthly_income: NonNegativeAmount | None = None
    onboarded: bool | None = None

    @field_validator("currency")
    @classmethod
    def _currency(cls, v: str | None) -> str | None:
        if v is not None and v.upper() not in CURRENCIES:
            raise ValueError(f"Currency must be one of {', '.join(CURRENCIES)}.")
        return v.upper() if v else v

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str | None) -> str | None:
        if v is not None and not valid_timezone(v):
            raise ValueError("Unknown timezone.")
        return v


class DeleteAccountIn(BaseModel):
    password: Annotated[str, StringConstraints(min_length=1, max_length=128)]


# ---------------------------------------------------------------- categories


class CategoryOut(ORM):
    id: int
    name: str
    type: TxnType
    is_default: bool


class CategoryIn(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
    type: TxnType


# ---------------------------------------------------------------- transactions


class TransactionIn(BaseModel):
    amount: Amount
    type: TxnType
    category_id: int
    description: ShortText
    transaction_date: date
    payment_method: PaymentMethod | None = None
    notes: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] | None = None
    source: Literal["manual", "ai"] = "manual"


class TransactionUpdate(BaseModel):
    amount: Amount | None = None
    type: TxnType | None = None
    category_id: int | None = None
    description: ShortText | None = None
    transaction_date: date | None = None
    payment_method: PaymentMethod | None = None
    notes: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] | None = None


class TransactionOut(ORM):
    id: int
    amount: Decimal
    currency: str
    type: TxnType
    category: CategoryOut
    description: str
    transaction_date: date
    payment_method: str | None
    notes: str | None
    source: str
    is_future: bool = False
    created_at: datetime
    updated_at: datetime


class TransactionPage(BaseModel):
    items: list[TransactionOut]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------- budgets & goals

BudgetStatus = Literal["healthy", "approaching", "near_limit", "exceeded", "no_budget"]


class BudgetIn(BaseModel):
    category_id: int | None = None  # None = total monthly budget
    amount: Amount
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)


class BudgetUpdate(BaseModel):
    amount: Amount


class BudgetOut(BaseModel):
    id: int
    category: CategoryOut | None
    amount: Decimal
    spent: Decimal
    remaining: Decimal
    utilisation: Decimal | None
    status: BudgetStatus
    year: int
    month: int


class BudgetSummary(BaseModel):
    year: int
    month: int
    currency: str
    total: BudgetOut | None
    categories: list[BudgetOut]
    total_expenses: Decimal
    unbudgeted_expenses: Decimal  # spending in categories that have no category budget


class GoalIn(BaseModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    target_amount: Amount
    current_amount: NonNegativeAmount = Decimal("0")
    target_date: date | None = None


class GoalUpdate(BaseModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)] | None = None
    target_amount: Amount | None = None
    current_amount: NonNegativeAmount | None = None
    target_date: date | None = None
    status: Literal["active", "completed", "archived"] | None = None


class GoalOut(ORM):
    id: int
    title: str
    target_amount: Decimal
    current_amount: Decimal
    target_date: date | None
    status: str
    progress: Decimal = Decimal("0")
    remaining: Decimal = Decimal("0")
    monthly_needed: Decimal | None = None  # to reach the target by its date, from this month on
    created_at: datetime


# ---------------------------------------------------------------- notifications


class NotificationOut(ORM):
    id: int
    type: str
    title: str
    message: str
    meta: dict
    is_read: bool
    created_at: datetime


# ---------------------------------------------------------------- AI


class ParseIn(BaseModel):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
    locale: Annotated[str, StringConstraints(max_length=16)] = "en-IN"
    timezone: str | None = None


class Draft(BaseModel):
    amount: Decimal | None
    currency: str
    transaction_type: Literal["income", "expense", "unknown"]
    category: str | None
    category_id: int | None
    description: str
    transaction_date: date | None
    payment_method: PaymentMethod | None


class ParseOut(BaseModel):
    draft: Draft
    confidence: float
    requires_confirmation: Literal[True] = True
    missing_fields: list[str]
    needs_clarification: bool
    clarification_question: str | None
    provider: str


class ChatIn(BaseModel):
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
    conversation_id: int | None = None


class ChatPeriod(BaseModel):
    start: date
    end: date
    label: str


class ChatOut(BaseModel):
    conversation_id: int
    message_id: int
    answer: str
    intent: str
    period: ChatPeriod | None
    facts: dict  # calculated by the application, shown next to the answer
    kind: Literal["answer", "clarification", "boundary", "draft", "education"]
    draft: ParseOut | None = None
    links: list[dict] = []
    provider: str
    grounded: bool  # true when every number in the answer came from the calculated facts


class ConversationOut(ORM):
    id: int
    title: str
    created_at: datetime
    updated_at: datetime


class ChatMessageOut(ORM):
    id: int
    role: str
    content: str
    meta: dict
    created_at: datetime


class InsightOut(BaseModel):
    id: str
    title: str
    summary: str
    evidence: dict
    suggested_action: str
    estimated_impact: str | None
    limitations: list[str]
    kind: str
    generated_at: datetime


class InsightsOut(BaseModel):
    insights: list[InsightOut]
    provider: str
    disclaimer: str
