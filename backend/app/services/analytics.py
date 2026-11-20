"""Dashboard and analytics figures (PRD §6.5). All values come from stored transactions."""
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.money import percent, zero
from app.core.periods import month_period, same_days_last_month, shift_month, today_in
from app.models import Budget, Notification, Transaction, User
from app.services import aggregates


def overview(db: Session, user: User, year: int, month: int) -> dict:
    period = month_period(year, month)
    today = today_in(user.timezone)
    is_current = period.contains(today)
    income = aggregates.total(db, user.id, "income", period.start, period.end)
    expenses = aggregates.total(db, user.id, "expense", period.start, period.end)

    total_budget = db.scalar(select(Budget).where(
        Budget.user_id == user.id, Budget.year == year, Budget.month == month, Budget.category_id.is_(None)))

    py, pm = shift_month(year, month, -1)
    prev = month_period(py, pm)
    if is_current:
        # Like-for-like: this month so far vs the same days of last month.
        cmp_period = same_days_last_month(today)
        cmp_expenses = aggregates.total(db, user.id, "expense", cmp_period.start, cmp_period.end)
        cmp_note = f"Compared with {cmp_period.label}, because this month isn't over yet."
    else:
        cmp_period = prev
        cmp_expenses = aggregates.total(db, user.id, "expense", prev.start, prev.end)
        cmp_note = f"Compared with all of {prev.label}."

    recent = list(db.scalars(
        select(Transaction).where(Transaction.user_id == user.id)
        .order_by(Transaction.transaction_date.desc(), Transaction.id.desc()).limit(6)
    ).unique())
    unread = db.scalar(select(func.count(Notification.id)).where(
        Notification.user_id == user.id, Notification.is_read.is_(False))) or 0
    return {
        "year": year, "month": month, "label": period.label, "currency": user.currency,
        "is_current_month": is_current,
        "days_elapsed": (today - period.start).days + 1 if is_current else period.days,
        "days_in_month": period.days,
        "income": income, "expenses": expenses, "net": income - expenses,
        "budget": total_budget.amount if total_budget else None,
        "budget_remaining": (total_budget.amount - expenses) if total_budget else None,
        "budget_utilisation": percent(expenses, total_budget.amount) if total_budget else None,
        "comparison": {
            "label": cmp_period.label, "expenses": cmp_expenses,
            "change": expenses - cmp_expenses, "change_percent": percent(expenses - cmp_expenses, cmp_expenses),
            "note": cmp_note,
        },
        "transaction_count": aggregates.count(db, user.id, None, period.start, period.end),
        "recent": recent,
        "unread_notifications": unread,
        "has_any_transactions": aggregates.first_transaction_date(db, user.id) is not None,
    }


def monthly(db: Session, user: User, months: int, end_year: int, end_month: int) -> list[dict]:
    out = []
    for back in range(months - 1, -1, -1):
        y, m = shift_month(end_year, end_month, -back)
        p = month_period(y, m)
        income = aggregates.total(db, user.id, "income", p.start, p.end)
        expenses = aggregates.total(db, user.id, "expense", p.start, p.end)
        out.append({"year": y, "month": m, "label": p.start.strftime("%b %Y"),
                    "income": income, "expenses": expenses, "net": income - expenses})
    return out


def categories(db: Session, user: User, year: int, month: int, kind: str) -> dict:
    p = month_period(year, month)
    py, pm = shift_month(year, month, -1)
    prev = month_period(py, pm)
    rows = aggregates.by_category(db, user.id, kind, p.start, p.end)
    prev_rows = {r.category_id: r.total for r in aggregates.by_category(db, user.id, kind, prev.start, prev.end)}
    grand = sum((r.total for r in rows), zero())
    return {
        "year": year, "month": month, "type": kind, "total": grand,
        "items": [{"category_id": r.category_id, "name": r.name, "total": r.total, "count": r.count,
                   "share": percent(r.total, grand), "previous_total": prev_rows.get(r.category_id, zero())}
                  for r in rows],
    }


def daily(db: Session, user: User, year: int, month: int) -> list[dict]:
    p = month_period(year, month)
    rows = dict(db.execute(
        select(Transaction.transaction_date, func.sum(Transaction.amount))
        .where(Transaction.user_id == user.id, Transaction.type == "expense",
               Transaction.transaction_date >= p.start, Transaction.transaction_date <= p.end)
        .group_by(Transaction.transaction_date)
    ).all())
    out, running, d = [], zero(), p.start
    while d <= p.end:
        spent = rows.get(d) or zero()
        running += spent
        out.append({"date": d.isoformat(), "day": d.day, "expenses": spent, "cumulative": running})
        d += timedelta(days=1)
    return out


def month_has_data(db: Session, user: User, d: date) -> bool:
    p = month_period(d.year, d.month)
    return aggregates.count(db, user.id, None, p.start, p.end) > 0
