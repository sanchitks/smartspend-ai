"""Default categories (PRD §6.3) plus a user's own custom categories."""
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, not_found, validation
from app.models import Budget, Category, Transaction, User

EXPENSE_DEFAULTS = [
    "Food & Dining", "Groceries", "Transportation", "Shopping", "Entertainment", "Healthcare", "Education",
    "Housing & Rent", "Utilities", "Travel", "Subscriptions", "Personal Care", "Other",
]
# Refunds are recorded as income in the "Refund" category; they are never netted against expenses.
INCOME_DEFAULTS = ["Salary", "Freelance", "Business", "Gift", "Refund", "Other"]

# Spending that is usually optional; used only to word suggestions, never to judge the user.
DISCRETIONARY = {"Food & Dining", "Shopping", "Entertainment", "Subscriptions", "Travel", "Personal Care"}

MAX_CUSTOM_CATEGORIES = 50


def seed_defaults(db: Session) -> None:
    existing = {(c.name, c.type) for c in db.scalars(select(Category).where(Category.user_id.is_(None)))}
    for kind, names in (("expense", EXPENSE_DEFAULTS), ("income", INCOME_DEFAULTS)):
        for name in names:
            if (name, kind) not in existing:
                db.add(Category(user_id=None, name=name, type=kind, is_default=True))
    db.commit()


def _visible(user: User):
    return or_(Category.user_id.is_(None), Category.user_id == user.id)


def list_categories(db: Session, user: User, kind: str | None = None) -> list[Category]:
    q = select(Category).where(_visible(user))
    if kind:
        q = q.where(Category.type == kind)
    rows = list(db.scalars(q))
    order = {n: i for i, n in enumerate(EXPENSE_DEFAULTS + INCOME_DEFAULTS)}
    # Defaults in the PRD order ("Other" last), then custom ones alphabetically.
    return sorted(rows, key=lambda c: (c.type, not c.is_default, order.get(c.name, 0) if c.is_default else 0, c.name.lower()))


def get_category(db: Session, user: User, category_id: int, kind: str | None = None) -> Category:
    cat = db.scalar(select(Category).where(Category.id == category_id, _visible(user)))
    if cat is None:
        raise validation("Choose a valid category.", "category_id", "unknown_category")
    if kind and cat.type != kind:
        raise validation(f"That category is for {cat.type}, not {kind}.", "category_id", "type_mismatch")
    return cat


def find_by_name(db: Session, user: User, name: str | None, kind: str | None) -> Category | None:
    if not name:
        return None
    q = select(Category).where(_visible(user), func.lower(Category.name) == name.strip().lower())
    if kind in ("income", "expense"):
        q = q.where(Category.type == kind)
    return db.scalars(q.order_by(Category.user_id.is_(None))).first()


def create_category(db: Session, user: User, name: str, kind: str) -> Category:
    if find_by_name(db, user, name, kind):
        raise AppError(409, "CONFLICT", "You already have a category with that name.")
    count = db.scalar(select(func.count()).select_from(Category).where(Category.user_id == user.id)) or 0
    if count >= MAX_CUSTOM_CATEGORIES:
        raise validation(f"You can have up to {MAX_CUSTOM_CATEGORIES} custom categories.")
    cat = Category(user_id=user.id, name=name, type=kind, is_default=False)
    db.add(cat)
    db.commit()
    return cat


def delete_category(db: Session, user: User, category_id: int) -> None:
    cat = db.scalar(select(Category).where(Category.id == category_id, Category.user_id == user.id))
    if cat is None:
        raise not_found("Category")
    used = db.scalar(select(func.count()).select_from(Transaction).where(Transaction.category_id == cat.id)) or 0
    if used:
        raise AppError(409, "CATEGORY_IN_USE", f"This category has {used} transaction(s). Move them to another category first.")
    db.query(Budget).filter(Budget.category_id == cat.id, Budget.user_id == user.id).delete()
    db.delete(cat)
    db.commit()
