"""Authentication, ownership and API hardening (PRD AUTH-01..05, §12.1, §15.2 security tests)."""
from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import get_settings
from tests.conftest import PASSWORD, add, register


def test_register_login_and_me(client):
    h = register(client, "Asha@Example.com")
    me = client.get("/api/v1/auth/me", headers=h).json()
    assert me["email"] == "asha@example.com" and me["currency"] == "INR" and "password_hash" not in me
    r = client.post("/api/v1/auth/login", json={"email": "ASHA@example.com", "password": PASSWORD})
    assert r.status_code == 200 and r.json()["access_token"]


def test_duplicate_email_rejected(client):
    register(client)
    r = client.post("/api/v1/auth/register", json={"name": "B", "email": "asha@example.com", "password": PASSWORD})
    assert r.status_code == 409 and r.json()["error"]["code"] == "EMAIL_TAKEN"


def test_login_errors_are_generic(client):
    register(client)
    wrong_pw = client.post("/api/v1/auth/login", json={"email": "asha@example.com", "password": "nope-nope-1"})
    no_user = client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "nope-nope-1"})
    assert wrong_pw.status_code == no_user.status_code == 401
    assert wrong_pw.json()["error"]["message"] == no_user.json()["error"]["message"]


def test_weak_password_rejected(client):
    r = client.post("/api/v1/auth/register", json={"name": "A", "email": "a@example.com", "password": "aaaaaaaa"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_protected_endpoints_require_auth(client):
    for path in ("/api/v1/auth/me", "/api/v1/transactions", "/api/v1/budgets", "/api/v1/analytics/overview",
                 "/api/v1/notifications", "/api/v1/savings-goals"):
        r = client.get(path)
        assert r.status_code == 401, path
        assert r.json()["error"]["code"] == "UNAUTHORIZED"


def test_logout_revokes_token(client):
    h = register(client)
    assert client.post("/api/v1/auth/logout", headers=h).status_code == 204
    r = client.get("/api/v1/auth/me", headers=h)
    assert r.status_code == 401 and r.json()["error"]["code"] == "SESSION_ENDED"


def test_expired_and_forged_tokens(client):
    h = register(client)
    token = h["Authorization"].split()[1]
    payload = jwt.decode(token, options={"verify_signature": False})
    s = get_settings()
    expired = jwt.encode({**payload, "exp": datetime.now(timezone.utc) - timedelta(minutes=1)}, s.jwt_secret_key,
                         algorithm="HS256")
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "TOKEN_EXPIRED"
    forged = jwt.encode(payload, "not-the-real-secret-but-long-enough-to-pass", algorithm="HS256")
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401
    unsigned = jwt.encode(payload, None, algorithm="none")
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {unsigned}"}).status_code == 401


def test_refresh_issues_new_token(client):
    h = register(client)
    r = client.post("/api/v1/auth/refresh", headers=h)
    assert r.status_code == 200
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"}).status_code == 200


def test_login_rate_limited(client):
    register(client)
    codes = [client.post("/api/v1/auth/login", json={"email": "asha@example.com", "password": "wrong-pass-1"}).status_code
             for _ in range(12)]
    assert codes[-1] == 429 and 401 in codes
    r = client.post("/api/v1/auth/login", json={"email": "asha@example.com", "password": "wrong-pass-1"})
    assert r.json()["error"]["code"] == "RATE_LIMITED" and "retry-after" in r.headers


def test_user_cannot_touch_another_users_transaction(client):
    a = register(client, "a@example.com")
    b = register(client, "b@example.com")
    txn = add(client, b, "450")
    tid = txn["id"]
    assert client.get(f"/api/v1/transactions/{tid}", headers=a).status_code == 404
    assert client.patch(f"/api/v1/transactions/{tid}", headers=a, json={"amount": "1"}).status_code == 404
    assert client.delete(f"/api/v1/transactions/{tid}", headers=a).status_code == 404
    assert client.get("/api/v1/transactions", headers=a).json()["total"] == 0
    # Still intact for its owner.
    assert client.get(f"/api/v1/transactions/{tid}", headers=b).json()["amount"] == "450.00"


def test_user_id_in_body_is_ignored(client):
    a = register(client, "a@example.com")
    b = register(client, "b@example.com")
    b_id = client.get("/api/v1/auth/me", headers=b).json()["id"]
    cats = client.get("/api/v1/categories?type=expense", headers=a).json()
    r = client.post("/api/v1/transactions", headers=a, json={
        "amount": "10", "type": "expense", "category_id": cats[0]["id"], "description": "x",
        "transaction_date": "2026-01-01", "user_id": b_id})
    assert r.status_code == 201
    assert client.get("/api/v1/transactions", headers=b).json()["total"] == 0


def test_security_headers_and_request_id(client):
    r = client.get("/api/v1/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["cache-control"] == "no-store"
    assert "default-src 'none'" in r.headers["content-security-policy"]
    assert len(r.headers["x-request-id"]) >= 16


def test_cors_only_allows_configured_origins(client):
    ok = client.options("/api/v1/auth/login", headers={"Origin": "http://localhost:5173",
                                                       "Access-Control-Request-Method": "POST"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    bad = client.options("/api/v1/auth/login", headers={"Origin": "https://evil.example",
                                                        "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in bad.headers


def test_oversized_request_rejected(client):
    r = client.post("/api/v1/auth/login", content=b"x" * 1_100_000, headers={"Content-Type": "application/json"})
    assert r.status_code == 413 and r.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_validation_errors_use_the_envelope(client):
    h = register(client)
    r = client.post("/api/v1/transactions", headers=h, json={"amount": "0", "type": "spend"})
    body = r.json()
    assert r.status_code == 422 and body["error"]["code"] == "VALIDATION_ERROR"
    assert {d["field"] for d in body["error"]["details"]} >= {"amount", "type"}
    assert "Traceback" not in r.text


def test_currency_locked_once_transactions_exist(client):
    h = register(client)
    assert client.patch("/api/v1/users/me", headers=h, json={"currency": "USD"}).json()["currency"] == "USD"
    client.patch("/api/v1/users/me", headers=h, json={"currency": "INR"})
    add(client, h, "100")
    r = client.patch("/api/v1/users/me", headers=h, json={"currency": "USD"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "CURRENCY_LOCKED"
    assert client.patch("/api/v1/users/me", headers=h, json={"timezone": "Mars/Base"}).status_code == 422


def test_delete_account_removes_everything(client):
    h = register(client)
    add(client, h, "100")
    assert client.request("DELETE", "/api/v1/users/me", headers=h, json={"password": "wrong-one-1"}).status_code == 403
    assert client.request("DELETE", "/api/v1/users/me", headers=h, json={"password": PASSWORD}).status_code == 204
    assert client.get("/api/v1/auth/me", headers=h).status_code == 401
    r = client.post("/api/v1/auth/login", json={"email": "asha@example.com", "password": PASSWORD})
    assert r.status_code == 401
