"""Transaction CRUD (PRD §6.2). Ownership is checked on every read and write."""
import csv
import io
from datetime import date
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import not_found, validation
from app.core.money import MAX_AMOUNT, to_money
from app.core.periods import today_in
from app.models import Transaction, User
from app.schemas import TransactionIn, TransactionUpdate
from app.services import alerts
from app.services.categories import find_by_name, get_category

SORTS = {
    "date_desc": (Transaction.transaction_date.desc(), Transaction.id.desc()),
    "date_asc": (Transaction.transaction_date.asc(), Transaction.id.asc()),
    "amount_desc": (Transaction.amount.desc(), Transaction.id.desc()),
    "amount_asc": (Transaction.amount.asc(), Transaction.id.asc()),
}


def get_owned(db: Session, user: User, txn_id: int) -> Transaction:
    t = db.scalar(select(Transaction).where(Transaction.id == txn_id, Transaction.user_id == user.id))
    if t is None:
        raise not_found("Transaction")  # same answer whether it doesn't exist or belongs to someone else
    return t


def _months(*days: date) -> set[tuple[int, int]]:
    return {(d.year, d.month) for d in days if d}


def _reevaluate(db: Session, user: User, months: set[tuple[int, int]]) -> None:
    for y, m in sorted(months):
        alerts.evaluate_month(db, user, y, m)


def create(db: Session, user: User, data: TransactionIn) -> Transaction:
    get_category(db, user, data.category_id, data.type)
    t = Transaction(
        user_id=user.id, amount=data.amount, currency=user.currency, type=data.type, category_id=data.category_id,
        description=data.description, transaction_date=data.transaction_date, payment_method=data.payment_method,
        notes=data.notes or None, source=data.source,
    )
    db.add(t)
    db.commit()
    if t.type == "expense":
        _reevaluate(db, user, _months(t.transaction_date))
    return t


def update(db: Session, user: User, txn_id: int, data: TransactionUpdate) -> Transaction:
    t = get_owned(db, user, txn_id)
    old_date = t.transaction_date
    changes = data.model_dump(exclude_unset=True)
    for required in ("amount", "type", "category_id", "description", "transaction_date"):
        if required in changes and changes[required] is None:
            raise validation(f"{required.replace('_', ' ').capitalize()} can't be empty.", required, "required")
    new_type = changes.get("type", t.type)
    new_category = changes.get("category_id", t.category_id)
    if "type" in changes or "category_id" in changes:
        get_category(db, user, new_category, new_type)
    for field, value in changes.items():
        setattr(t, field, value)
    db.commit()
    _reevaluate(db, user, _months(old_date, t.transaction_date))
    return t


def delete(db: Session, user: User, txn_id: int) -> None:
    t = get_owned(db, user, txn_id)
    month = _months(t.transaction_date)
    db.delete(t)
    db.commit()
    _reevaluate(db, user, month)


def query(db: Session, user: User, *, start: date | None = None, end: date | None = None, kind: str | None = None,
          category_id: int | None = None, search: str | None = None, min_amount: Decimal | None = None,
          max_amount: Decimal | None = None, sort: str = "date_desc"):
    q = select(Transaction).where(Transaction.user_id == user.id)
    if start:
        q = q.where(Transaction.transaction_date >= start)
    if end:
        q = q.where(Transaction.transaction_date <= end)
    if kind:
        q = q.where(Transaction.type == kind)
    if category_id:
        q = q.where(Transaction.category_id == category_id)
    if min_amount is not None:
        q = q.where(Transaction.amount >= min_amount)
    if max_amount is not None:
        q = q.where(Transaction.amount <= max_amount)
    if search:
        like = f"%{search.strip().lower()[:100]}%"
        q = q.where(or_(func.lower(Transaction.description).like(like), func.lower(Transaction.notes).like(like)))
    return q.order_by(*SORTS.get(sort, SORTS["date_desc"]))


def page(db: Session, user: User, page_no: int, page_size: int, **filters):
    q = query(db, user, **filters)
    total = db.scalar(select(func.count()).select_from(q.order_by(None).subquery())) or 0
    items = list(db.scalars(q.offset((page_no - 1) * page_size).limit(page_size)).unique())
    return items, total


def is_future(user: User, t: Transaction) -> bool:
    return t.transaction_date > today_in(user.timezone)


# ---------------------------------------------------------------- CSV export / import

CSV_COLUMNS = ["date", "type", "category", "description", "amount", "currency", "payment_method", "notes"]
MAX_IMPORT_ROWS = 2000


def _safe_cell(value) -> str:
    """Stop spreadsheet formula injection: cells starting with = + - @ are prefixed with a quote."""
    s = "" if value is None else str(value)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def export_csv(db: Session, user: User, **filters) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_COLUMNS)
    for t in db.scalars(query(db, user, **filters)).unique():
        w.writerow([t.transaction_date.isoformat(), t.type, _safe_cell(t.category.name), _safe_cell(t.description),
                    str(t.amount), t.currency, t.payment_method or "", _safe_cell(t.notes)])
    return buf.getvalue()


def preview_import(db: Session, user: User, text: str) -> dict:
    """Validate every row; invalid rows are reported with a reason, never silently dropped."""
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    headers = {h.strip().lower() for h in (reader.fieldnames or [])}
    missing = {"date", "type", "category", "description", "amount"} - headers
    if missing:
        raise validation(f"The CSV is missing column(s): {', '.join(sorted(missing))}.", "file", "missing_columns")
    valid, invalid = [], []
    for line_no, raw in enumerate(reader, start=2):
        if line_no - 1 > MAX_IMPORT_ROWS:
            invalid.append({"line": line_no, "error": f"Only the first {MAX_IMPORT_ROWS} rows can be imported at once."})
            break
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
        try:
            valid.append({"line": line_no, **_parse_row(db, user, row)})
        except ValueError as exc:
            invalid.append({"line": line_no, "error": str(exc), "row": {k: row.get(k, "") for k in CSV_COLUMNS}})
    return {"valid": valid, "invalid": invalid}


def _parse_row(db: Session, user: User, row: dict) -> dict:
    kind = row.get("type", "").lower()
    if kind not in ("income", "expense"):
        raise ValueError("Type must be income or expense.")
    try:
        d = date.fromisoformat(row.get("date", ""))
    except ValueError:
        raise ValueError("Date must look like 2026-11-20.") from None
    try:
        amount = to_money(row.get("amount", "").lstrip("'"))
    except (ValueError, TypeError):
        raise ValueError("Amount is not a number.") from None
    if amount <= 0 or amount > MAX_AMOUNT:
        raise ValueError("Amount must be greater than zero.")
    currency = (row.get("currency") or user.currency).upper()
    if currency != user.currency:
        raise ValueError(f"Currency {currency} doesn't match your account currency ({user.currency}).")
    cat = find_by_name(db, user, row.get("category", "").lstrip("'"), kind)
    if cat is None:
        raise ValueError(f"Unknown {kind} category \"{row.get('category', '')}\".")
    desc = row.get("description", "").lstrip("'")[:200]
    if not desc:
        raise ValueError("Description is empty.")
    pm = row.get("payment_method") or None
    if pm and pm not in ("cash", "upi", "debit_card", "credit_card", "net_banking", "wallet", "other"):
        pm = "other"
    return {"transaction_date": d.isoformat(), "type": kind, "category_id": cat.id, "category": cat.name,
            "description": desc, "amount": str(amount), "payment_method": pm,
            "notes": (row.get("notes") or "").lstrip("'")[:1000] or None}


def commit_import(db: Session, user: User, text: str) -> dict:
    result = preview_import(db, user, text)
    months = set()
    for r in result["valid"]:
        d = date.fromisoformat(r["transaction_date"])
        db.add(Transaction(user_id=user.id, amount=Decimal(r["amount"]), currency=user.currency, type=r["type"],
                           category_id=r["category_id"], description=r["description"], transaction_date=d,
                           payment_method=r["payment_method"], notes=r["notes"], source="import"))
        if r["type"] == "expense":
            months.add((d.year, d.month))
    db.commit()
    _reevaluate(db, user, months)
    return {"imported": len(result["valid"]), "invalid": result["invalid"]}
