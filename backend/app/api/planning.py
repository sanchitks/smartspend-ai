"""Budgets, savings goals and notifications."""
from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.deps import current_user, default_month
from app.core.errors import AppError, not_found
from app.core.periods import shift_month, today_in
from app.database import get_db
from app.models import Notification, SavingsGoal, User
from app.schemas import (
    BudgetIn,
    BudgetOut,
    BudgetSummary,
    BudgetUpdate,
    CategoryOut,
    GoalIn,
    GoalOut,
    GoalUpdate,
    NotificationOut,
)
from app.services import alerts
from app.services import budgets as budget_service
from app.services import goals as goal_service

router = APIRouter(tags=["planning"])


def budget_out(p: budget_service.Progress) -> BudgetOut:
    b = p.budget
    return BudgetOut(id=b.id, category=CategoryOut.model_validate(b.category) if b.category else None, amount=b.amount,
                     spent=p.spent, remaining=p.remaining, utilisation=p.utilisation, status=p.status, year=b.year,
                     month=b.month)


# ---------------------------------------------------------------- budgets


@router.get("/budgets", response_model=BudgetSummary)
def get_budgets(year: int | None = Query(None, ge=2000, le=2100), month: int | None = Query(None, ge=1, le=12),
                user: User = Depends(current_user), db: Session = Depends(get_db)):
    y, m = default_month(user, year, month)
    s = budget_service.summary(db, user, y, m)
    return BudgetSummary(year=y, month=m, currency=user.currency,
                         total=budget_out(s["total"]) if s["total"] else None,
                         categories=[budget_out(p) for p in s["categories"]],
                         total_expenses=s["total_expenses"], unbudgeted_expenses=s["unbudgeted_expenses"])


@router.post("/budgets", response_model=BudgetOut, status_code=201)
def create_budget(body: BudgetIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    b = budget_service.create(db, user, body.category_id, body.amount, body.year, body.month)
    alerts.evaluate_month(db, user, b.year, b.month)
    return budget_out(budget_service.progress(db, user, b))


class CopyIn(BaseModel):
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)


@router.post("/budgets/copy-previous")
def copy_previous(body: CopyIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    py, pm = shift_month(body.year, body.month, -1)
    created = budget_service.copy_previous_month(db, user, body.year, body.month, py, pm)
    if created == 0:
        raise AppError(404, "NOTHING_TO_COPY", "Last month has no budgets to copy.")
    alerts.evaluate_month(db, user, body.year, body.month)
    return {"created": created}


@router.patch("/budgets/{budget_id}", response_model=BudgetOut)
def update_budget(budget_id: int, body: BudgetUpdate, user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    b = budget_service.get_owned(db, user, budget_id)
    b.amount = body.amount
    db.commit()
    alerts.evaluate_month(db, user, b.year, b.month)
    return budget_out(budget_service.progress(db, user, b))


@router.delete("/budgets/{budget_id}", status_code=204)
def delete_budget(budget_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(budget_service.get_owned(db, user, budget_id))
    db.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------- savings goals


@router.get("/savings-goals", response_model=list[GoalOut])
def list_goals(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return goal_service.list_goals(db, user)


@router.post("/savings-goals", response_model=GoalOut, status_code=201)
def create_goal(body: GoalIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    count = len(db.scalars(select(SavingsGoal.id).where(SavingsGoal.user_id == user.id)).all())
    if count >= goal_service.MAX_GOALS:
        raise AppError(422, "VALIDATION_ERROR", f"You can have up to {goal_service.MAX_GOALS} savings goals.")
    g = SavingsGoal(user_id=user.id, **body.model_dump())
    goal_service.auto_complete(g)
    db.add(g)
    db.commit()
    return goal_service.enrich(g, today_in(user.timezone))


@router.patch("/savings-goals/{goal_id}", response_model=GoalOut)
def update_goal(goal_id: int, body: GoalUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    g = goal_service.get_owned(db, user, goal_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        if value is None and field != "target_date":
            continue
        setattr(g, field, value)
    if "status" not in body.model_fields_set:
        goal_service.auto_complete(g)
    db.commit()
    return goal_service.enrich(g, today_in(user.timezone))


@router.delete("/savings-goals/{goal_id}", status_code=204)
def delete_goal(goal_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(goal_service.get_owned(db, user, goal_id))
    db.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------- notifications


@router.get("/notifications", response_model=list[NotificationOut])
def list_notifications(unread_only: bool = False, limit: int = Query(50, ge=1, le=200),
                       user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        q = q.where(Notification.is_read.is_(False))
    return list(db.scalars(q.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit)))


@router.patch("/notifications/{notification_id}/read", response_model=NotificationOut)
def mark_read(notification_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    n = db.scalar(select(Notification).where(Notification.id == notification_id, Notification.user_id == user.id))
    if n is None:
        raise not_found("Notification")
    n.is_read = True
    db.commit()
    return n


@router.post("/notifications/read-all")
def mark_all_read(user: User = Depends(current_user), db: Session = Depends(get_db)):
    result = db.execute(update(Notification).where(Notification.user_id == user.id, Notification.is_read.is_(False))
                        .values(is_read=True))
    db.commit()
    return {"updated": result.rowcount}
