"""Transactions, budgets, alerts and analytics (PRD §6.2-6.7, §15.3 critical test cases)."""
from datetime import timedelta

from app.core.periods import shift_month
from tests.conftest import add, category_id, register, today


def _budget(client, h, amount, category=None):
    t = today()
    r = client.post("/api/v1/budgets", headers=h, json={
        "category_id": category_id(client, h, category) if category else None,
        "amount": str(amount), "year": t.year, "month": t.month})
    assert r.status_code == 201, r.text
    return r.json()


def _summary(client, h):
    return client.get("/api/v1/budgets", headers=h).json()


def _food(summary):
    return next(b for b in summary["categories"] if b["category"]["name"] == "Food & Dining")


def _alerts(client, h):
    return client.get("/api/v1/notifications", headers=h).json()


# ---------------------------------------------------------------- transactions


def test_transaction_crud_and_validation(client):
    h = register(client)
    t = add(client, h, "450", description="Dinner at a restaurant")
    assert t["amount"] == "450.00" and t["currency"] == "INR" and t["category"]["name"] == "Food & Dining"
    r = client.patch(f"/api/v1/transactions/{t['id']}", headers=h, json={"amount": "300", "notes": "with friends"})
    assert r.json()["amount"] == "300.00" and r.json()["notes"] == "with friends"
    salary = category_id(client, h, "Salary", "income")
    r = client.patch(f"/api/v1/transactions/{t['id']}", headers=h, json={"category_id": salary})
    assert r.status_code == 422  # an expense can't use an income category
    assert client.patch(f"/api/v1/transactions/{t['id']}", headers=h, json={"amount": None}).status_code == 422
    assert client.delete(f"/api/v1/transactions/{t['id']}", headers=h).status_code == 204
    assert client.get(f"/api/v1/transactions/{t['id']}", headers=h).status_code == 404


def test_amount_rules(client):
    h = register(client)
    cid = category_id(client, h, "Groceries")
    base = {"type": "expense", "category_id": cid, "description": "x", "transaction_date": today().isoformat()}
    for bad in ("0", "-5", "1.999", "abc", "10000000000000"):
        assert client.post("/api/v1/transactions", headers=h, json={**base, "amount": bad}).status_code == 422, bad
    assert client.post("/api/v1/transactions", headers=h, json={**base, "amount": "0.01"}).status_code == 201


def test_future_dates_are_flagged(client):
    h = register(client)
    t = add(client, h, "100", when=today() + timedelta(days=3))
    assert t["is_future"] is True
    assert add(client, h, "100")["is_future"] is False


def test_list_filters_search_and_pagination(client):
    h = register(client)
    for i in range(30):
        add(client, h, 10 + i, description=f"Item {i}")
    add(client, h, "999", category="Transportation", description="Uber to airport")
    add(client, h, "50000", category="Salary", kind="income", description="November salary")
    page = client.get("/api/v1/transactions?page=2&page_size=10", headers=h).json()
    assert page["total"] == 32 and len(page["items"]) == 10 and page["page"] == 2
    assert client.get("/api/v1/transactions?q=airport", headers=h).json()["total"] == 1
    assert client.get("/api/v1/transactions?type=income", headers=h).json()["total"] == 1
    cid = category_id(client, h, "Transportation")
    assert client.get(f"/api/v1/transactions?category_id={cid}", headers=h).json()["total"] == 1
    r = client.get("/api/v1/transactions?min_amount=30&max_amount=35", headers=h).json()
    assert r["total"] == 6
    top = client.get("/api/v1/transactions?sort=amount_desc&page_size=1", headers=h).json()["items"][0]
    assert top["amount"] == "50000.00"
    assert client.get("/api/v1/transactions?page_size=500", headers=h).status_code == 422
    assert client.get("/api/v1/transactions?start=2026-02-01&end=2026-01-01", headers=h).status_code == 422


def test_csv_export_neutralises_formulas(client):
    h = register(client)
    add(client, h, "100", description="=HYPERLINK(\"http://evil\")")
    r = client.get("/api/v1/transactions/export", headers=h)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "'=HYPERLINK" in r.text and "\n=HYPERLINK" not in r.text


def test_csv_import_reports_invalid_rows(client):
    h = register(client)
    d = today().isoformat()
    csv_text = ("date,type,category,description,amount\n"
                f"{d},expense,Groceries,Vegetables,320\n"
                f"{d},expense,Nonsense,Thing,10\n"
                f"not-a-date,expense,Groceries,Milk,50\n"
                f"{d},expense,Groceries,Milk,-4\n"
                f"{d},income,Salary,Pay,50000\n")
    preview = client.post("/api/v1/transactions/import/preview", headers=h, json={"csv": csv_text}).json()
    assert len(preview["valid"]) == 2 and len(preview["invalid"]) == 3
    assert client.get("/api/v1/transactions", headers=h).json()["total"] == 0  # preview saves nothing
    done = client.post("/api/v1/transactions/import", headers=h, json={"csv": csv_text}).json()
    assert done["imported"] == 2 and len(done["invalid"]) == 3
    missing = client.post("/api/v1/transactions/import/preview", headers=h, json={"csv": "date,amount\n"})
    assert missing.status_code == 422


def test_custom_categories(client):
    h = register(client)
    r = client.post("/api/v1/categories", headers=h, json={"name": "Pets", "type": "expense"})
    assert r.status_code == 201 and r.json()["is_default"] is False
    assert client.post("/api/v1/categories", headers=h, json={"name": "pets", "type": "expense"}).status_code == 409
    other = register(client, "b@example.com")
    assert "Pets" not in [c["name"] for c in client.get("/api/v1/categories", headers=other).json()]
    add(client, h, "500", category="Pets")
    assert client.delete(f"/api/v1/categories/{r.json()['id']}", headers=h).status_code == 409


# ---------------------------------------------------------------- budgets (PRD §15.3)


def test_expense_updates_budget_and_aggregates(client):
    h = register(client)
    _budget(client, h, "5000", "Food & Dining")
    t = add(client, h, "450")
    food = _food(_summary(client, h))
    assert (food["spent"], food["remaining"], food["utilisation"]) == ("450.00", "4550.00", "9.0")
    # Editing ₹450 → ₹300 changes every aggregate by ₹150.
    client.patch(f"/api/v1/transactions/{t['id']}", headers=h, json={"amount": "300"})
    food = _food(_summary(client, h))
    assert (food["spent"], food["remaining"]) == ("300.00", "4700.00")
    assert client.get("/api/v1/analytics/overview", headers=h).json()["expenses"] == "300.00"
    # Deleting the only expense leaves zero, not a stale or negative amount.
    client.delete(f"/api/v1/transactions/{t['id']}", headers=h)
    food = _food(_summary(client, h))
    assert (food["spent"], food["remaining"], food["status"]) == ("0.00", "5000.00", "healthy")


def test_income_never_counts_against_budgets(client):
    h = register(client)
    _budget(client, h, "1000")
    add(client, h, "500", category="Refund", kind="income")
    assert _summary(client, h)["total"]["spent"] == "0.00"


def test_one_total_and_one_category_budget_per_month(client):
    h = register(client)
    _budget(client, h, "20000")
    t = today()
    dup = client.post("/api/v1/budgets", headers=h, json={"category_id": None, "amount": "1", "year": t.year,
                                                          "month": t.month})
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "BUDGET_EXISTS"
    _budget(client, h, "5000", "Food & Dining")
    dup = client.post("/api/v1/budgets", headers=h, json={
        "category_id": category_id(client, h, "Food & Dining"), "amount": "1", "year": t.year, "month": t.month})
    assert dup.status_code == 409
    salary = category_id(client, h, "Salary", "income")
    r = client.post("/api/v1/budgets", headers=h, json={"category_id": salary, "amount": "1", "year": t.year,
                                                        "month": t.month})
    assert r.status_code == 422


def test_budget_edit_recalculates_immediately(client):
    h = register(client)
    b = _budget(client, h, "1000", "Food & Dining")
    add(client, h, "900")
    assert _food(_summary(client, h))["status"] == "near_limit"
    r = client.patch(f"/api/v1/budgets/{b['id']}", headers=h, json={"amount": "2000"})
    assert r.json()["status"] == "healthy" and r.json()["remaining"] == "1100.00"


def test_alert_at_exactly_75_percent_is_created_once(client):
    h = register(client)
    _budget(client, h, "1000", "Food & Dining")
    add(client, h, "750")
    alerts = _alerts(client, h)
    assert len(alerts) == 1 and alerts[0]["meta"]["threshold"] == 75
    add(client, h, "10")  # 76%: still the same threshold, no duplicate
    client.get("/api/v1/budgets", headers=h)
    assert len(_alerts(client, h)) == 1


def test_big_jump_creates_only_the_highest_alert_then_exceeded(client):
    h = register(client)
    _budget(client, h, "1000", "Food & Dining")
    add(client, h, "950")
    alerts = _alerts(client, h)
    assert [a["meta"]["threshold"] for a in alerts] == [90]
    add(client, h, "100")
    alerts = _alerts(client, h)
    assert alerts[0]["type"] == "budget_exceeded" and alerts[0]["meta"]["exceeded"] is True
    assert len(alerts) == 2
    # Editing back below a threshold keeps history and doesn't re-send it.
    t = add(client, h, "1")
    client.delete(f"/api/v1/transactions/{t['id']}", headers=h)
    assert len(_alerts(client, h)) == 2


def test_notifications_mark_read(client):
    h = register(client)
    _budget(client, h, "100", "Food & Dining")
    add(client, h, "100")
    n = _alerts(client, h)[0]
    assert client.patch(f"/api/v1/notifications/{n['id']}/read", headers=h).json()["is_read"] is True
    assert client.get("/api/v1/notifications?unread_only=true", headers=h).json() == []
    other = register(client, "b@example.com")
    assert client.patch(f"/api/v1/notifications/{n['id']}/read", headers=other).status_code == 404


def test_copy_previous_month_budgets(client):
    h = register(client)
    t = today()
    py, pm = shift_month(t.year, t.month, -1)
    client.post("/api/v1/budgets", headers=h, json={"category_id": None, "amount": "30000", "year": py, "month": pm})
    r = client.post("/api/v1/budgets/copy-previous", headers=h, json={"year": t.year, "month": t.month})
    assert r.json() == {"created": 1}
    assert _summary(client, h)["total"]["amount"] == "30000.00"


# ---------------------------------------------------------------- analytics and goals


def test_dashboard_totals_match_records(client):
    h = register(client)
    add(client, h, "50000", category="Salary", kind="income")
    add(client, h, "450.50")
    add(client, h, "1200", category="Transportation")
    _budget(client, h, "20000")
    o = client.get("/api/v1/analytics/overview", headers=h).json()
    assert (o["income"], o["expenses"], o["net"]) == ("50000.00", "1650.50", "48349.50")
    assert o["budget_remaining"] == "18349.50" and o["budget_utilisation"] == "8.3"
    assert len(o["recent"]) == 3 and o["is_current_month"] is True
    cats = client.get("/api/v1/analytics/categories", headers=h).json()
    assert [(c["name"], c["total"]) for c in cats["items"]] == [("Transportation", "1200.00"),
                                                                ("Food & Dining", "450.50")]


def test_analytics_handles_empty_months(client):
    h = register(client)
    o = client.get("/api/v1/analytics/overview?year=2020&month=2", headers=h).json()
    assert o["expenses"] == "0.00" and o["budget"] is None and o["comparison"]["change_percent"] is None
    monthly = client.get("/api/v1/analytics/monthly?months=6", headers=h).json()["items"]
    assert len(monthly) == 6 and all(m["expenses"] == "0.00" for m in monthly)
    daily = client.get("/api/v1/analytics/daily?year=2024&month=2", headers=h).json()["items"]
    assert len(daily) == 29


def test_current_month_is_compared_like_for_like(client):
    h = register(client)
    t = today()
    py, pm = shift_month(t.year, t.month, -1)
    from datetime import date
    add(client, h, "100", when=date(py, pm, 1))      # inside the same-days window last month
    add(client, h, "9999", when=date(py, pm, 28) if t.day < 28 else date(py, pm, 1))
    o = client.get("/api/v1/analytics/overview", headers=h).json()
    expected = "100.00" if t.day < 28 else "10099.00"
    assert o["comparison"]["expenses"] == expected


def test_savings_goals(client):
    h = register(client)
    t = today()
    target = (t.replace(day=1) + timedelta(days=95)).isoformat()
    r = client.post("/api/v1/savings-goals", headers=h, json={"title": "Laptop", "target_amount": "60000",
                                                              "current_amount": "15000", "target_date": target})
    g = r.json()
    assert r.status_code == 201 and g["progress"] == "25.0" and g["remaining"] == "45000.00"
    assert g["monthly_needed"] is not None
    g = client.patch(f"/api/v1/savings-goals/{g['id']}", headers=h, json={"current_amount": "60000"}).json()
    assert g["status"] == "completed" and g["progress"] == "100.0"
    other = register(client, "b@example.com")
    assert client.delete(f"/api/v1/savings-goals/{g['id']}", headers=other).status_code == 404
