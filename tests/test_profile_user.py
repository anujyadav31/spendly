from datetime import date
from urllib.parse import urlparse

import database.db as db_module
from app import format_display_date, format_inr


def _seed_user_id():
    return db_module.get_user_by_email("demo@spendly.com")["id"]


# --- get_user_by_id -------------------------------------------------- #

def test_get_user_by_id_returns_seed_user(app):
    user = db_module.get_user_by_id(_seed_user_id())
    assert user["name"] == "Demo User"
    assert user["email"] == "demo@spendly.com"
    assert user["member_since"] == date.today().strftime("%B %Y")


def test_get_user_by_id_missing_returns_none(app):
    assert db_module.get_user_by_id(99999) is None


# --- Route ----------------------------------------------------------- #

def test_profile_stale_session_clears_and_redirects(client):
    with client.session_transaction() as sess:
        sess["user_id"] = 99999
        sess["user_name"] = "Ghost"

    response = client.get("/profile")
    assert response.status_code == 302
    assert urlparse(response.headers["Location"]).path == "/login"
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_profile_shows_member_since_from_db(client):
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})
    html = client.get("/profile").get_data(as_text=True)
    assert date.today().strftime("%B %Y") in html


# --- Filters --------------------------------------------------------- #

def test_display_date_formats_iso():
    assert format_display_date("2026-10-01") == "01 Oct 2026"


def test_display_date_passes_through_invalid():
    assert format_display_date("not a date") == "not a date"
    assert format_display_date(None) is None


def test_inr_handles_none():
    assert format_inr(None) == "₹0.00"
