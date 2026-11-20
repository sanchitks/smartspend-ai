"""Unit tests: money maths, periods, budget status rules and alert thresholds."""
from datetime import date
from decimal import Decimal

import pytest

from app.ai import grounding
from app.ai.handlers import resolve_period
from app.core.money import format_money, percent, to_money
from app.core.periods import month_period, same_days_last_month, shift_month
from app.services.alerts import EXCEEDED, crossed_level
from app.services.budgets import status_for

D = Decimal


def test_money_is_exact_decimal():
    assert to_money("0.1") + to_money("0.2") == D("0.30")
    assert to_money("1,234.5") == D("1234.50")
    assert to_money(450) == D("450.00")
    with pytest.raises(TypeError):
        to_money(0.1)
    with pytest.raises(ValueError):
        to_money("abc")


def test_percent_never_divides_by_zero():
    assert percent(D("50"), D("0")) is None
    assert percent(D("75"), D("100")) == D("75.0")


def test_indian_currency_format():
    assert format_money(D("123456.50"), "INR") == "₹1,23,456.50"
    assert format_money(D("450.00"), "INR") == "₹450"
    assert format_money(D("1234567"), "USD") == "$1,234,567"
    assert format_money(D("-300"), "INR") == "-₹300"


@pytest.mark.parametrize("spent,budget,status", [
    ("0", "1000", "healthy"), ("749.99", "1000", "healthy"), ("750", "1000", "approaching"),
    ("900", "1000", "near_limit"), ("1000", "1000", "near_limit"), ("1000.01", "1000", "exceeded"),
])
def test_budget_status_thresholds(spent, budget, status):
    assert status_for(D(spent), D(budget))[1] == status


def test_no_budget_status():
    assert status_for(D("10"), None) == (None, "no_budget")


def test_alert_levels():
    assert crossed_level(D("749"), D("1000")) is None
    assert crossed_level(D("750"), D("1000")) == 75  # exactly 75%
    assert crossed_level(D("950"), D("1000")) == 90  # jumps straight past 75%
    assert crossed_level(D("1001"), D("1000")) == EXCEEDED


def test_month_periods():
    p = month_period(2024, 2)
    assert (p.start, p.end) == (date(2024, 2, 1), date(2024, 2, 29))
    assert shift_month(2026, 1, -1) == (2025, 12)
    # Like-for-like comparison clamps to the shorter month.
    lfl = same_days_last_month(date(2026, 3, 31))
    assert (lfl.start, lfl.end) == (date(2026, 2, 1), date(2026, 2, 28))


def test_resolve_period():
    today = date(2026, 11, 20)
    assert resolve_period("ambiguous", today) is None
    p = resolve_period("unspecified", today)
    assert (p.start, p.end) == (date(2026, 11, 1), today)
    p = resolve_period("specific_month", today, year=2026, month=9)
    assert (p.start, p.end) == (date(2026, 9, 1), date(2026, 9, 30))
    p = resolve_period("last_n_days", today, n_days=7)
    assert (p.start, p.end) == (date(2026, 11, 14), today)


def test_grounding_accepts_only_calculated_numbers():
    facts = {"items": [{"label": "Spent", "value": "₹1,23,456.50"}, {"label": "Used", "value": "75.0%"}]}
    assert grounding.check("You spent ₹1,23,456.50, which is 75% of your budget.", facts)[0]
    ok, reason = grounding.check("You spent ₹1,23,999 this month.", facts)
    assert not ok and reason == "ungrounded_numbers"
    assert grounding.check("This is guaranteed to save you money.", facts) == (False, "unsafe_advice")
