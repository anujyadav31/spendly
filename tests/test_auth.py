import os
import re
from urllib.parse import urlparse

import pytest
from markupsafe import escape

import database.db as db_module
from app import LOGIN_ERROR, LOGOUT_SUCCESS, REGISTER_SUCCESS

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def post_login(client, email="demo@spendly.com", password="demo123", **kwargs):
    return client.post("/login", data={"email": email, "password": password}, **kwargs)


def body(response):
    return response.get_data(as_text=True)


def session_of(client):
    with client.session_transaction() as sess:
        return dict(sess)


def redirect_path(response):
    return urlparse(response.headers["Location"]).path


# --- GET /login ------------------------------------------------------ #

def test_login_route_accepts_get_and_post(app):
    rule = next(r for r in app.url_map.iter_rules() if r.endpoint == "login")
    assert {"GET", "POST"} <= rule.methods


def test_get_login_renders_form(client):
    response = client.get("/login")
    html = body(response)
    assert response.status_code == 200
    assert 'name="email"' in html
    assert 'name="password"' in html
    assert 'action="/login"' in html


def test_login_form_action_uses_url_for():
    with open(os.path.join(PROJECT_ROOT, "templates", "login.html")) as f:
        source = f.read()
    assert "url_for('login')" in source
    assert 'action="/login"' not in source


def test_get_login_when_signed_in_redirects(client):
    post_login(client)
    response = client.get("/login")
    assert response.status_code == 302
    assert redirect_path(response) == "/"


def test_get_register_when_signed_in_redirects(client):
    post_login(client)
    response = client.get("/register")
    assert response.status_code == 302
    assert redirect_path(response) == "/"


def test_post_register_when_signed_in_creates_no_user(client):
    post_login(client)
    response = client.post(
        "/register",
        data={
            "name": "Asha Rao",
            "email": "asha@example.com",
            "password": "password123",
            "confirm_password": "password123",
        },
    )
    assert response.status_code == 302
    assert redirect_path(response) == "/"
    assert db_module.get_user_by_email("asha@example.com") is None
    assert session_of(client)["user_name"] == "Demo User"


# --- Successful login ------------------------------------------------ #

def test_demo_login_redirects_to_landing(client):
    response = post_login(client)
    assert response.status_code == 302
    assert redirect_path(response) == "/"


def test_login_sets_session(client):
    post_login(client)
    sess = session_of(client)
    demo = db_module.get_user_by_email("demo@spendly.com")
    assert sess["user_id"] == demo["id"]
    assert sess["user_name"] == "Demo User"
    assert set(sess) - {"_flashes"} == {"user_id", "user_name"}


def test_login_clears_existing_session(client):
    with client.session_transaction() as sess:
        sess["stale"] = "value"
    post_login(client)
    assert "stale" not in session_of(client)


def test_welcome_flash_shown_once(client):
    html = body(post_login(client, follow_redirects=True))
    assert "Welcome back" in html
    assert 'class="auth-success"' in html
    assert "Welcome back, Demo User" not in body(client.get("/"))


@pytest.mark.parametrize("email", ["  DEMO@Spendly.com ", "Demo@SPENDLY.COM"])
def test_email_case_and_whitespace_insensitive(client, email):
    response = post_login(client, email=email)
    assert response.status_code == 302
    assert "user_id" in session_of(client)


def test_navbar_signed_in(client):
    post_login(client)
    html = body(client.get("/"))
    assert "Demo User" in html
    assert "Sign out" in html
    assert 'href="/logout"' in html
    assert "Sign in" not in html
    assert "Get started" not in html


def test_navbar_signed_out(client):
    html = body(client.get("/"))
    assert "Sign in" in html
    assert "Get started" in html
    assert "Sign out" not in html


def test_registered_user_can_login(client):
    client.post(
        "/register",
        data={
            "name": "Asha Rao",
            "email": "asha@example.com",
            "password": "password123",
            "confirm_password": "password123",
        },
    )
    response = post_login(client, email="ASHA@example.com", password="password123")
    assert response.status_code == 302
    assert session_of(client)["user_name"] == "Asha Rao"


# --- Failed login ---------------------------------------------------- #

@pytest.mark.parametrize(
    "data",
    [
        {"email": "demo@spendly.com", "password": "wrong-password"},
        {"email": "nobody@example.com", "password": "demo123"},
        {"email": "", "password": "demo123"},
        {"email": "demo@spendly.com", "password": ""},
        {"email": "", "password": ""},
        {"email": "   ", "password": "demo123"},
        {},
    ],
    ids=[
        "wrong-password",
        "unknown-email",
        "blank-email",
        "blank-password",
        "both-blank",
        "whitespace-email",
        "missing-fields",
    ],
)
def test_failed_login_generic_401(client, data):
    response = client.post("/login", data=data)
    assert response.status_code == 401
    assert LOGIN_ERROR in body(response)
    assert "user_id" not in session_of(client)


def test_failed_login_repopulates_email_not_password(client):
    html = body(post_login(client, password="wrongpass-xyz"))
    assert 'value="demo@spendly.com"' in html
    assert "wrongpass-xyz" not in html


# --- Logout ---------------------------------------------------------- #

def test_logout_clears_session_and_redirects(client):
    post_login(client)
    response = client.get("/logout")
    assert response.status_code == 302
    assert redirect_path(response) == "/"
    sess = session_of(client)
    assert "user_id" not in sess
    assert "user_name" not in sess


def test_logout_flash_shown_once(client):
    post_login(client, follow_redirects=True)
    html = body(client.get("/logout", follow_redirects=True))
    assert str(escape(LOGOUT_SUCCESS)) in html
    assert "Sign in" in html
    assert "Get started" in html
    assert str(escape(LOGOUT_SUCCESS)) not in body(client.get("/"))


def test_logout_when_signed_out(client):
    response = client.get("/logout")
    assert response.status_code == 302
    assert redirect_path(response) == "/"
    assert client.get("/logout", follow_redirects=True).status_code == 200


# --- Regressions and constraints ------------------------------------- #

def test_register_flash_still_once_on_login(client):
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
    assert body(response).count(REGISTER_SUCCESS) == 1
    assert REGISTER_SUCCESS not in body(client.get("/login"))


@pytest.mark.parametrize("selector", [r"\.flash-stack", r"\.flash-info", r"\.nav-user"])
def test_new_auth_css_uses_variables_only(selector):
    with open(os.path.join(PROJECT_ROOT, "static", "css", "style.css")) as f:
        css = f.read()
    match = re.search(selector + r"\s*\{([^}]*)\}", css)
    assert match, f"{selector} rule missing"
    assert "#" not in match.group(1)


def test_authenticate_user_helper(app):
    user = db_module.authenticate_user("demo@spendly.com", "demo123")
    assert user is not None
    assert user["name"] == "Demo User"
    assert db_module.authenticate_user("demo@spendly.com", "nope") is None
    assert db_module.authenticate_user("nobody@example.com", "demo123") is None
