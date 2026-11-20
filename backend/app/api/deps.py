"""Shared dependencies: the signed-in user comes only from a verified token and a live session row."""
from datetime import datetime, timezone

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.periods import today_in
from app.core.security import decode_access_token
from app.database import get_db
from app.models import AuthSession, User


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def current_session(request: Request, db: Session = Depends(get_db)) -> tuple[User, AuthSession]:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AppError(401, "UNAUTHORIZED", "Please log in.", headers={"WWW-Authenticate": "Bearer"})
    payload = decode_access_token(token)
    session = db.get(AuthSession, payload["sid"])
    now = datetime.now(timezone.utc)
    if (session is None or session.revoked_at is not None or _aware(session.expires_at) <= now
            or str(session.user_id) != payload["sub"]):
        raise AppError(401, "SESSION_ENDED", "Your session has ended. Please log in again.")
    user = db.get(User, session.user_id)
    if user is None:
        raise AppError(401, "UNAUTHORIZED", "Please log in.")
    return user, session


def current_user(pair: tuple[User, AuthSession] = Depends(current_session)) -> User:
    return pair[0]


def default_month(user: User, year: int | None, month: int | None) -> tuple[int, int]:
    if year and month:
        return year, month
    today = today_in(user.timezone)
    return today.year, today.month
