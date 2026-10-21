import os
import re
import tempfile
from urllib.parse import urlparse

import pytest
from werkzeug.security import check_password_hash

import database.db as db_module
from app import DUPLICATE_EMAIL_ERROR, REGISTER_SUCCESS

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

NAME_REQUIRED = "Please enter your name."
NAME_TOO_LONG = "Name must be 100 characters or fewer."
EMAIL_INVALID = "Please enter a valid email address."
PASSWORD_SHORT = "Password must be at least 8 characters."
PASSWORD_MISMATCH = "Passwords do not match."


def post_register(client, **overrides):
    data = {"name": "Asha Rao", "email": "asha@example.com", "password": "password123"}
    data.update(overrides)
    data.setdefault("confirm_password", data["password"])
    return client.post("/register", data=data)


def user_count():
    conn = db_module.get_db()
    try:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    finally:
        conn.close()


def body(response):
    return response.get_data(as_text=True)


# --- GET ------------------------------------------------------------- #

def test_register_route_accepts_get_and_post(app):
    rule = next(r for r in app.url_map.iter_rules() if r.endpoint == "register")
    assert {"GET", "POST"} <= rule.methods


def test_get_register_renders_form(client):
    response = client.get("/register")
    html = body(response)
    assert response.status_code == 200
    for field in (
        'name="name"',
        'name="email"',
        'name="password"',
        'name="confirm_password"',
        'minlength="8"',
    ):
        assert field in html
    assert 'action="/register"' in html


def test_register_form_action_uses_url_for():
    with open(os.path.join(PROJECT_ROOT, "templates", "register.html")) as f:
        source = f.read()
    assert "url_for('register')" in source
    assert 'action="/register"' not in source


# --- Success path ---------------------------------------------------- #

def test_valid_registration_redirects_to_login(client):
    response = post_register(client)
    assert response.status_code == 302
    assert urlparse(response.headers["Location"]).path == "/login"


def test_success_flash_shown_once(client):
    response = client.post(
        "/register",
        data={
            "name": "Asha Rao",
            "email": "asha@example.com",
            "password": "password123",
            "confirm_password": "password123",
        },
        follow_redirects=True,
    )
    html = body(response)
    assert response.status_code == 200
    assert 'class="auth-success"' in html
    assert REGISTER_SUCCESS in html

    assert REGISTER_SUCCESS not in body(client.get("/login"))


def test_user_row_created_with_werkzeug_hash(client):
    before = user_count()
    post_register(client, name="  Asha Rao  ")
    assert user_count() == before + 1

    user = db_module.get_user_by_email("asha@example.com")
    assert user["name"] == "Asha Rao"
    assert user["password_hash"].startswith(("scrypt:", "pbkdf2:"))
    assert user["password_hash"] != "password123"
    assert check_password_hash(user["password_hash"], "password123")


def test_email_normalised(client):
    post_register(client, email="  Foo@Bar.COM ")
    assert db_module.get_user_by_email("foo@bar.com") is not None
    assert db_module.get_user_by_email("  Foo@Bar.COM ") is None


def test_name_at_limit_accepted(client):
    assert post_register(client, name="x" * 100).status_code == 302


def test_password_at_limit_accepted(client):
    assert post_register(client, password="12345678").status_code == 302


# --- Duplicates ------------------------------------------------------ #

@pytest.mark.parametrize(
    "email", ["demo@spendly.com", "DEMO@Spendly.com", "  Demo@SPENDLY.com "]
)
def test_duplicate_demo_email_rejected(client, email):
    before = user_count()
    response = post_register(client, email=email)
    assert response.status_code == 400
    assert DUPLICATE_EMAIL_ERROR in body(response)
    assert user_count() == before


def test_duplicate_after_own_registration(client):
    assert post_register(client, email="a@b.com").status_code == 302
    before = user_count()
    response = post_register(client, email="A@B.COM")
    assert response.status_code == 400
    assert DUPLICATE_EMAIL_ERROR in body(response)
    assert user_count() == before


def test_integrity_error_backstop(client, monkeypatch):
    monkeypatch.setattr("app.get_user_by_email", lambda email: None)
    before = user_count()
    response = post_register(client, email="demo@spendly.com")
    assert response.status_code == 400
    assert DUPLICATE_EMAIL_ERROR in body(response)
    assert user_count() == before


# --- Validation errors ----------------------------------------------- #

@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"name": ""}, NAME_REQUIRED),
        ({"name": "   "}, NAME_REQUIRED),
        ({"name": "x" * 101}, NAME_TOO_LONG),
        ({"email": ""}, EMAIL_INVALID),
        ({"email": "foo"}, EMAIL_INVALID),
        ({"email": "foo@bar"}, EMAIL_INVALID),
        ({"email": "@bar.com"}, EMAIL_INVALID),
        ({"password": ""}, PASSWORD_SHORT),
        ({"password": "1234567"}, PASSWORD_SHORT),
        ({"confirm_password": "password124"}, PASSWORD_MISMATCH),
        ({"confirm_password": ""}, PASSWORD_MISMATCH),
    ],
)
def test_invalid_input_rejected(client, overrides, message):
    before = user_count()
    response = post_register(client, **overrides)
    assert response.status_code == 400
    assert message in body(response)
    assert user_count() == before


def test_validation_order_first_failure_wins(client):
    html = body(post_register(client, name="", email="bad", password="short"))
    assert NAME_REQUIRED in html
    assert EMAIL_INVALID not in html

    html = body(post_register(client, email="bad", password="short"))
    assert EMAIL_INVALID in html
    assert PASSWORD_SHORT not in html

    html = body(post_register(client, password="short", confirm_password="other"))
    assert PASSWORD_SHORT in html
    assert PASSWORD_MISMATCH not in html


def test_mismatch_checked_before_duplicate(client):
    html = body(
        post_register(client, email="demo@spendly.com", confirm_password="nope12345")
    )
    assert PASSWORD_MISMATCH in html
    assert DUPLICATE_EMAIL_ERROR not in html


def test_failed_submit_repopulates_name_email_not_password(client):
    html = body(
        post_register(client, password="secret123", confirm_password="secret124")
    )
    assert 'value="Asha Rao"' in html
    assert 'value="asha@example.com"' in html

    for field in ("password", "confirm_password"):
        tag = re.search(rf'<input[^>]*name="{field}"[^>]*>', html).group(0)
        assert "value=" not in tag
    assert "secret123" not in html
    assert "secret124" not in html


def test_repopulated_values_are_escaped(client):
    html = body(post_register(client, name="<b>x</b>", password="short"))
    assert "&lt;b&gt;x&lt;/b&gt;" in html
    assert "<b>x</b>" not in html


# --- Styling and isolation ------------------------------------------- #

def test_new_css_uses_variables_only():
    with open(os.path.join(PROJECT_ROOT, "static", "css", "style.css")) as f:
        css = f.read()
    block = re.search(r"\.auth-success\s*\{([^}]*)\}", css).group(1)
    assert "var(--accent" in block
    assert "#" not in block


def test_tests_use_temp_database(app, real_db_snapshot):
    real_db, _ = real_db_snapshot
    assert os.path.abspath(db_module.DB_PATH) != os.path.abspath(real_db)
    assert os.path.realpath(db_module.DB_PATH).startswith(
        os.path.realpath(tempfile.gettempdir())
    )


def test_real_database_untouched(real_db_snapshot):
    from conftest import _sha256

    real_db, snapshot = real_db_snapshot
    assert _sha256(real_db) == snapshot
