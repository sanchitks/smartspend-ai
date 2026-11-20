"""Monthly budgets and their progress (PRD §6.4 calculation rules)."""
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError, not_found
from app.core.money import percent, zero
from app.core.periods import month_period
from app.models import Budget, User
from app.services import aggregates
from app.services.categories import get_category


@dataclass
class Progress:
    budget: Budget | None
    amount: Decimal | None
    spent: Decimal
    remaining: Decimal | None  # negative = overspent
    utilisation: Decimal | None  # None when there is no budget (never divide by zero)
    status: str


def status_for(spent: Decimal, amount: Decimal | None) -> tuple[Decimal | None, str]:
    if amount is None or amount <= 0:
        return None, "no_budget"
    util = percent(spent, amount)  # rounded, for display only
    approaching, near = sorted(get_settings().alert_thresholds)[:2]
    # Compare exact amounts, not the rounded percentage (74.999% must not count as 75%).
    if spent > amount:
        return util, "exceeded"
    if spent * 100 >= amount * near:
        return util, "near_limit"
    if spent * 100 >= amount * approaching:
        return util, "approaching"
    return util, "healthy"


def progress(db: Session, user: User, budget: Budget) -> Progress:
    period = month_period(budget.year, budget.month)
    spent = aggregates.total(db, user.id, "expense", period.start, period.end, budget.category_id)
    util, status = status_for(spent, budget.amount)
    return Progress(budget, budget.amount, spent, budget.amount - spent, util, status)


def list_for_month(db: Session, user: User, year: int, month: int) -> list[Budget]:
    return list(db.scalars(select(Budget).where(Budget.user_id == user.id, Budget.year == year, Budget.month == month)))


def get_owned(db: Session, user: User, budget_id: int) -> Budget:
    b = db.scalar(select(Budget).where(Budget.id == budget_id, Budget.user_id == user.id))
    if b is None:
        raise not_found("Budget")
    return b


def create(db: Session, user: User, category_id: int | None, amount: Decimal, year: int, month: int) -> Budget:
    if category_id is not None:
        get_category(db, user, category_id, "expense")
    existing = db.scalar(
        select(Budget).where(
            Budget.user_id == user.id, Budget.year == year, Budget.month == month,
            Budget.category_id.is_(None) if category_id is None else Budget.category_id == category_id,
        )
    )
    if existing:
        what = "a total budget" if category_id is None else "a budget for this category"
        raise AppError(409, "BUDGET_EXISTS", f"You already have {what} this month. Edit it instead.",
                       [{"field": "id", "issue": "exists", "id": existing.id}])
    b = Budget(user_id=user.id, category_id=category_id, amount=amount, currency=user.currency, year=year, month=month)
    db.add(b)
    try:
        db.commit()
    except IntegrityError as exc:  # two requests raced past the check above
        db.rollback()
        raise AppError(409, "BUDGET_EXISTS", "That budget already exists. Edit it instead.") from exc
    return b


def copy_previous_month(db: Session, user: User, year: int, month: int, from_year: int, from_month: int) -> int:
    """Copy last month's budgets into an empty month. Returns how many were created."""
    if list_for_month(db, user, year, month):
        raise AppError(409, "BUDGET_EXISTS", "This month already has budgets.")
    created = 0
    for old in list_for_month(db, user, from_year, from_month):
        db.add(Budget(user_id=user.id, category_id=old.category_id, amount=old.amount,
                      currency=user.currency, year=year, month=month))
        created += 1
    db.commit()
    return created


def summary(db: Session, user: User, year: int, month: int) -> dict:
    period = month_period(year, month)
    budgets = list_for_month(db, user, year, month)
    total_budget = next((b for b in budgets if b.category_id is None), None)
    category_budgets = [b for b in budgets if b.category_id is not None]
    total_expenses = aggregates.total(db, user.id, "expense", period.start, period.end)
    covered = zero()
    rows = []
    for b in category_budgets:
        p = progress(db, user, b)
        covered += p.spent
        rows.append(p)
    order = {"exceeded": 0, "near_limit": 1, "approaching": 2, "healthy": 3}
    rows.sort(key=lambda p: (order.get(p.status, 9), -(p.utilisation or 0)))
    return {
        "total": progress(db, user, total_budget) if total_budget else None,
        "categories": rows,
        "total_expenses": total_expenses,
        "unbudgeted_expenses": total_expenses - covered,
    }
