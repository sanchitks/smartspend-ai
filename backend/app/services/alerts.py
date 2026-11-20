"""Budget threshold alerts (PRD §6.7).

Policy:
- Thresholds are 75% (approaching), 90% (near limit) and over 100% (exceeded); the first two are configurable.
- One alert per budget, per month, per threshold. A single big expense that jumps from 50% to 95% creates one
  alert (the highest threshold crossed), not two.
- Alerts are re-evaluated after any expense is created, edited or deleted. Alerts already sent are kept as
  history even if spending later drops below the threshold, and they are not sent again for that month.
"""
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.money import format_money
from app.models import Budget, Notification, User
from app.services import budgets as budget_service

EXCEEDED = 101  # sentinel for "over 100%"


def _levels() -> list[int]:
    return sorted(get_settings().alert_thresholds) + [EXCEEDED]


def crossed_level(spent, amount) -> int | None:
    """Highest threshold this spending has reached, or None."""
    if amount is None or amount <= 0:
        return None
    if spent > amount:
        return EXCEEDED
    util = spent / amount * 100
    reached = [t for t in _levels() if t != EXCEEDED and util >= t]
    return max(reached) if reached else None


def _key(budget: Budget, level: int) -> str:
    return f"budget:{budget.id}:{budget.year:04d}-{budget.month:02d}:{level}"


def evaluate_month(db: Session, user: User, year: int, month: int) -> list[Notification]:
    created = []
    for budget in budget_service.list_for_month(db, user, year, month):
        p = budget_service.progress(db, user, budget)
        level = crossed_level(p.spent, budget.amount)
        if level is None:
            continue
        prefix = f"budget:{budget.id}:{budget.year:04d}-{budget.month:02d}:"
        sent = {
            int(k.rsplit(":", 1)[1])
            for k in db.scalars(select(Notification.dedupe_key).where(
                Notification.user_id == user.id, Notification.dedupe_key.like(prefix + "%"),
            ))
        }
        if any(s >= level for s in sent):
            continue
        note = _build(user, budget, p, level)
        db.add(note)
        try:
            db.commit()
            created.append(note)
        except IntegrityError:  # another request created the same alert first
            db.rollback()
    return created


def _build(user: User, budget: Budget, p, level: int) -> Notification:
    name = budget.category.name if budget.category else "Total monthly"
    period = f"{budget.year:04d}-{budget.month:02d}"
    spent, amount = format_money(p.spent, user.currency), format_money(budget.amount, user.currency)
    if level == EXCEEDED:
        title = f"{name} budget exceeded"
        message = f"You've spent {spent} of your {amount} {name.lower()} budget, {format_money(-p.remaining, user.currency)} over."
        kind = "budget_exceeded"
    else:
        title = f"{name} budget at {p.utilisation}%"
        message = f"You've spent {spent} of {amount}. {format_money(p.remaining, user.currency)} left this month."
        kind = "budget_near_limit" if level >= max(get_settings().alert_thresholds) else "budget_approaching"
    return Notification(
        user_id=user.id, type=kind, title=title[:120], message=message[:500], dedupe_key=_key(budget, level),
        meta={
            "budget_id": budget.id, "category_id": budget.category_id, "category": name, "period": period,
            "threshold": level if level != EXCEEDED else 100, "exceeded": level == EXCEEDED,
            "spent": str(p.spent), "budget": str(budget.amount), "utilisation": str(p.utilisation),
        },
    )
