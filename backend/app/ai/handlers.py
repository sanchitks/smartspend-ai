"""Deterministic retrieval and calculation for each assistant intent.

Each handler reads only the signed-in user's data (user_id comes from the server-side session) and returns:
- facts: labelled, formatted values shown next to the answer and given to the model,
- reference: a correct plain-language answer built from those facts (used whenever the AI text is rejected),
- links: where to see the supporting transactions.
"""
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.money import CENT, format_money, percent, zero
from app.core.periods import (
    Period,
    days_left_in_month,
    month_period,
    month_to_date,
    same_days_last_month,
    shift_month,
    week_period,
)
from app.models import Budget, SavingsGoal, User
from app.services import aggregates, budgets as budget_service
from app.services.categories import find_by_name
from app.services.goals import enrich


@dataclass
class Result:
    facts: dict
    reference: str
    links: list[dict] = field(default_factory=list)
    kind: str = "answer"


def resolve_period(kind: str, today: date, n_days: int | None = None, year: int | None = None,
                   month: int | None = None) -> Period | None:
    """Turn an intent's period word into exact dates. None means it's too vague and we must ask."""
    if kind == "ambiguous":
        return None
    if kind in ("unspecified", "this_month"):
        return month_to_date(today)
    if kind == "last_month":
        y, m = shift_month(today.year, today.month, -1)
        return month_period(y, m)
    if kind == "this_week":
        p = week_period(today)
        return Period(p.start, min(p.end, today), "this week")
    if kind == "last_week":
        return week_period(today, -1)
    if kind == "today":
        return Period(today, today, "today")
    if kind == "yesterday":
        d = today - timedelta(days=1)
        return Period(d, d, "yesterday")
    if kind == "last_n_days":
        n = max(1, min(n_days or 30, 366))
        return Period(today - timedelta(days=n - 1), today, f"the last {n} days")
    if kind == "this_year":
        return Period(date(today.year, 1, 1), today, f"{today.year} so far")
    if kind == "specific_month" and year and month:
        if (year, month) == (today.year, today.month):
            return month_to_date(today)
        return month_period(year, month)
    return month_to_date(today)


def describe(p: Period) -> str:
    """Readable period with exact dates, e.g. 'November 2026 so far (1–20 Nov)'."""
    def short(d: date) -> str:
        return f"{d.day} {d.strftime('%b')}"

    if p.label.endswith(")") and "(" in p.label:  # part of a month, e.g. the same days of last month
        return f"{p.label.split(' (')[0]} ({short(p.start)}–{short(p.end)})"
    if p.start == p.end:
        return f"{p.label} ({short(p.start)})"
    if p.start.day == 1 and p.end == month_period(p.start.year, p.start.month).end:
        return p.label
    return f"{p.label} ({short(p.start)}–{short(p.end)} {p.end.year})"


def _link(label: str, start: date, end: date, kind: str | None = None, category_id: int | None = None) -> dict:
    q = {"start": start.isoformat(), "end": end.isoformat()}
    if kind:
        q["type"] = kind
    if category_id:
        q["category_id"] = str(category_id)
    return {"label": label, "to": "/app/transactions?" + urlencode(q)}


def _incomplete(p: Period, today: date) -> bool:
    return p.end >= today and not (p.start == p.end)


class Handlers:
    def __init__(self, db: Session, user: User, today: date):
        self.db, self.user, self.today = db, user, today
        self.cur = user.currency

    def m(self, amount: Decimal) -> str:
        return format_money(amount, self.cur)

    def _cat(self, name: str | None, kind: str):
        return find_by_name(self.db, self.user, name, kind) if name else None

    # ------------------------------------------------------------ totals

    def total(self, kind: str, p: Period, category: str | None) -> Result:
        cat = self._cat(category, kind)
        if category and cat is None:
            other = "income" if kind == "expense" else "expense"
            if self._cat(category, other):
                kind, cat = other, self._cat(category, other)
        amount = aggregates.total(self.db, self.user.id, kind, p.start, p.end, cat.id if cat else None)
        count = aggregates.count(self.db, self.user.id, kind, p.start, p.end, cat.id if cat else None)
        when = describe(p)
        verb = "spent" if kind == "expense" else "received"
        on = f" on {cat.name}" if cat and kind == "expense" else f" as {cat.name}" if cat else ""
        label = ("Spent" if kind == "expense" else "Received") + (f" on {cat.name}" if cat else "")
        facts = {"period": when, "items": [{"label": label, "value": self.m(amount)},
                                           {"label": "Transactions", "value": str(count)}], "notes": []}
        if count == 0:
            what = f"{cat.name} {'expenses' if kind == 'expense' else 'income'}" if cat else (
                "expenses" if kind == "expense" else "income")
            reference = f"You haven't recorded any {what} for {when}."
        else:
            reference = f"You {verb} {self.m(amount)}{on} in {when}, across {count} transaction{'s' if count != 1 else ''}."
        if _incomplete(p, self.today):
            facts["notes"].append("This period isn't over yet.")
        return Result(facts, reference, [_link("View these transactions", p.start, p.end, kind, cat.id if cat else None)])

    # ------------------------------------------------------------ categories

    def category_summary(self, p: Period) -> Result:
        rows = aggregates.by_category(self.db, self.user.id, "expense", p.start, p.end)
        grand = sum((r.total for r in rows), zero())
        when = describe(p)
        if not rows:
            return Result({"period": when, "items": [], "notes": []},
                          f"You haven't recorded any expenses for {when}.",
                          [_link("Add or view transactions", p.start, p.end, "expense")])
        top = rows[:3]
        items = [{"label": r.name, "value": f"{self.m(r.total)} ({percent(r.total, grand)}%)"} for r in top]
        items.append({"label": "Total spent", "value": self.m(grand)})
        first = top[0]
        reference = (f"In {when}, your biggest spending category was {first.name} at {self.m(first.total)}, "
                     f"{percent(first.total, grand)}% of the {self.m(grand)} you spent.")
        if len(top) > 1:
            rest = " and ".join(f"{r.name} ({self.m(r.total)})" for r in top[1:])
            reference += f" Next were {rest}."
        return Result({"period": when, "items": items, "notes": []}, reference,
                      [_link("View expenses", p.start, p.end, "expense")])

    # ------------------------------------------------------------ budgets

    def budget_status(self, p: Period, category: str | None) -> Result:
        y, mo = p.end.year, p.end.month
        month = month_period(y, mo)
        is_current = month.contains(self.today)
        cat = self._cat(category, "expense")
        q = select(Budget).where(Budget.user_id == self.user.id, Budget.year == y, Budget.month == mo)
        q = q.where(Budget.category_id == cat.id) if cat else q.where(Budget.category_id.is_(None))
        budget = self.db.scalar(q)
        name = f"{cat.name} budget" if cat else "total monthly budget"
        link = [{"label": "Open budgets", "to": f"/app/budgets?year={y}&month={mo}"}]
        if budget is None:
            spent = aggregates.total(self.db, self.user.id, "expense", month.start, month.end, cat.id if cat else None)
            return Result(
                {"period": month.label, "items": [{"label": "Spent", "value": self.m(spent)}],
                 "notes": [f"No {name} is set for {month.label}."]},
                f"You haven't set a {name} for {month.label}, so there's nothing to compare against. "
                f"You've spent {self.m(spent)}{' on ' + cat.name if cat else ''} that month.",
                link)
        prog = budget_service.progress(self.db, self.user, budget)
        days_left = days_left_in_month(self.today) if is_current else 0
        items = [
            {"label": "Budget", "value": self.m(budget.amount)},
            {"label": "Spent", "value": self.m(prog.spent)},
            {"label": "Remaining" if prog.remaining >= 0 else "Over budget by",
             "value": self.m(abs(prog.remaining))},
            {"label": "Used", "value": f"{prog.utilisation}%"},
        ]
        status_words = {"healthy": "on track", "approaching": "approaching the limit",
                        "near_limit": "near the limit", "exceeded": "over the limit"}[prog.status]
        if prog.remaining >= 0:
            reference = (f"Your {name} for {month.label} is {self.m(budget.amount)}. You've used "
                         f"{self.m(prog.spent)} ({prog.utilisation}%), so {self.m(prog.remaining)} is left")
            reference += f" with {days_left} day{'s' if days_left != 1 else ''} to go." if is_current else "."
        else:
            reference = (f"Your {name} for {month.label} is {self.m(budget.amount)}, and you've spent "
                         f"{self.m(prog.spent)}, which is {self.m(-prog.remaining)} over.")
        reference += f" Status: {status_words}."
        if is_current:
            items.append({"label": "Days left", "value": str(days_left)})
        return Result({"period": month.label, "items": items, "notes": []}, reference, link + [
            _link("View the spending", month.start, month.end, "expense", cat.id if cat else None)])

    # ------------------------------------------------------------ comparison

    def comparison(self, kind_word: str, p: Period, category: str | None) -> Result:
        cat = self._cat(category, "expense")
        cid = cat.id if cat else None
        if kind_word in ("unspecified", "this_month") or (p.start.day == 1 and p.end == self.today
                                                          and p.start.month == self.today.month):
            cur, prev = month_to_date(self.today), same_days_last_month(self.today)
            note = "This month isn't over yet, so it's compared with the same days of last month."
        elif kind_word in ("this_week", "last_week", "last_n_days", "today", "yesterday", "this_year"):
            length = (p.end - p.start).days + 1
            cur = p
            prev = Period(p.start - timedelta(days=length), p.start - timedelta(days=1), "the period before")
            note = "Compared with the same number of days just before." if _incomplete(p, self.today) else ""
        else:  # a whole month
            cur = p
            y, mo = shift_month(p.start.year, p.start.month, -1)
            prev = month_period(y, mo)
            note = ""
        a = aggregates.total(self.db, self.user.id, "expense", cur.start, cur.end, cid)
        b = aggregates.total(self.db, self.user.id, "expense", prev.start, prev.end, cid)
        diff = a - b
        pct = percent(abs(diff), b)
        what = f" on {cat.name}" if cat else ""
        items = [{"label": describe(cur), "value": self.m(a)}, {"label": describe(prev), "value": self.m(b)},
                 {"label": "Difference", "value": ("+" if diff > 0 else "−" if diff < 0 else "") + self.m(abs(diff))}]
        if pct is not None:
            items.append({"label": "Change", "value": f"{pct}%"})
        if diff == 0:
            change = "exactly the same"
        else:
            direction = "more" if diff > 0 else "less"
            change = f"{self.m(abs(diff))} {direction}" + (f" ({pct}%)" if pct is not None else "")
        reference = (f"You spent {self.m(a)}{what} in {describe(cur)}, compared with {self.m(b)} in "
                     f"{describe(prev)}: {change}.")
        if note:
            reference += " " + note
        return Result({"period": f"{describe(cur)} vs {describe(prev)}", "items": items,
                       "notes": [note] if note else []}, reference,
                      [_link("View this period", cur.start, cur.end, "expense", cid)])

    # ------------------------------------------------------------ scenario

    def scenario(self, pct: float, category: str | None) -> Result:
        y, mo = shift_month(self.today.year, self.today.month, -1)
        base = month_period(y, mo)  # last full month is the baseline
        cat = self._cat(category, "expense")
        baseline = aggregates.total(self.db, self.user.id, "expense", base.start, base.end, cat.id if cat else None)
        rate = Decimal(str(pct))
        monthly = (baseline * rate / 100).quantize(CENT, rounding=ROUND_HALF_UP)
        yearly = monthly * 12
        what = cat.name if cat else "total spending"
        pct_text = f"{rate.normalize():f}"
        facts = {"period": f"Baseline: {base.label}", "items": [
            {"label": f"{what} in {base.label}", "value": self.m(baseline)},
            {"label": "Cut", "value": f"{pct_text}%"},
            {"label": "Estimated saving per month", "value": self.m(monthly)},
            {"label": "Over 12 months", "value": self.m(yearly)},
        ], "notes": ["Hypothetical estimate, assuming your spending stays at last month's level."]}
        if baseline == 0:
            reference = (f"You didn't record any {what} in {base.label}, so there's no baseline to estimate a "
                         f"{pct_text}% cut from yet.")
        else:
            reference = (f"Hypothetical estimate: in {base.label} you spent {self.m(baseline)} on {what}. Cutting "
                         f"that by {pct_text}% would save about {self.m(monthly)} a month, or {self.m(yearly)} over "
                         f"12 months, if the rest of your spending stays the same.")
        return Result(facts, reference, [_link("View the baseline month", base.start, base.end, "expense",
                                               cat.id if cat else None)])

    # ------------------------------------------------------------ goals

    def goals(self) -> Result:
        rows = [enrich(g, self.today) for g in self.db.scalars(
            select(SavingsGoal).where(SavingsGoal.user_id == self.user.id, SavingsGoal.status == "active"))]
        link = [{"label": "Open savings goals", "to": "/app/goals"}]
        if not rows:
            return Result({"period": None, "items": [], "notes": []},
                          "You don't have any active savings goals yet. You can add one on the Savings Goals page.",
                          link)
        items, parts = [], []
        for g in rows[:5]:
            items.append({"label": g["title"], "value": f"{self.m(g['current_amount'])} of "
                                                         f"{self.m(g['target_amount'])} ({g['progress']}%)"})
            part = f"{g['title']} is at {self.m(g['current_amount'])} of {self.m(g['target_amount'])} ({g['progress']}%)"
            if g["monthly_needed"]:
                part += f", needing about {self.m(g['monthly_needed'])} a month to reach it by {g['target_date']:%d %b %Y}"
                items.append({"label": f"{g['title']}: needed per month", "value": self.m(g["monthly_needed"])})
            parts.append(part)
        return Result({"period": None, "items": items, "notes": []}, ". ".join(parts) + ".", link)
