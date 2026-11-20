"""The provider interface. The app talks to this, never to an SDK directly, so tests and demos can swap in a mock."""
from abc import ABC, abstractmethod
from typing import Literal

from pydantic import BaseModel, Field

INTENTS = (
    "expense_total", "income_total", "category_summary", "budget_status", "period_comparison",
    "savings_scenario", "goal_status", "general_budgeting", "add_transaction", "out_of_scope",
)
PERIODS = (
    "this_month", "last_month", "this_week", "last_week", "today", "yesterday", "last_n_days",
    "specific_month", "this_year", "unspecified", "ambiguous",
)
PAYMENT_METHODS = ("cash", "upi", "debit_card", "credit_card", "net_banking", "wallet", "other")


class AIUnavailable(Exception):
    """The provider couldn't be reached or refused service (timeout, rate limit, outage, bad key)."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class AIOutputError(Exception):
    """The provider answered, but the output was malformed, truncated, refused or failed validation."""


# ---- validated output contracts (PRD Appendix A) ----


class ExtractedTransaction(BaseModel):
    amount: str | None
    currency: str | None
    transaction_type: Literal["income", "expense", "unknown"]
    category: str | None
    description: str = Field(max_length=200)
    transaction_date: str | None
    payment_method: Literal["cash", "upi", "debit_card", "credit_card", "net_banking", "wallet", "other"] | None
    confidence: float = Field(ge=0, le=1)
    missing_fields: list[str]
    needs_clarification: bool
    clarification_question: str | None


class IntentResult(BaseModel):
    intent: Literal[INTENTS]  # type: ignore[valid-type]
    category: str | None
    period: Literal[PERIODS]  # type: ignore[valid-type]
    n_days: int | None = Field(default=None, ge=1, le=366)
    year: int | None = Field(default=None, ge=2000, le=2100)
    month: int | None = Field(default=None, ge=1, le=12)
    percent: float | None = Field(default=None, gt=0, le=100)
    confidence: float = Field(ge=0, le=1)


class TextAnswer(BaseModel):
    answer: str = Field(min_length=1, max_length=1500)


class InsightText(BaseModel):
    id: str
    summary: str = Field(max_length=400)
    suggested_action: str = Field(max_length=300)


class InsightTexts(BaseModel):
    items: list[InsightText]


class AIProvider(ABC):
    name: str = "base"
    model: str | None = None

    @property
    def is_live(self) -> bool:
        """True for a real language model, False for the offline demo provider."""
        return False

    @abstractmethod
    def extract_transaction(self, text: str, ctx: dict) -> ExtractedTransaction: ...

    @abstractmethod
    def classify_intent(self, message: str, ctx: dict) -> IntentResult: ...

    @abstractmethod
    def write_answer(self, question: str, intent: str, facts: dict, reference: str, ctx: dict) -> str | None:
        """Rephrase the calculated answer conversationally. None means: use the reference answer as is."""

    @abstractmethod
    def write_education(self, question: str, ctx: dict) -> str: ...

    @abstractmethod
    def explain_insights(self, insights: list[dict], ctx: dict) -> list[InsightText] | None:
        """Better wording for calculated insights. None means: keep the calculated wording."""
