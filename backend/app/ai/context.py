"""The minimal context handed to the AI: dates, locale and category names. No names, emails or raw records."""
from sqlalchemy.orm import Session

from app.core.periods import today_in
from app.models import User
from app.services.categories import list_categories


def build_ctx(db: Session, user: User, locale: str = "en-IN", timezone: str | None = None) -> dict:
    tz = timezone or user.timezone
    today = today_in(tz)
    cats = list_categories(db, user)
    return {
        "today": today.isoformat(),
        "weekday": today.strftime("%A"),
        "timezone": tz,
        "locale": locale,
        "currency": user.currency,
        "expense_categories": [c.name for c in cats if c.type == "expense"],
        "income_categories": [c.name for c in cats if c.type == "income"],
        "categories": sorted({c.name for c in cats}),
    }
