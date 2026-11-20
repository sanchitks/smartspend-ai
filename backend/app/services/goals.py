"""Savings goals (PRD BUD-06). Tracking only: no investment features."""
from datetime import date
from decimal import ROUND_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import not_found
from app.core.money import CENT, percent, zero
from app.core.periods import today_in
from app.models import SavingsGoal, User

MAX_GOALS = 30


def months_until(today: date, target: date) -> int:
    """Months left including the current one; at least 1."""
    return max(1, (target.year - today.year) * 12 + (target.month - today.month) + 1)


def enrich(goal: SavingsGoal, today: date) -> dict:
    remaining = max(goal.target_amount - goal.current_amount, zero())
    monthly_needed = None
    if goal.target_date and remaining > 0 and goal.status == "active" and goal.target_date >= today:
        monthly_needed = (remaining / months_until(today, goal.target_date)).quantize(CENT, rounding=ROUND_UP)
    return {
        "id": goal.id, "title": goal.title, "target_amount": goal.target_amount, "current_amount": goal.current_amount,
        "target_date": goal.target_date, "status": goal.status, "created_at": goal.created_at,
        "progress": min(percent(goal.current_amount, goal.target_amount) or Decimal("0"), Decimal("100")),
        "remaining": remaining, "monthly_needed": monthly_needed,
    }


def list_goals(db: Session, user: User) -> list[dict]:
    today = today_in(user.timezone)
    goals = db.scalars(select(SavingsGoal).where(SavingsGoal.user_id == user.id).order_by(SavingsGoal.created_at))
    return [enrich(g, today) for g in goals]


def get_owned(db: Session, user: User, goal_id: int) -> SavingsGoal:
    g = db.scalar(select(SavingsGoal).where(SavingsGoal.id == goal_id, SavingsGoal.user_id == user.id))
    if g is None:
        raise not_found("Savings goal")
    return g


def auto_complete(goal: SavingsGoal) -> None:
    if goal.status == "active" and goal.current_amount >= goal.target_amount:
        goal.status = "completed"
