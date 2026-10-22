import re

import database.db as db_module

SEED_EMAIL = "demo@spendly.com"
SEED_PASSWORD = "demo123"

SEED_NAMES = ["Bills", "Shopping", "Food", "Health", "Entertainment", "Transport", "Other"]
SEED_TOTALS = [1850.0, 1299.0, 760.50, 680.0, 499.0, 250.0, 150.0]


def _seed_user_id():
    return db_module.get_user_by_email(SEED_EMAIL)["id"]


def _new_user(email="fresh@spendly.com", password="password123"):
    return db_module.create_user("Fresh User", email, password)


def _add_expense(user_id, amount, category, day="2026-10-01", description="test"):
    conn = db_module.get_db()
    try:
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, day, description),
        )
        conn.commit()
    finally:
        conn.close()


def _login(client, email, password):
    return client.post("/login", data={"email": email, "password": password})


# ------------------------------------------------------------------ #
# get_category_breakdown                                              #
# ------------------------------------------------------------------ #


def test_seed_breakdown_names_and_totals(app):
    breakdown = db_module.get_category_breakdown(_seed_user_id())
    assert [c["name"] for c in breakdown] == SEED_NAMES
    assert [c["total"] for c in breakdown] == SEED_TOTALS
    assert set(breakdown[0]) == {"name", "total", "percent"}


def test_seed_breakdown_percents(app):
    percents = [c["percent"] for c in db_module.get_category_breakdown(_seed_user_id())]
    assert percents == [33, 24, 14, 12, 9, 5, 3]
    assert all(isinstance(p, int) for p in percents)
    assert sum(percents) == 100


def test_single_category_is_100_percent(app):
    user_id = _new_user()
    _add_expense(user_id, 42.0, "Food")
    _add_expense(user_id, 8.0, "Food")
    breakdown = db_module.get_category_breakdown(user_id)
    assert breakdown == [{"name": "Food", "total": 50.0, "percent": 100}]


def test_three_equal_categories_sum_to_100(app):
    user_id = _new_user()
    for category in ("Food", "Bills", "Transport"):
        _add_expense(user_id, 100.0, category)
    breakdown = db_module.get_category_breakdown(user_id)
    assert [c["percent"] for c in breakdown] == [34, 33, 33]
    # Ties broken by name ascending.
    assert [c["name"] for c in breakdown] == ["Bills", "Food", "Transport"]


def test_new_user_has_empty_breakdown(app):
    assert db_module.get_category_breakdown(_new_user()) == []


def test_other_users_expenses_excluded(app):
    user_id = _new_user()
    _add_expense(user_id, 10.0, "Health")
    breakdown = db_module.get_category_breakdown(user_id)
    assert breakdown == [{"name": "Health", "total": 10.0, "percent": 100}]
    # Seed user's breakdown is unaffected by the new user's expense.
    seed = db_module.get_category_breakdown(_seed_user_id())
    assert [c["total"] for c in seed] == SEED_TOTALS


# ------------------------------------------------------------------ #
# /profile route                                                      #
# ------------------------------------------------------------------ #


def test_profile_renders_category_bars(app, client):
    _login(client, SEED_EMAIL, SEED_PASSWORD)
    html = client.get("/profile").get_data(as_text=True)
    assert html.count('<progress class="cat-bar') == 7
    percents = [int(p) for p in re.findall(r'<span class="cat-percent">(\d+)%</span>', html)]
    assert len(percents) == 7
    assert sum(percents) == 100


def test_profile_new_user_shows_empty_state(app, client):
    _new_user()
    _login(client, "fresh@spendly.com", "password123")
    html = client.get("/profile").get_data(as_text=True)
    assert "No spending yet." in html
    assert '<progress class="cat-bar' not in html
