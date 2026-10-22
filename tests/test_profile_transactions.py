import re

import database.db as db_module

ISO_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
DISPLAY_DATE_RE = re.compile(r"\d{2} [A-Z][a-z]{2} \d{4}")
EXPECTED_KEYS = {"date", "description", "category", "amount"}


def _seed_user_id():
    return db_module.get_user_by_email("demo@spendly.com")["id"]


def _new_user(email="fresh@spendly.com", password="secret123"):
    return db_module.create_user("Fresh User", email, password)


def _add_expense(user_id, amount, category, date_str, desc="Test expense"):
    conn = db_module.get_db()
    try:
        cur = conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, date_str, desc),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _login(client, email, password):
    return client.post("/login", data={"email": email, "password": password})


def _tbody(html):
    match = re.search(r"<tbody>(.*?)</tbody>", html, re.S)
    assert match, "transaction table body not found"
    return match.group(1)


# ------------------------------------------------------------------ #
# get_recent_transactions                                             #
# ------------------------------------------------------------------ #


def test_seed_user_returns_eight_dicts_with_expected_keys(app):
    rows = db_module.get_recent_transactions(_seed_user_id())
    assert len(rows) == 8
    for row in rows:
        assert isinstance(row, dict)
        assert set(row) == EXPECTED_KEYS
        assert isinstance(row["amount"], float)
        assert ISO_DATE_RE.fullmatch(row["date"])


def test_dates_are_newest_first(app):
    dates = [r["date"] for r in db_module.get_recent_transactions(_seed_user_id())]
    assert dates == sorted(dates, reverse=True)


def test_same_date_rows_ordered_by_id_desc(app):
    user_id = _new_user()
    _add_expense(user_id, 10.0, "Food", "2026-01-05", "first")
    _add_expense(user_id, 20.0, "Food", "2026-01-05", "second")
    _add_expense(user_id, 30.0, "Food", "2026-01-05", "third")
    descs = [r["description"] for r in db_module.get_recent_transactions(user_id)]
    assert descs == ["third", "second", "first"]


def test_default_limit_is_ten(app):
    user_id = _new_user()
    for day in range(1, 13):
        _add_expense(user_id, float(day), "Other", f"2026-02-{day:02d}")
    rows = db_module.get_recent_transactions(user_id)
    assert len(rows) == 10
    assert rows[0]["date"] == "2026-02-12"
    assert rows[-1]["date"] == "2026-02-03"


def test_custom_limit(app):
    user_id = _new_user()
    for day in range(1, 13):
        _add_expense(user_id, float(day), "Other", f"2026-02-{day:02d}")
    assert len(db_module.get_recent_transactions(user_id, limit=3)) == 3


def test_new_user_has_no_transactions(app):
    assert db_module.get_recent_transactions(_new_user()) == []


def test_other_users_expenses_excluded(app):
    user_id = _new_user()
    _add_expense(user_id, 99.0, "Food", "2026-03-01", "mine")
    rows = db_module.get_recent_transactions(user_id)
    assert [r["description"] for r in rows] == ["mine"]
    seed_descs = {
        r["description"] for r in db_module.get_recent_transactions(_seed_user_id())
    }
    assert "mine" not in seed_descs


def test_null_description_becomes_empty_string(app):
    user_id = _new_user()
    _add_expense(user_id, 5.0, "Other", "2026-04-01", None)
    assert db_module.get_recent_transactions(user_id)[0]["description"] == ""


# ------------------------------------------------------------------ #
# /profile route                                                      #
# ------------------------------------------------------------------ #


def test_profile_shows_seed_transactions(client):
    _login(client, "demo@spendly.com", "demo123")
    resp = client.get("/profile")
    assert resp.status_code == 200
    body = _tbody(resp.get_data(as_text=True))
    assert len(re.findall(r"<tr>", body)) == 8
    assert len(DISPLAY_DATE_RE.findall(body)) == 8
    assert not ISO_DATE_RE.search(body)
    assert "No expenses yet." not in body


def test_profile_empty_state_for_new_user(client):
    _new_user()
    _login(client, "fresh@spendly.com", "secret123")
    resp = client.get("/profile")
    assert resp.status_code == 200
    assert "No expenses yet." in _tbody(resp.get_data(as_text=True))
