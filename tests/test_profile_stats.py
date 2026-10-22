import database.db as db_module

ZERO_STATS = {
    "total_spent": 0.0,
    "transaction_count": 0,
    "top_category": "—",
    "top_category_total": 0.0,
}


def _seed_user_id():
    return db_module.get_user_by_email("demo@spendly.com")["id"]


def _new_user(email="fresh@spendly.com", password="secret123"):
    return db_module.create_user("Fresh User", email, password)


def _add_expense(user_id, amount, category, expense_date="2026-01-15",
                 description="Test expense"):
    conn = db_module.get_db()
    try:
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, expense_date, description),
        )
        conn.commit()
    finally:
        conn.close()


def _login(client, email, password):
    return client.post("/login", data={"email": email, "password": password})


def test_seed_user_stats(app):
    stats = db_module.get_summary_stats(_seed_user_id())
    assert stats == {
        "total_spent": 5488.5,
        "transaction_count": 8,
        "top_category": "Bills",
        "top_category_total": 1850.0,
    }


def test_new_user_gets_exact_zero_stats(app):
    assert db_module.get_summary_stats(_new_user()) == ZERO_STATS


def test_top_category_tie_resolves_alphabetically(app):
    user_id = _new_user()
    _add_expense(user_id, 300.0, "Shopping")
    _add_expense(user_id, 100.0, "Food")
    _add_expense(user_id, 200.0, "Food")
    stats = db_module.get_summary_stats(user_id)
    assert stats["top_category"] == "Food"
    assert stats["top_category_total"] == 300.0
    assert stats["transaction_count"] == 3
    assert stats["total_spent"] == 600.0


def test_other_users_expenses_excluded(app):
    user_id = _new_user()
    _add_expense(user_id, 99.99, "Health")
    stats = db_module.get_summary_stats(user_id)
    assert stats == {
        "total_spent": 99.99,
        "transaction_count": 1,
        "top_category": "Health",
        "top_category_total": 99.99,
    }
    seed_stats = db_module.get_summary_stats(_seed_user_id())
    assert seed_stats["total_spent"] == 5488.5
    assert seed_stats["transaction_count"] == 8


def test_profile_route_shows_seed_stats(client):
    _login(client, "demo@spendly.com", "demo123")
    response = client.get("/profile")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "₹5,488.50" in html
    assert "₹1,850.00" in html
    assert html.count("All time") >= 2
    assert "This month" not in html


def test_profile_route_new_user_shows_zero_stats(client):
    _new_user()
    _login(client, "fresh@spendly.com", "secret123")
    response = client.get("/profile")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "₹0.00" in html
    assert "—" in html
