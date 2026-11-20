"""Dashboard metrics and analytics (PRD §6.5)."""
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.deps import current_user, default_month
from app.api.records import txn_out
from app.database import get_db
from app.models import User
from app.services import analytics

router = APIRouter(tags=["analytics"])

YearQ = Query(None, ge=2000, le=2100)
MonthQ = Query(None, ge=1, le=12)


def money_json(data) -> JSONResponse:
    """Money goes out as exact strings ("450.00"), never as JSON floats."""
    return JSONResponse(jsonable_encoder(data, custom_encoder={Decimal: str}))


@router.get("/analytics/overview")
def overview(year: int | None = YearQ, month: int | None = MonthQ, user: User = Depends(current_user),
             db: Session = Depends(get_db)):
    y, m = default_month(user, year, month)
    data = analytics.overview(db, user, y, m)
    data["recent"] = [txn_out(user, t) for t in data["recent"]]
    return money_json(data)


@router.get("/analytics/monthly")
def monthly(months: int = Query(6, ge=1, le=24), year: int | None = YearQ, month: int | None = MonthQ,
            user: User = Depends(current_user), db: Session = Depends(get_db)):
    y, m = default_month(user, year, month)
    return money_json({"currency": user.currency, "items": analytics.monthly(db, user, months, y, m)})


@router.get("/analytics/categories")
def categories(year: int | None = YearQ, month: int | None = MonthQ,
               type: Literal["income", "expense"] = "expense", user: User = Depends(current_user),
               db: Session = Depends(get_db)):
    y, m = default_month(user, year, month)
    return money_json({"currency": user.currency, **analytics.categories(db, user, y, m, type)})


@router.get("/analytics/daily")
def daily(year: int | None = YearQ, month: int | None = MonthQ, user: User = Depends(current_user),
          db: Session = Depends(get_db)):
    y, m = default_month(user, year, month)
    return money_json({"currency": user.currency, "year": y, "month": m, "items": analytics.daily(db, user, y, m)})
