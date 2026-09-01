"""End-to-end API tests for authentication and per-user data isolation.

These hit a real MongoDB (a local `mongod` must be running) using a
dedicated `reconcile_test` database so they never touch dev data. This is
a deliberate simplification for a take-home: no mocking layer, just a real
Mongo the same way the app uses it in production.
"""

import os

os.environ["DATABASE_NAME"] = "reconcile_test"
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("JWT_SECRET", "test-secret")

import pytest
from fastapi.testclient import TestClient

from database import get_db
from main import app

client = TestClient(app)

COLLECTIONS = ["users", "datasets", "orders", "payments", "reconciliations"]


@pytest.fixture(autouse=True)
def clean_db():
    db = get_db()
    for name in COLLECTIONS:
        db[name].delete_many({})
    yield
    for name in COLLECTIONS:
        db[name].delete_many({})


def _signup(email: str) -> str:
    r = client.post("/auth/signup", json={"name": "Test", "email": email, "password": "password123"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_signup_login_and_me_round_trip():
    token = _signup("roundtrip@example.com")
    login = client.post("/auth/login", json={"email": "roundtrip@example.com", "password": "password123"})
    assert login.status_code == 200
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "roundtrip@example.com"


def test_duplicate_signup_is_rejected():
    _signup("dupe@example.com")
    r = client.post("/auth/signup", json={"name": "Again", "email": "dupe@example.com", "password": "password123"})
    assert r.status_code == 409


def test_login_with_wrong_password_is_rejected():
    _signup("wrongpw@example.com")
    r = client.post("/auth/login", json={"email": "wrongpw@example.com", "password": "not-the-password"})
    assert r.status_code == 401


def test_protected_route_requires_authentication():
    r = client.get("/reconciliation/000000000000000000000000/summary")
    assert r.status_code == 401


def test_user_cannot_access_another_users_reconciliation():
    token_a = _signup("owner@example.com")
    token_b = _signup("intruder@example.com")

    upload = client.post("/datasets/demo", headers={"Authorization": f"Bearer {token_a}"})
    assert upload.status_code == 200, upload.text
    rid = upload.json()["reconciliation_id"]
    run = client.post(f"/reconciliation/run/{rid}", headers={"Authorization": f"Bearer {token_a}"})
    assert run.status_code == 200

    own = client.get(f"/reconciliation/{rid}/summary", headers={"Authorization": f"Bearer {token_a}"})
    assert own.status_code == 200

    other_summary = client.get(f"/reconciliation/{rid}/summary", headers={"Authorization": f"Bearer {token_b}"})
    assert other_summary.status_code == 404

    other_list = client.get(f"/reconciliation/{rid}/discrepancies", headers={"Authorization": f"Bearer {token_b}"})
    assert other_list.status_code == 404
