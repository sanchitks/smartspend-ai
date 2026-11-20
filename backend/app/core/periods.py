"""Date ranges. Budgets use calendar months; 'today' is always in the user's own timezone."""
import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True)
class Period:
    start: date  # inclusive
    end: date  # inclusive
    label: str

    def contains(self, d: date) -> bool:
        return self.start <= d <= self.end

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


def valid_timezone(name: str) -> bool:
    try:
        ZoneInfo(name)
        return True
    except (ZoneInfoNotFoundError, ValueError):
        return False


def today_in(tz_name: str) -> date:
    try:
        return datetime.now(ZoneInfo(tz_name)).date()
    except (ZoneInfoNotFoundError, ValueError):
        return datetime.now(timezone.utc).date()


def month_period(year: int, month: int) -> Period:
    last = calendar.monthrange(year, month)[1]
    start = date(year, month, 1)
    return Period(start, date(year, month, last), start.strftime("%B %Y"))


def shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def month_to_date(today: date) -> Period:
    full = month_period(today.year, today.month)
    return Period(full.start, today, f"{full.label} so far")


def same_days_last_month(today: date) -> Period:
    """The first N days of the previous month, where N is today's day of month (clamped)."""
    y, m = shift_month(today.year, today.month, -1)
    prev = month_period(y, m)
    end_day = min(today.day, prev.end.day)
    return Period(prev.start, date(y, m, end_day), f"{prev.label} (1–{end_day})")


def week_period(today: date, offset_weeks: int = 0) -> Period:
    start = today - timedelta(days=today.weekday()) + timedelta(weeks=offset_weeks)
    return Period(start, start + timedelta(days=6), "this week" if offset_weeks == 0 else "last week")


def days_left_in_month(today: date) -> int:
    """Days remaining including today."""
    return month_period(today.year, today.month).end.day - today.day + 1
