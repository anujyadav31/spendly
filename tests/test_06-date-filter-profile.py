"""Tests for Step 6: date-range filter on GET /profile."""
import datetime
import html as html_lib
import re

import pytest

import database.db as db_module

PASSWORD = "secret123"


# ---------------------------------------------------------------- helpers
def _new_user(email="filter@spendly.com"):
    return db_module.create_user("Filter User", email, PASSWORD)


def _add_expense(user_id, amount, category, expense_date, description="Test expense"):
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


def _login(client, email, password=PASSWORD):
    return client.post("/login", data={"email": email, "password": password})


def _expense_count(user_id):
    conn = db_module.get_db()
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM expenses WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
    finally:
        conn.close()


def _get(client, **params):
    response = client.get("/profile", query_string=params)
    return response, response.get_data(as_text=True)


@pytest.fixture
def ranged(app):
    """A fresh user with fixed-date expenses across several months."""
    user_id = _new_user()
    _add_expense(user_id, 100.0, "Food", "2025-01-10", "JAN-ITEM")
    _add_expense(user_id, 200.0, "Food", "2025-02-15", "FEB-ITEM")
    _add_expense(user_id, 300.0, "Bills", "2025-02-28", "FEBEND-ITEM")
    _add_expense(user_id, 400.0, "Travel", "2025-03-01", "MAR-ITEM")
    return user_id


@pytest.fixture
def logged_in(client, ranged):
    _login(client, "filter@spendly.com")
    return client


def _find_preset_href(html, label):
    """Return the unescaped href of the anchor whose text is `label`."""
    pattern = r'<a\b[^>]*href="([^"]*)"[^>]*>\s*' + re.escape(label) + r"\s*</a>"
    match = re.search(pattern, html, re.IGNORECASE)
    assert match, f"Expected a preset link labelled {label!r}"
    return html_lib.unescape(match.group(1))


def _find_preset_tag(html, label):
    pattern = r"<a\b[^>]*>\s*" + re.escape(label) + r"\s*</a>"
    match = re.search(pattern, html, re.IGNORECASE)
    assert match, f"Expected a preset link labelled {label!r}"
    return match.group(0)


def _iso(d):
    return d.isoformat()


# ---------------------------------------------------------------- auth guard
class TestAuthGuard:
    @pytest.mark.parametrize(
        "params",
        [
            {},
            {"date_from": "2025-01-01", "date_to": "2025-12-31"},
            {"date_from": "garbage"},
        ],
    )
    def test_profile_with_filter_signed_out_redirects_to_login(self, client, params):
        response = client.get("/profile", query_string=params)
        assert response.status_code == 302, "Signed-out user must be redirected"
        assert "/login" in response.headers["Location"]


# ---------------------------------------------------------------- unfiltered
class TestUnfiltered:
    def test_no_params_shows_all_expenses(self, logged_in):
        response, html = _get(logged_in)
        assert response.status_code == 200
        for desc in ("JAN-ITEM", "FEB-ITEM", "FEBEND-ITEM", "MAR-ITEM"):
            assert desc in html, f"{desc} should show with no filter"
        assert "₹1,000.00" in html, "Total of all expenses expected"

    def test_seed_user_no_params_matches_step5_totals(self, client):
        _login(client, "demo@spendly.com", "demo123")
        response, html = _get(client)
        assert response.status_code == 200
        assert "₹5,488.50" in html

    def test_helpers_without_dates_are_unfiltered(self, ranged):
        stats = db_module.get_summary_stats(ranged)
        assert stats["total_spent"] == 1000.0
        assert stats["transaction_count"] == 4
        assert len(db_module.get_recent_transactions(ranged)) == 4
        assert sum(c["total"] for c in db_module.get_category_breakdown(ranged)) == 1000.0

    def test_only_one_bound_given_is_unfiltered(self, logged_in):
        _, html = _get(logged_in, date_from="2025-02-01")
        for desc in ("JAN-ITEM", "FEB-ITEM", "FEBEND-ITEM", "MAR-ITEM"):
            assert desc in html, "A single bound should fall back to unfiltered"
        _, html = _get(logged_in, date_to="2025-02-01")
        for desc in ("JAN-ITEM", "FEB-ITEM", "FEBEND-ITEM", "MAR-ITEM"):
            assert desc in html, "A single bound should fall back to unfiltered"


# ---------------------------------------------------------------- custom range (route)
class TestCustomRangeRoute:
    def test_range_limits_transactions(self, logged_in):
        response, html = _get(logged_in, date_from="2025-02-01", date_to="2025-02-28")
        assert response.status_code == 200
        assert "FEB-ITEM" in html
        assert "FEBEND-ITEM" in html
        assert "JAN-ITEM" not in html
        assert "MAR-ITEM" not in html

    def test_range_limits_summary_stats(self, logged_in):
        _, html = _get(logged_in, date_from="2025-02-01", date_to="2025-02-28")
        assert "₹500.00" in html, "Total spent should be 200 + 300"
        assert "₹1,000.00" not in html

    def test_range_limits_category_breakdown(self, logged_in):
        _, html = _get(logged_in, date_from="2025-02-01", date_to="2025-02-28")
        assert "Bills" in html
        assert "Food" in html
        assert "Travel" not in html, "Travel expense is outside the range"

    def test_bounds_are_inclusive(self, logged_in):
        _, html = _get(logged_in, date_from="2025-02-28", date_to="2025-03-01")
        assert "FEBEND-ITEM" in html, "date_from must be inclusive"
        assert "MAR-ITEM" in html, "date_to must be inclusive"
        assert "FEB-ITEM" not in html.replace("FEBEND-ITEM", "")

    def test_same_day_range_is_valid(self, logged_in):
        response, html = _get(logged_in, date_from="2025-02-15", date_to="2025-02-15")
        assert "FEB-ITEM" in html
        assert "JAN-ITEM" not in html
        assert "Start date must be before end date." not in html

    def test_active_custom_range_reflected_in_inputs(self, logged_in):
        _, html = _get(logged_in, date_from="2025-02-01", date_to="2025-02-28")
        assert 'type="date"' in html
        assert 'name="date_from"' in html
        assert 'name="date_to"' in html
        assert "2025-02-01" in html
        assert "2025-02-28" in html

    def test_amounts_keep_rupee_symbol_when_filtered(self, logged_in):
        _, html = _get(logged_in, date_from="2025-02-01", date_to="2025-02-28")
        assert "₹" in html
        assert not re.search(r"\$\s?\d", html), "No dollar amounts expected"

    def test_other_users_data_not_leaked_in_range(self, logged_in):
        other = _new_user("other@spendly.com")
        _add_expense(other, 777.0, "Health", "2025-02-10", "OTHER-USER-ITEM")
        _, html = _get(logged_in, date_from="2025-02-01", date_to="2025-02-28")
        assert "OTHER-USER-ITEM" not in html


# ---------------------------------------------------------------- empty range
class TestEmptyRange:
    def test_range_with_no_expenses_shows_zero_state(self, logged_in):
        response, html = _get(logged_in, date_from="2020-01-01", date_to="2020-01-31")
        assert response.status_code == 200
        assert "₹0.00" in html
        for desc in ("JAN-ITEM", "FEB-ITEM", "FEBEND-ITEM", "MAR-ITEM"):
            assert desc not in html

    def test_empty_range_helpers(self, ranged):
        stats = db_module.get_summary_stats(ranged, "2020-01-01", "2020-01-31")
        assert stats["total_spent"] == 0.0
        assert stats["transaction_count"] == 0
        assert db_module.get_recent_transactions(
            ranged, date_from="2020-01-01", date_to="2020-01-31"
        ) == []
        assert db_module.get_category_breakdown(ranged, "2020-01-01", "2020-01-31") == []


# ---------------------------------------------------------------- invalid input
class TestInvalidInput:
    @pytest.mark.parametrize(
        "params",
        [
            {"date_from": "not-a-date", "date_to": "2025-02-28"},
            {"date_from": "2025-02-01", "date_to": "not-a-date"},
            {"date_from": "not-a-date", "date_to": "also-bad"},
            {"date_from": "2025-13-45", "date_to": "2025-14-01"},
            {"date_from": "02/01/2025", "date_to": "02/28/2025"},
            {"date_from": "", "date_to": ""},
            {"date_from": "' OR 1=1; DROP TABLE expenses;--", "date_to": "2025-02-28"},
        ],
    )
    def test_malformed_dates_fall_back_to_unfiltered(self, logged_in, ranged, params):
        response, html = _get(logged_in, **params)
        assert response.status_code == 200, "Malformed dates must not crash"
        for desc in ("JAN-ITEM", "FEB-ITEM", "FEBEND-ITEM", "MAR-ITEM"):
            assert desc in html, f"{desc} expected in unfiltered fallback"
        assert _expense_count(ranged) == 4, "expenses table must be intact"

    def test_malformed_dates_do_not_flash_range_error(self, logged_in):
        _, html = _get(logged_in, date_from="not-a-date")
        assert "Start date must be before end date." not in html

    def test_from_after_to_flashes_error_and_is_unfiltered(self, logged_in):
        response, html = _get(logged_in, date_from="2025-03-01", date_to="2025-01-01")
        assert response.status_code == 200
        assert "Start date must be before end date." in html
        assert 'class="auth-error"' in html
        for desc in ("JAN-ITEM", "FEB-ITEM", "FEBEND-ITEM", "MAR-ITEM"):
            assert desc in html, "Reversed range must fall back to unfiltered"
        assert "₹1,000.00" in html

    def test_valid_range_shows_no_error(self, logged_in):
        _, html = _get(logged_in, date_from="2025-01-01", date_to="2025-03-31")
        assert "Start date must be before end date." not in html


# ---------------------------------------------------------------- presets
class TestPresets:
    @pytest.mark.parametrize(
        "label",
        ["This Month", "Last 3 Months", "Last 6 Months", "All Time"],
    )
    def test_filter_bar_has_preset_links(self, logged_in, label):
        _, html = _get(logged_in)
        _find_preset_href(html, label)

    def test_all_time_preset_is_clean_profile_url(self, logged_in):
        _, html = _get(logged_in, date_from="2025-02-01", date_to="2025-02-28")
        href = _find_preset_href(html, "All Time")
        assert "?" not in href, "All Time must carry no query params"
        assert href.rstrip("/").endswith("/profile")

    def test_all_time_preset_removes_filter(self, logged_in):
        _, html = _get(logged_in, date_from="2025-02-01", date_to="2025-02-28")
        href = _find_preset_href(html, "All Time")
        response = logged_in.get(href)
        body = response.get_data(as_text=True)
        assert response.status_code == 200
        for desc in ("JAN-ITEM", "FEB-ITEM", "FEBEND-ITEM", "MAR-ITEM"):
            assert desc in body

    def test_this_month_link_params(self, logged_in):
        _, html = _get(logged_in)
        href = _find_preset_href(html, "This Month")
        today = datetime.date.today()
        assert f"date_from={_iso(today.replace(day=1))}" in href
        assert f"date_to={_iso(today)}" in href

    @pytest.mark.parametrize("label", ["Last 3 Months", "Last 6 Months"])
    def test_multi_month_links_end_today(self, logged_in, label):
        _, html = _get(logged_in)
        href = _find_preset_href(html, label)
        today = datetime.date.today()
        assert f"date_to={_iso(today)}" in href
        match = re.search(r"date_from=(\d{4}-\d{2}-\d{2})", href)
        assert match, "Preset must supply a date_from"
        start = datetime.date.fromisoformat(match.group(1))
        days = (today - start).days
        expected = (80, 100) if label == "Last 3 Months" else (170, 200)
        assert expected[0] <= days <= expected[1], (
            f"{label} window of {days} days is implausible"
        )

    def test_this_month_filters_all_sections(self, app, client):
        today = datetime.date.today()
        user_id = _new_user("presets@spendly.com")
        last_month_end = today.replace(day=1) - datetime.timedelta(days=1)
        _add_expense(user_id, 111.0, "Food", _iso(today), "TODAY-ITEM")
        _add_expense(user_id, 222.0, "Travel", _iso(today.replace(day=1)), "FIRST-ITEM")
        _add_expense(user_id, 333.0, "Bills", _iso(last_month_end), "PREVMONTH-ITEM")
        _login(client, "presets@spendly.com")
        _, html = _get(client)
        href = _find_preset_href(html, "This Month")
        response = client.get(href)
        body = response.get_data(as_text=True)
        assert response.status_code == 200
        assert "TODAY-ITEM" in body
        assert "FIRST-ITEM" in body
        assert "PREVMONTH-ITEM" not in body
        assert "₹333.00" in body, "Total should be 111 + 222"
        assert "Bills" not in body, "Previous-month category excluded"

    @pytest.mark.parametrize(
        "label, inside_days, outside_days",
        [
            ("Last 3 Months", 30, 150),
            ("Last 6 Months", 150, 400),
        ],
    )
    def test_multi_month_presets_filter_by_window(
        self, app, client, label, inside_days, outside_days
    ):
        today = datetime.date.today()
        user_id = _new_user("window@spendly.com")
        _add_expense(user_id, 10.0, "Food", _iso(today), "NOW-ITEM")
        _add_expense(
            user_id, 20.0, "Food", _iso(today - datetime.timedelta(days=inside_days)),
            "INSIDE-ITEM",
        )
        _add_expense(
            user_id, 30.0, "Food", _iso(today - datetime.timedelta(days=outside_days)),
            "OUTSIDE-ITEM",
        )
        _login(client, "window@spendly.com")
        _, html = _get(client)
        href = _find_preset_href(html, label)
        body = client.get(href).get_data(as_text=True)
        assert "NOW-ITEM" in body
        assert "INSIDE-ITEM" in body
        assert "OUTSIDE-ITEM" not in body

    def test_active_preset_highlighted_all_time_by_default(self, logged_in):
        _, html = _get(logged_in)
        assert "active" in _find_preset_tag(html, "All Time").lower()
        assert "active" not in _find_preset_tag(html, "This Month").lower()

    def test_active_preset_highlighted_for_this_month(self, logged_in):
        _, html = _get(logged_in)
        href = _find_preset_href(html, "This Month")
        body = logged_in.get(href).get_data(as_text=True)
        assert "active" in _find_preset_tag(body, "This Month").lower()
        assert "active" not in _find_preset_tag(body, "All Time").lower()

    def test_no_preset_active_for_custom_range(self, logged_in):
        _, html = _get(logged_in, date_from="2025-02-01", date_to="2025-02-28")
        for label in ("This Month", "Last 3 Months", "Last 6 Months", "All Time"):
            assert "active" not in _find_preset_tag(html, label).lower(), (
                f"{label} should not be active for a custom range"
            )


# ---------------------------------------------------------------- DB helpers
class TestHelpers:
    def test_summary_stats_respects_range(self, ranged):
        stats = db_module.get_summary_stats(ranged, "2025-02-01", "2025-02-28")
        assert stats["total_spent"] == 500.0
        assert stats["transaction_count"] == 2
        assert stats["top_category"] == "Bills"
        assert stats["top_category_total"] == 300.0

    def test_summary_stats_inclusive_bounds(self, ranged):
        stats = db_module.get_summary_stats(ranged, "2025-02-28", "2025-03-01")
        assert stats["transaction_count"] == 2
        assert stats["total_spent"] == 700.0

    def test_recent_transactions_respects_range_and_order(self, ranged):
        rows = db_module.get_recent_transactions(
            ranged, date_from="2025-02-01", date_to="2025-03-01"
        )
        assert [r["date"] for r in rows] == ["2025-03-01", "2025-02-28", "2025-02-15"]

    def test_recent_transactions_limit_still_applies(self, ranged):
        rows = db_module.get_recent_transactions(
            ranged, limit=2, date_from="2025-01-01", date_to="2025-12-31"
        )
        assert len(rows) == 2
        assert rows[0]["date"] == "2025-03-01"

    def test_category_breakdown_respects_range_and_percentages(self, ranged):
        rows = db_module.get_category_breakdown(ranged, "2025-02-01", "2025-02-28")
        by_name = {r["name"]: r for r in rows}
        assert set(by_name) == {"Food", "Bills"}
        assert by_name["Food"]["total"] == 200.0
        assert by_name["Bills"]["total"] == 300.0
        assert by_name["Food"]["percent"] == 40
        assert by_name["Bills"]["percent"] == 60
        assert sum(r["percent"] for r in rows) == 100

    def test_helpers_only_return_own_user_in_range(self, ranged):
        other = _new_user("other2@spendly.com")
        _add_expense(other, 999.0, "Health", "2025-02-10", "OTHER")
        stats = db_module.get_summary_stats(ranged, "2025-02-01", "2025-02-28")
        assert stats["total_spent"] == 500.0
        rows = db_module.get_recent_transactions(
            ranged, date_from="2025-02-01", date_to="2025-02-28"
        )
        assert all(r["description"] != "OTHER" for r in rows)

    def test_sql_injection_in_dates_is_harmless(self, ranged):
        stats = db_module.get_summary_stats(ranged, "' OR 1=1 --", "2025-12-31")
        assert isinstance(stats["total_spent"], float)
        assert _expense_count(ranged) == 4


# ---------------------------------------------------------------- DB side effects
class TestNoSideEffects:
    def test_filtering_does_not_modify_expenses(self, logged_in, ranged):
        _get(logged_in, date_from="2025-02-01", date_to="2025-02-28")
        _get(logged_in, date_from="2025-03-01", date_to="2025-01-01")
        _get(logged_in, date_from="bad")
        assert _expense_count(ranged) == 4
