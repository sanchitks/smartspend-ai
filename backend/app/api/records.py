"""Categories and transactions (PRD TXN-01..07)."""
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, StringConstraints
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.errors import validation
from app.database import get_db
from app.models import Transaction, User
from app.schemas import (
    CategoryIn,
    CategoryOut,
    TransactionIn,
    TransactionOut,
    TransactionPage,
    TransactionUpdate,
)
from app.services import categories as category_service
from app.services import transactions as txn_service

router = APIRouter(tags=["records"])


def txn_out(user: User, t: Transaction) -> TransactionOut:
    out = TransactionOut.model_validate(t)
    out.is_future = txn_service.is_future(user, t)
    return out


# ---------------------------------------------------------------- categories


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(type: Literal["income", "expense"] | None = None, user: User = Depends(current_user),
                    db: Session = Depends(get_db)):
    return category_service.list_categories(db, user, type)


@router.post("/categories", response_model=CategoryOut, status_code=201)
def create_category(body: CategoryIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return category_service.create_category(db, user, body.name, body.type)


@router.delete("/categories/{category_id}", status_code=204)
def delete_category(category_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    category_service.delete_category(db, user, category_id)
    return Response(status_code=204)


# ---------------------------------------------------------------- transactions


class Filters:
    def __init__(
        self,
        start: date | None = None,
        end: date | None = None,
        type: Literal["income", "expense"] | None = None,
        category_id: int | None = Query(None, ge=1),
        q: Annotated[str | None, Query(max_length=100)] = None,
        min_amount: Annotated[Decimal | None, Query(ge=0, max_digits=14, decimal_places=2)] = None,
        max_amount: Annotated[Decimal | None, Query(ge=0, max_digits=14, decimal_places=2)] = None,
        sort: Literal["date_desc", "date_asc", "amount_desc", "amount_asc"] = "date_desc",
    ):
        if start and end and start > end:
            raise validation("The start date must be on or before the end date.", "start", "range")
        if min_amount is not None and max_amount is not None and min_amount > max_amount:
            raise validation("The minimum amount can't be more than the maximum.", "min_amount", "range")
        self.kwargs = {"start": start, "end": end, "kind": type, "category_id": category_id, "search": q,
                       "min_amount": min_amount, "max_amount": max_amount, "sort": sort}


@router.get("/transactions", response_model=TransactionPage)
def list_transactions(filters: Filters = Depends(), page: int = Query(1, ge=1, le=10_000),
                      page_size: int = Query(25, ge=1, le=100), user: User = Depends(current_user),
                      db: Session = Depends(get_db)):
    items, total = txn_service.page(db, user, page, page_size, **filters.kwargs)
    return TransactionPage(items=[txn_out(user, t) for t in items], total=total, page=page, page_size=page_size)


@router.post("/transactions", response_model=TransactionOut, status_code=201)
def create_transaction(body: TransactionIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return txn_out(user, txn_service.create(db, user, body))


@router.get("/transactions/export", response_class=Response)
def export_transactions(filters: Filters = Depends(), user: User = Depends(current_user),
                        db: Session = Depends(get_db)):
    csv_text = txn_service.export_csv(db, user, **filters.kwargs)
    return Response(csv_text, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="smartspend-transactions.csv"'})


class ImportIn(BaseModel):
    csv: Annotated[str, StringConstraints(min_length=1, max_length=900_000)]


@router.post("/transactions/import/preview")
def preview_import(body: ImportIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return txn_service.preview_import(db, user, body.csv)


@router.post("/transactions/import")
def commit_import(body: ImportIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return txn_service.commit_import(db, user, body.csv)


@router.get("/transactions/{txn_id}", response_model=TransactionOut)
def get_transaction(txn_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return txn_out(user, txn_service.get_owned(db, user, txn_id))


@router.patch("/transactions/{txn_id}", response_model=TransactionOut)
def update_transaction(txn_id: int, body: TransactionUpdate, user: User = Depends(current_user),
                       db: Session = Depends(get_db)):
    return txn_out(user, txn_service.update(db, user, txn_id, body))


@router.delete("/transactions/{txn_id}", status_code=204)
def delete_transaction(txn_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    txn_service.delete(db, user, txn_id)
    return Response(status_code=204)
