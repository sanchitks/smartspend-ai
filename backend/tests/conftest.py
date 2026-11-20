import os
import tempfile
from pathlib import Path

# Configure before the app is imported: a throwaway database and the offline AI provider.
# TEST_DATABASE_URL runs the suite against a disposable PostgreSQL database instead (it is wiped on every test).
_tmp = Path(tempfile.mkdtemp(prefix="smartspend-tests-"))
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{(_tmp / 'test.db').as_posix()}"
os.environ["AI_PROVIDER"] = "mock"
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["LOG_LEVEL"] = "WARNING"
os.environ["APP_ENV"] = "test"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api import ai as ai_api  # noqa: E402
from app.api import auth as auth_api  # noqa: E402
from app.core.periods import today_in  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services.categories import seed_defaults  # noqa: E402

PASSWORD = "correct horse 1"


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_defaults(db)
    for limiter in (auth_api.LOGIN_BY_IP, auth_api.LOGIN_BY_EMAIL, auth_api.REGISTER_BY_IP, ai_api.AI_LIMIT):
        limiter.reset()
    with TestClient(app) as c:
        yield c


def register(client, email="asha@example.com", name="Asha") -> dict:
    r = client.post("/api/v1/auth/register", json={"name": name, "email": email, "password": PASSWORD})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def category_id(client, headers, name, kind="expense") -> int:
    cats = client.get(f"/api/v1/categories?type={kind}", headers=headers).json()
    return next(c["id"] for c in cats if c["name"] == name)


def add(client, headers, amount, category="Food & Dining", kind="expense", when=None, description="Test"):
    when = when or today()
    r = client.post("/api/v1/transactions", headers=headers, json={
        "amount": str(amount), "type": kind, "category_id": category_id(client, headers, category, kind),
        "description": description, "transaction_date": when.isoformat(),
    })
    assert r.status_code == 201, r.text
    return r.json()


def today():
    return today_in("Asia/Kolkata")
