import hashlib
import os
import shutil
import tempfile

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL_DB = os.path.join(PROJECT_ROOT, "expense_tracker.db")


def _sha256(path):
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


# Snapshot the real DB and redirect the app to a temp DB *before* importing
# it — app.py runs init_db()/seed_db() at import time.
REAL_DB_SHA256 = _sha256(REAL_DB)
SESSION_DIR = tempfile.mkdtemp(prefix="spendly-tests-")
os.environ["SPENDLY_DB_PATH"] = os.path.join(SESSION_DIR, "import.db")
os.environ.setdefault("SPENDLY_SECRET_KEY", "test-secret")

import database.db as db_module  # noqa: E402
from app import app as flask_app  # noqa: E402


@pytest.fixture
def app(tmp_path, monkeypatch):
    """Fresh, seeded temp database for every test."""
    monkeypatch.setattr(db_module, "DB_PATH", str(tmp_path / "test.db"))
    db_module.init_db()
    db_module.seed_db()
    flask_app.config.update(TESTING=True)
    yield flask_app


@pytest.fixture
def real_db_snapshot():
    return REAL_DB, REAL_DB_SHA256


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(SESSION_DIR, ignore_errors=True)
    if _sha256(REAL_DB) != REAL_DB_SHA256:
        print(f"\nERROR: test run modified the real database at {REAL_DB}")
        session.exitstatus = 1
