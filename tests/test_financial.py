import os
import tempfile
import sqlite3

try:
    import pytest
except Exception:
    # minimal fallback for pytest.approx used in tests
    class _Approx:
        def __init__(self, value, rel=1e-12, atol=1e-12):
            self.value = value
            self.tol = max(rel * abs(value), atol)
        def __eq__(self, other):
            try:
                return abs(float(other) - float(self.value)) <= self.tol
            except Exception:
                return False
        def __repr__(self):
            return f"approx({self.value})"
    class _PytestFallback:
        @staticmethod
        def approx(value):
            return _Approx(value)
    pytest = _PytestFallback()

from fastapi.testclient import TestClient


def setup_app_db():
    tf = tempfile.NamedTemporaryFile(delete=False)
    db_path = tf.name
    tf.close()
    os.environ["USERS_DB"] = db_path
    return db_path


def test_deposit_withdraw_and_loan_flow():
    db_path = setup_app_db()

    # import app after setting USERS_DB
    from backend.main import app

    admin_client = TestClient(app)
    user_client = TestClient(app)

    # Register admin (first user becomes admin)
    r = admin_client.post("/register", data={"username": "admin", "password": "adm"})
    assert r.status_code in (200, 303)
    # login admin
    r = admin_client.post("/login", data={"username": "admin", "password": "adm"})
    assert r.status_code in (200, 303)

    # Register normal user
    r = user_client.post("/register", data={"username": "user1", "password": "pwd"})
    assert r.status_code in (200, 303)
    r = user_client.post("/login", data={"username": "user1", "password": "pwd"})
    assert r.status_code in (200, 303)

    # Deposit 100
    r = user_client.post("/client/savings/deposit", data={"amount": "100"})
    assert r.status_code in (200, 303)

    # Withdraw 30
    r = user_client.post("/client/savings/withdraw", data={"amount": "30"})
    assert r.status_code in (200, 303)

    # Check balance via DB
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    user = conn.execute("SELECT id FROM users WHERE username = ?", ("user1",)).fetchone()
    assert user is not None
    uid = user["id"]
    deposits = conn.execute("SELECT COALESCE(SUM(amount),0) FROM savings WHERE user_id = ? AND type = 'deposit'", (uid,)).fetchone()[0]
    withdrawals = conn.execute("SELECT COALESCE(SUM(amount),0) FROM savings WHERE user_id = ? AND type = 'withdraw'", (uid,)).fetchone()[0]
    assert float(deposits) - float(withdrawals) == pytest.approx(70.0)

    # Request a loan
    r = user_client.post("/client/loan/request", data={"amount": "50", "term": "6"})
    assert r.status_code in (200, 303)

    # Get loan id
    loan = conn.execute("SELECT id, status FROM loans WHERE user_id = ? ORDER BY id DESC LIMIT 1", (uid,)).fetchone()
    assert loan is not None
    loan_id = loan["id"]
    assert loan["status"] == "pending"

    # Admin approves the loan
    r = admin_client.post("/admin/loan/approve", data={"loan_id": str(loan_id)})
    assert r.status_code in (200, 303)

    loan2 = conn.execute("SELECT status FROM loans WHERE id = ?", (loan_id,)).fetchone()
    assert loan2["status"] == "approved"

    conn.close()
