"""The single source of truth for money totals. Everything (dashboard, budgets, alerts, AI answers) calls these."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.money import zero
from app.models import Category, Transaction


def total(db: Session, user_id: int, kind: str, start: date, end: date, category_id: int | None = None) -> Decimal:
    q = select(func.coalesce(func.sum(Transaction.amount), 0)).where(
        Transaction.user_id == user_id,
        Transaction.type == kind,
        Transaction.transaction_date >= start,
        Transaction.transaction_date <= end,
    )
    if category_id is not None:
        q = q.where(Transaction.category_id == category_id)
    return db.scalar(q) or zero()


def count(db: Session, user_id: int, kind: str | None, start: date, end: date, category_id: int | None = None) -> int:
    q = select(func.count(Transaction.id)).where(
        Transaction.user_id == user_id, Transaction.transaction_date >= start, Transaction.transaction_date <= end
    )
    if kind:
        q = q.where(Transaction.type == kind)
    if category_id is not None:
        q = q.where(Transaction.category_id == category_id)
    return db.scalar(q) or 0


@dataclass
class CategoryTotal:
    category_id: int
    name: str
    total: Decimal
    count: int


def by_category(db: Session, user_id: int, kind: str, start: date, end: date) -> list[CategoryTotal]:
    """Totals per category, largest first (ties broken by name so results are stable)."""
    rows = db.execute(
        select(Category.id, Category.name, func.sum(Transaction.amount), func.count(Transaction.id))
        .join(Category, Category.id == Transaction.category_id)
        .where(
            Transaction.user_id == user_id,
            Transaction.type == kind,
            Transaction.transaction_date >= start,
            Transaction.transaction_date <= end,
        )
        .group_by(Category.id, Category.name)
    ).all()
    items = [CategoryTotal(r[0], r[1], r[2] or zero(), r[3]) for r in rows]
    return sorted(items, key=lambda c: (-c.total, c.name))


def first_transaction_date(db: Session, user_id: int) -> date | None:
    return db.scalar(select(func.min(Transaction.transaction_date)).where(Transaction.user_id == user_id))
