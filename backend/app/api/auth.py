"""Registration, login, token refresh, logout and profile (PRD AUTH-01..05)."""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import _aware, current_session, current_user
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import (
    RateLimiter,
    client_ip,
    create_access_token,
    enforce,
    hash_password,
    needs_rehash,
    verify_password,
)
from app.database import get_db
from app.models import AuthSession, Budget, Transaction, User
from app.schemas import DeleteAccountIn, LoginIn, ProfileUpdate, RegisterIn, TokenOut, UserOut

router = APIRouter(tags=["auth"])
_s = get_settings()
LOGIN_BY_IP = RateLimiter(_s.login_attempts_per_15_min, 15 * 60)
LOGIN_BY_EMAIL = RateLimiter(_s.login_attempts_per_15_min, 15 * 60)
REGISTER_BY_IP = RateLimiter(_s.registrations_per_hour, 60 * 60)
BAD_LOGIN = "Email or password is incorrect."


def _start_session(db: Session, user: User) -> TokenOut:
    s = get_settings()
    session = AuthSession(id=str(uuid.uuid4()), user_id=user.id,
                          expires_at=datetime.now(timezone.utc) + timedelta(days=s.session_max_days))
    db.add(session)
    db.commit()
    token, expires = create_access_token(user.id, session.id)
    return TokenOut(access_token=token, expires_at=expires, user=UserOut.model_validate(user))


@router.post("/auth/register", response_model=TokenOut, status_code=201)
def register(body: RegisterIn, request: Request, db: Session = Depends(get_db)):
    enforce(REGISTER_BY_IP, client_ip(request), "Too many sign-ups from this network. Please try again later.")
    if db.scalar(select(User.id).where(User.email == body.email)):
        raise AppError(409, "EMAIL_TAKEN", "An account with this email already exists. Try logging in.")
    user = User(name=body.name, email=body.email, password_hash=hash_password(body.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(409, "EMAIL_TAKEN", "An account with this email already exists. Try logging in.") from exc
    return _start_session(db, user)


@router.post("/auth/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    enforce(LOGIN_BY_IP, client_ip(request), "Too many login attempts. Please wait a few minutes.")
    enforce(LOGIN_BY_EMAIL, body.email, "Too many login attempts for this account. Please wait a few minutes.")
    user = db.scalar(select(User).where(User.email == body.email))
    if not verify_password(body.password, user.password_hash if user else None):
        raise AppError(401, "INVALID_CREDENTIALS", BAD_LOGIN)
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
    LOGIN_BY_EMAIL.reset(body.email)
    # Tidy up this user's old sessions.
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id,
                                         AuthSession.expires_at < datetime.now(timezone.utc)))
    return _start_session(db, user)


@router.post("/auth/refresh", response_model=TokenOut)
def refresh(pair=Depends(current_session)):
    """Swap a still-valid token for a fresh one. The session's absolute expiry still applies."""
    user, session = pair
    token, expires = create_access_token(user.id, session.id)
    expires = min(expires, _aware(session.expires_at))
    return TokenOut(access_token=token, expires_at=expires, user=UserOut.model_validate(user))


@router.post("/auth/logout", status_code=204)
def logout(pair=Depends(current_session), db: Session = Depends(get_db)):
    _, session = pair
    session.revoked_at = datetime.now(timezone.utc)
    db.commit()
    return Response(status_code=204)


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user


@router.patch("/users/me", response_model=UserOut)
def update_profile(body: ProfileUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    changes = body.model_dump(exclude_unset=True)
    if "currency" in changes and changes["currency"] and changes["currency"] != user.currency:
        has_records = db.scalar(select(func.count(Transaction.id)).where(Transaction.user_id == user.id))
        if has_records:
            raise AppError(409, "CURRENCY_LOCKED",
                           "Currency can't be changed after you've added transactions, because amounts in different "
                           "currencies can't be added together.")
    for field, value in changes.items():
        if value is not None or field == "monthly_income":
            setattr(user, field, value)
    db.commit()
    return user


@router.delete("/users/me", status_code=204)
def delete_account(body: DeleteAccountIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Permanently delete the account and every record that belongs to it."""
    if not verify_password(body.password, user.password_hash):
        raise AppError(403, "INVALID_CREDENTIALS", "That password is incorrect.")
    # Transactions first (they reference categories), then the user; the rest cascades from the user row.
    db.execute(delete(Transaction).where(Transaction.user_id == user.id))
    db.execute(delete(Budget).where(Budget.user_id == user.id))
    db.execute(delete(User).where(User.id == user.id))
    db.commit()
    return Response(status_code=204)
