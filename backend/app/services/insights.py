"""Evidence-backed insights and savings ideas (PRD §6.6).

The observations and every number in them are calculated here. The AI may only re-word the summary and the
suggested action; its wording is checked against each item's evidence and dropped if a number doesn't match.
"""
import logging
import re
from collections import defaultdict
from datetime import datetime, timezone
from decimal import ROUND_DOWN, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import grounding
from app.ai.providers import AIOutputError, AIProvider, AIUnavailable
from app.core.money import CENT, format_money, percent
from app.core.periods import days_left_in_month, month_to_date, same_days_last_month
from app.models import Transaction, User
from app.services import aggregates, budgets as budget_service
from app.services.categories import DISCRETIONARY
from app.services.goals import list_goals

log = logging.getLogger("smartspend.ai")

MIN_DAYS_FOR_TRENDS = 7  # don't compare month-over-month in the first week: too little data
MIN_PREVIOUS_TXNS = 2
MAX_INSIGHTS = 4


def _insight(id_, kind, title, summary, evidence, action, impact=None, limitations=None, priority=5):
    return {"id": id_, "kind": kind, "title": title, "summary": summary, "evidence": evidence,
            "suggested_action": action, "estimated_impact": impact, "limitations": limitations or [],
            "priority": priority}


def generate(db: Session, user: User, today) -> list[dict]:
    m = lambda a: format_money(a, user.currency)  # noqa: E731
    out: list[dict] = []
    mtd = month_to_date(today)
    days_left = days_left_in_month(today)
    period_key = f"{today.year:04d}-{today.month:02d}"

    # 1. Category budgets that are close to or over their limit.
    summary = budget_service.summary(db, user, today.year, today.month)
    for p in summary["categories"]:
        if p.status not in ("approaching", "near_limit", "exceeded"):
            continue
        name = p.budget.category.name
        ev = {"period": period_key, "budget": str(p.amount), "spent": str(p.spent),
              "utilisation_percent": str(p.utilisation), "days_left": days_left}
        if p.status == "exceeded":
            over = -p.remaining
            out.append(_insight(
                f"budget-{p.budget.id}", "budget", f"{name} is over budget",
                f"You've spent {m(p.spent)} on {name} this month, {m(over)} more than the {m(p.amount)} you planned.",
                ev | {"over_by": str(over)},
                f"Look through this month's {name} transactions and decide whether to adjust the budget or hold off "
                f"on more {name} spending until next month.", priority=1))
        else:
            per_day = (p.remaining / days_left).quantize(CENT, rounding=ROUND_DOWN) if days_left else p.remaining
            out.append(_insight(
                f"budget-{p.budget.id}", "budget", f"{name} budget is at {p.utilisation}%",
                f"You've used {m(p.spent)} of your {m(p.amount)} {name} budget, with {days_left} days left.",
                ev | {"remaining": str(p.remaining), "per_day": str(per_day)},
                f"Keeping {name} to about {m(per_day)} a day would stay within the budget.",
                limitations=["Assumes spending is spread evenly over the rest of the month."], priority=2))

    # 2. A weekly cap from the total budget.
    total = summary["total"]
    if total and total.remaining > 0 and days_left >= 3:
        weeks = Decimal(days_left) / 7
        weekly = (total.remaining / weeks).quantize(CENT, rounding=ROUND_DOWN)
        out.append(_insight(
            "weekly-cap", "cap", "A weekly limit for the rest of the month",
            f"You have {m(total.remaining)} left in your monthly budget with {days_left} days to go.",
            {"period": period_key, "remaining": str(total.remaining), "days_left": days_left,
             "weekly_cap": str(weekly)},
            f"Aim for about {m(weekly)} a week until the month ends.",
            limitations=["Based on your total monthly budget; fixed bills still due are not separated out."],
            priority=3))

    # 3. Month-over-month increases, like-for-like and only with enough data.
    if today.day >= MIN_DAYS_FOR_TRENDS:
        prev = same_days_last_month(today)
        prev_rows = {r.category_id: r for r in aggregates.by_category(db, user.id, "expense", prev.start, prev.end)}
        cur_rows = aggregates.by_category(db, user.id, "expense", mtd.start, mtd.end)
        cur_total = sum((r.total for r in cur_rows), Decimal("0"))
        for r in cur_rows:
            before = prev_rows.get(r.category_id)
            if not before or before.count < MIN_PREVIOUS_TXNS or before.total <= 0:
                continue
            change = percent(r.total - before.total, before.total)
            meaningful = r.total - before.total >= cur_total * Decimal("0.05")
            if change is not None and change >= 20 and meaningful:
                out.append(_insight(
                    f"trend-{r.category_id}", "trend", f"{r.name} spending is up {change}%",
                    f"{r.name} is {m(r.total)} so far this month, compared with {m(before.total)} over the same "
                    f"days last month.",
                    {"period": period_key, "current_period_total": str(r.total),
                     "previous_period_total": str(before.total), "change_percent": str(change),
                     "compared_days": f"1-{today.day}"},
                    f"Check whether the extra {r.name} spending was planned, and set a {r.name} budget if it helps.",
                    limitations=["The current month is incomplete; compared with the same days of last month."],
                    priority=4))
                break  # one trend is enough for the panel

    # 4. Repeated discretionary purchases supported by the records.
    groups: dict[tuple, list[Transaction]] = defaultdict(list)
    for t in db.scalars(select(Transaction).where(
            Transaction.user_id == user.id, Transaction.type == "expense",
            Transaction.transaction_date >= mtd.start, Transaction.transaction_date <= mtd.end)).unique():
        if t.category.name in DISCRETIONARY:
            key = (t.category.name, re.sub(r"[^a-z]+", " ", t.description.lower()).strip())
            groups[key].append(t)
    repeats = sorted(((k, v) for k, v in groups.items() if len(v) >= 3 and k[1]),
                     key=lambda kv: -sum(t.amount for t in kv[1]))
    if repeats:
        (cat, _), items = repeats[0]
        spent = sum((t.amount for t in items), Decimal("0"))
        half = (spent / 2).quantize(CENT, rounding=ROUND_DOWN)
        label = items[0].description
        out.append(_insight(
            "repeat", "repeat", f"\"{label}\" came up {len(items)} times",
            f"You've recorded \"{label}\" {len(items)} times this month in {cat}, {m(spent)} in total.",
            {"period": period_key, "count": len(items), "total": str(spent), "category": cat, "half": str(half)},
            f"If you'd like to save here, doing this half as often would free up about {m(half)} a month.",
            impact=f"About {m(half)} a month",
            limitations=["Assumes next month looks like this one."], priority=5))

    # 5. Savings goals that have a date.
    for g in list_goals(db, user):
        if g["status"] == "active" and g["monthly_needed"]:
            out.append(_insight(
                f"goal-{g['id']}", "goal", f"\"{g['title']}\" needs {m(g['monthly_needed'])} a month",
                f"You've saved {m(g['current_amount'])} of {m(g['target_amount'])}. To reach it by "
                f"{g['target_date']:%d %b %Y}, set aside about {m(g['monthly_needed'])} a month.",
                {"target": str(g["target_amount"]), "saved": str(g["current_amount"]),
                 "monthly_needed": str(g["monthly_needed"]), "target_date": g["target_date"].isoformat()},
                f"Consider moving {m(g['monthly_needed'])} to savings at the start of each month.", priority=6))
            break

    # 6. Something neutral when there's data but nothing to flag.
    if not out:
        rows = aggregates.by_category(db, user.id, "expense", mtd.start, mtd.end)
        if rows:
            grand = sum((r.total for r in rows), Decimal("0"))
            top = rows[0]
            out.append(_insight(
                "top-category", "info", f"{top.name} is your largest expense",
                f"{top.name} accounts for {percent(top.total, grand)}% of this month's spending ({m(top.total)} of "
                f"{m(grand)}).",
                {"period": period_key, "category_total": str(top.total), "total": str(grand),
                 "share_percent": str(percent(top.total, grand))},
                f"A {top.name} budget would let you track it through the month.", priority=9))

    out.sort(key=lambda i: i["priority"])
    now = datetime.now(timezone.utc)
    for i in out:
        i["generated_at"] = now
        i.pop("priority")
    return out[:MAX_INSIGHTS]


def reword(insights: list[dict], provider: AIProvider, ctx: dict) -> tuple[list[dict], bool]:
    """Let the model improve wording, item by item. Returns (insights, degraded)."""
    if not provider.is_live or not insights:
        return insights, False
    try:
        texts = provider.explain_insights(insights, ctx) or []
    except (AIUnavailable, AIOutputError) as exc:
        log.warning("insight wording fell back to calculated text",
                    extra={"error_type": getattr(exc, "reason", type(exc).__name__)})
        return insights, True
    by_id = {t.id: t for t in texts}
    for item in insights:
        t = by_id.get(item["id"])
        if not t:
            continue
        sources = (item["evidence"], item["summary"], item["suggested_action"], item["title"])
        if grounding.check(t.summary, *sources)[0]:
            item["summary"] = t.summary
        if grounding.check(t.suggested_action, *sources)[0]:
            item["suggested_action"] = t.suggested_action
    return insights, False
