"""Tests for Step 8: GET/POST /expenses/<id>/edit (spec: 08-edit-expense.md)."""

import datetime
import re

import pytest

import database.db as db_module

DEMO_EMAIL = "demo@spendly.com"
DEMO_PASSWORD = "demo123"
OTHER_EMAIL = "other@spendly.com"
OTHER_PASSWORD = "secret123"

ERR_AMOUNT = "Please enter an amount greater than zero."
ERR_CATEGORY = "Please choose a valid category."
ERR_DATE = "Please enter a valid date (not in the future)."
ERR_DESC = "Description must be 200 characters or fewer."

TODAY = datetime.date.today().isoformat()
TOMORROW = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()

ORIG = {
    "amount": 100.0,
    "category": "Food",
    "date": "2025-02-10",
    "description": "EDITTARGET",
}


# ---------------------------------------------------------------- helpers
def _login(client, email=DEMO_EMAIL, password=DEMO_PASSWORD):
    return client.post("/login", data={"email": email, "password": password})


def _user_id(email):
    conn = db_module.get_db()
    try:
        return conn.execute(
            "SELECT id FROM users WHERE email = ?", (email,)
        ).fetchone()[0]
    finally:
        conn.close()


def _count_all():
    conn = db_module.get_db()
    try:
        return conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
    finally:
        conn.close()


def _row_by_id(expense_id):
    conn = db_module.get_db()
    try:
        return conn.execute(
            "SELECT * FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()
    finally:
        conn.close()


def _id_by_description(description):
    conn = db_module.get_db()
    try:
        rows = conn.execute(
            "SELECT id FROM expenses WHERE description = ?", (description,)
        ).fetchall()
    finally:
        conn.close()
    assert len(rows) == 1, f"Expected exactly one expense '{description}'"
    return rows[0][0]


def _category_total(user_id, category):
    conn = db_module.get_db()
    try:
        return conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM expenses "
            "WHERE user_id = ? AND category = ?",
            (user_id, category),
        ).fetchone()[0]
    finally:
        conn.close()


def _user_total(user_id):
    conn = db_module.get_db()
    try:
        return conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE user_id = ?",
            (user_id,),
        ).fetchone()[0]
    finally:
        conn.close()


def _user_count(user_id):
    conn = db_module.get_db()
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM expenses WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
    finally:
        conn.close()


def _snapshot(expense_id):
    row = _row_by_id(expense_id)
    return None if row is None else tuple(row)


def _url(expense_id):
    return f"/expenses/{expense_id}/edit"


def _form(**overrides):
    data = {
        "amount": "250.75",
        "category": "Transport",
        "date": "2025-03-04",
        "description": "EDITED",
    }
    data.update(overrides)
    return {k: v for k, v in data.items() if v is not None}


def _selected(html, category):
    return re.search(
        r'<option[^>]*value="%s"[^>]*selected|'
        r'<option[^>]*selected[^>]*value="%s"'
        % (re.escape(category), re.escape(category)),
        html,
    )


@pytest.fixture
def logged_in(client, app):
    _login(client)
    return client


@pytest.fixture
def target_id(app):
    """A known expense owned by the demo user."""
    db_module.create_expense(
        _user_id(DEMO_EMAIL),
        ORIG["amount"],
        ORIG["category"],
        ORIG["date"],
        ORIG["description"],
    )
    return _id_by_description(ORIG["description"])


@pytest.fixture
def other_user(app):
    return db_module.create_user("Other User", OTHER_EMAIL, OTHER_PASSWORD)


@pytest.fixture
def other_expense_id(other_user):
    db_module.create_expense(other_user, 55.5, "Bills", "2025-01-15", "OTHERSECRET")
    return _id_by_description("OTHERSECRET")


# ---------------------------------------------------------------- auth guard
class TestAuthGuard:
    def test_get_signed_out_redirects_to_login(self, client, target_id):
        response = client.get(_url(target_id))
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_post_signed_out_redirects_and_changes_nothing(self, client, target_id):
        before = _snapshot(target_id)
        response = client.post(_url(target_id), data=_form())
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]
        assert _snapshot(target_id) == before

    def test_signed_out_nonexistent_id_redirects_not_404(self, client, app):
        response = client.get(_url(999999))
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    @pytest.mark.parametrize("method", ["get", "post"])
    def test_session_user_deleted_redirects_and_clears_session(self, client, method):
        _login(client)
        uid = _user_id(DEMO_EMAIL)
        conn = db_module.get_db()
        try:
            first_id = conn.execute(
                "SELECT id FROM expenses WHERE user_id = ? LIMIT 1", (uid,)
            ).fetchone()[0]
            conn.execute("DELETE FROM expenses WHERE user_id = ?", (uid,))
            conn.execute("DELETE FROM users WHERE id = ?", (uid,))
            conn.commit()
        finally:
            conn.close()
        if method == "post":
            response = client.post(_url(first_id), data=_form())
        else:
            response = client.get(_url(first_id))
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]
        with client.session_transaction() as sess:
            assert "user_id" not in sess, "Session should be cleared"


# ---------------------------------------------------------------- GET form
class TestForm:
    def test_get_returns_200(self, logged_in, target_id):
        assert logged_in.get(_url(target_id)).status_code == 200

    def test_title_and_submit_label(self, logged_in, target_id):
        html = logged_in.get(_url(target_id)).get_data(as_text=True)
        assert "Edit expense" in html
        assert "Save changes" in html

    def test_form_posts_to_edit_url(self, logged_in, target_id):
        html = logged_in.get(_url(target_id)).get_data(as_text=True)
        match = re.search(r"<form\b[^>]*>", html)
        assert match, "Expected a form"
        tag = match.group(0)
        assert f'action="{_url(target_id)}"' in tag
        assert re.search(r'method="post"', tag, re.IGNORECASE)

    def test_fields_prefilled_with_current_values(self, logged_in, target_id):
        html = logged_in.get(_url(target_id)).get_data(as_text=True)
        amount_tag = re.search(r'<input\b[^>]*name="amount"[^>]*>', html).group(0)
        assert re.search(r'value="100(\.0+)?"', amount_tag), amount_tag
        assert f'value="{ORIG["date"]}"' in html
        assert f'value="{ORIG["description"]}"' in html
        assert _selected(html, "Food"), "Current category should be selected"

    def test_prefill_reflects_non_default_category(self, logged_in, app):
        db_module.create_expense(
            _user_id(DEMO_EMAIL), 12.0, "Health", "2025-04-01", "HEALTHROW"
        )
        eid = _id_by_description("HEALTHROW")
        html = logged_in.get(_url(eid)).get_data(as_text=True)
        assert _selected(html, "Health")
        assert not _selected(html, "Food")

    def test_null_description_renders_empty(self, logged_in, app):
        db_module.create_expense(_user_id(DEMO_EMAIL), 9.0, "Other", "2025-04-02", "")
        conn = db_module.get_db()
        try:
            eid = conn.execute(
                "SELECT id FROM expenses WHERE date = ? AND amount = ?",
                ("2025-04-02", 9.0),
            ).fetchone()[0]
        finally:
            conn.close()
        response = logged_in.get(_url(eid))
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "None" not in html, "NULL description must not render as None"

    def test_all_categories_in_dropdown(self, logged_in, target_id):
        html = logged_in.get(_url(target_id)).get_data(as_text=True)
        for category in db_module.CATEGORIES:
            assert re.search(
                r'<option[^>]*value="%s"' % re.escape(category), html
            ), f"Missing category option {category}"

    def test_date_input_max_is_today(self, logged_in, target_id):
        html = logged_in.get(_url(target_id)).get_data(as_text=True)
        tag = re.search(r'<input\b[^>]*name="date"[^>]*>', html).group(0)
        assert f'max="{TODAY}"' in tag

    def test_cancel_link_points_to_profile(self, logged_in, target_id):
        html = logged_in.get(_url(target_id)).get_data(as_text=True)
        assert re.search(
            r'<a\b[^>]*href="/profile"[^>]*>\s*Cancel\s*</a>', html
        ), "Expected Cancel link to /profile"

    def test_no_error_block_on_fresh_get(self, logged_in, target_id):
        html = logged_in.get(_url(target_id)).get_data(as_text=True)
        for msg in (ERR_AMOUNT, ERR_CATEGORY, ERR_DATE, ERR_DESC):
            assert msg not in html

    def test_page_has_no_dollar_or_inline_style(self, logged_in, target_id):
        html = logged_in.get(_url(target_id)).get_data(as_text=True)
        assert "$" not in html
        assert "<style" not in html
        assert 'style="' not in html

    def test_get_does_not_modify_expense(self, logged_in, target_id):
        before = _snapshot(target_id)
        logged_in.get(_url(target_id))
        assert _snapshot(target_id) == before


# ---------------------------------------------------------------- happy path
class TestValidPost:
    def test_redirects_to_profile(self, logged_in, target_id):
        response = logged_in.post(_url(target_id), data=_form())
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/profile")

    def test_row_updated_in_db(self, logged_in, target_id):
        logged_in.post(_url(target_id), data=_form())
        row = _row_by_id(target_id)
        assert float(row["amount"]) == pytest.approx(250.75)
        assert row["category"] == "Transport"
        assert row["date"] == "2025-03-04"
        assert row["description"] == "EDITED"
        assert row["user_id"] == _user_id(DEMO_EMAIL), "Owner unchanged"

    def test_edit_does_not_create_new_expense(self, logged_in, target_id):
        before = _count_all()
        logged_in.post(_url(target_id), data=_form())
        assert _count_all() == before

    def test_only_target_row_changes(self, logged_in, target_id):
        conn = db_module.get_db()
        try:
            others_before = [
                tuple(r)
                for r in conn.execute(
                    "SELECT * FROM expenses WHERE id != ? ORDER BY id", (target_id,)
                ).fetchall()
            ]
        finally:
            conn.close()
        logged_in.post(_url(target_id), data=_form())
        conn = db_module.get_db()
        try:
            others_after = [
                tuple(r)
                for r in conn.execute(
                    "SELECT * FROM expenses WHERE id != ? ORDER BY id", (target_id,)
                ).fetchall()
            ]
        finally:
            conn.close()
        assert others_after == others_before

    def test_flash_shown_after_redirect(self, logged_in, target_id):
        response = logged_in.post(_url(target_id), data=_form(), follow_redirects=True)
        assert response.status_code == 200
        assert "Expense updated" in response.get_data(as_text=True)

    def test_flash_uses_success_category(self, logged_in, target_id):
        logged_in.post(_url(target_id), data=_form())
        with logged_in.session_transaction() as sess:
            flashes = [tuple(f) for f in sess.get("_flashes", [])]
        assert ("success", "Expense updated") in flashes

    def test_new_amount_visible_on_profile_in_rupees(self, client, other_user):
        _login(client, OTHER_EMAIL, OTHER_PASSWORD)
        db_module.create_expense(other_user, 10.0, "Food", "2025-02-01", "SOLOROW")
        eid = _id_by_description("SOLOROW")
        response = client.post(
            _url(eid), data=_form(amount="4321.00"), follow_redirects=True
        )
        html = response.get_data(as_text=True)
        assert re.search(r"₹\s*4,?321", html), "Expected new ₹ amount"
        assert "$" not in html

    def test_amount_rounded_to_two_decimals(self, logged_in, target_id):
        logged_in.post(_url(target_id), data=_form(amount="10.126"))
        assert float(_row_by_id(target_id)["amount"]) == pytest.approx(10.13)

    def test_description_is_stripped(self, logged_in, target_id):
        logged_in.post(_url(target_id), data=_form(description="  PADDED  "))
        assert _row_by_id(target_id)["description"] == "PADDED"

    @pytest.mark.parametrize("desc", ["", "   ", None])
    def test_cleared_description_stored_as_null(self, logged_in, target_id, desc):
        response = logged_in.post(_url(target_id), data=_form(description=desc))
        assert response.status_code == 302
        assert _row_by_id(target_id)["description"] is None

    def test_cleared_description_profile_still_renders(self, client, other_user):
        _login(client, OTHER_EMAIL, OTHER_PASSWORD)
        db_module.create_expense(other_user, 10.0, "Food", "2025-02-01", "WILLCLEAR")
        eid = _id_by_description("WILLCLEAR")
        response = client.post(
            _url(eid), data=_form(description=""), follow_redirects=True
        )
        html = response.get_data(as_text=True)
        assert response.status_code == 200
        assert "No expenses yet." not in html
        assert "WILLCLEAR" not in html
        assert "None" not in html

    def test_description_of_exactly_200_chars_accepted(self, logged_in, target_id):
        desc = "d" * 200
        response = logged_in.post(_url(target_id), data=_form(description=desc))
        assert response.status_code == 302
        assert _row_by_id(target_id)["description"] == desc

    def test_max_amount_accepted(self, logged_in, target_id):
        response = logged_in.post(_url(target_id), data=_form(amount="10000000"))
        assert response.status_code == 302
        assert float(_row_by_id(target_id)["amount"]) == pytest.approx(1e7)

    def test_today_date_accepted(self, logged_in, target_id):
        response = logged_in.post(_url(target_id), data=_form(date=TODAY))
        assert response.status_code == 302
        assert _row_by_id(target_id)["date"] == TODAY

    @pytest.mark.parametrize("category", list(db_module.CATEGORIES))
    def test_every_category_accepted(self, logged_in, target_id, category):
        response = logged_in.post(_url(target_id), data=_form(category=category))
        assert response.status_code == 302
        assert _row_by_id(target_id)["category"] == category

    def test_resubmitting_same_values_succeeds(self, logged_in, target_id):
        response = logged_in.post(
            _url(target_id),
            data=_form(
                amount="100",
                category="Food",
                date=ORIG["date"],
                description=ORIG["description"],
            ),
        )
        assert response.status_code == 302

    def test_sql_injection_in_description_stored_literally(self, logged_in, target_id):
        payload = "x'); DROP TABLE expenses;--"
        before = _count_all()
        response = logged_in.post(_url(target_id), data=_form(description=payload))
        assert response.status_code == 302
        assert _count_all() == before
        assert _row_by_id(target_id)["description"] == payload


# ---------------------------------------------------------------- profile integration
class TestProfileIntegration:
    def test_every_row_has_edit_link(self, logged_in, app):
        uid = _user_id(DEMO_EMAIL)
        recent = db_module.get_recent_transactions(uid)
        assert recent, "Demo user should have seeded expenses"
        html = logged_in.get("/profile").get_data(as_text=True)
        for tx in recent:
            assert "id" in tx, "get_recent_transactions must return id"
            assert re.search(
                r'<a\b[^>]*href="/expenses/%d/edit"' % tx["id"], html
            ), f"Missing Edit link for expense {tx['id']}"

    def test_edit_link_text_and_aria_label(self, logged_in, target_id):
        html = logged_in.get("/profile").get_data(as_text=True)
        match = re.search(
            r'<a\b[^>]*href="/expenses/%d/edit"[^>]*>\s*Edit\s*</a>' % target_id, html
        )
        assert match, "Expected an 'Edit' link for the target expense"
        assert "aria-label=" in match.group(0)

    def test_actions_column_header_present(self, logged_in):
        html = logged_in.get("/profile").get_data(as_text=True)
        assert "Actions" in html

    def test_no_delete_link_on_profile(self, logged_in):
        html = logged_in.get("/profile").get_data(as_text=True)
        assert "/delete" not in html, "Delete belongs to Step 9"

    def test_empty_state_text_kept(self, client, other_user):
        _login(client, OTHER_EMAIL, OTHER_PASSWORD)
        html = client.get("/profile").get_data(as_text=True)
        assert "No expenses yet." in html
        assert re.search(r'colspan="5"', html), "Empty-state colspan is 5"

    def test_other_users_edit_links_not_on_my_profile(
        self, logged_in, other_expense_id
    ):
        html = logged_in.get("/profile").get_data(as_text=True)
        assert f"/expenses/{other_expense_id}/edit" not in html

    def test_edit_link_leads_to_prefilled_form(self, logged_in, target_id):
        html = logged_in.get("/profile").get_data(as_text=True)
        href = re.search(r'href="(/expenses/%d/edit)"' % target_id, html).group(1)
        response = logged_in.get(href)
        assert response.status_code == 200
        assert ORIG["description"] in response.get_data(as_text=True)

    def test_totals_and_category_move_after_category_change(self, logged_in, target_id):
        uid = _user_id(DEMO_EMAIL)
        food_before = _category_total(uid, "Food")
        shop_before = _category_total(uid, "Shopping")
        total_before = _user_total(uid)
        count_before = _user_count(uid)

        logged_in.post(_url(target_id), data=_form(amount="100", category="Shopping"))

        assert _category_total(uid, "Food") == pytest.approx(food_before - 100)
        assert _category_total(uid, "Shopping") == pytest.approx(shop_before + 100)
        assert _user_total(uid) == pytest.approx(total_before)
        assert _user_count(uid) == count_before

        breakdown = db_module.get_category_breakdown(uid)
        assert breakdown, "Breakdown should be non-empty"
        assert logged_in.get("/profile").status_code == 200

    def test_total_spent_reflects_amount_change(self, logged_in, target_id):
        uid = _user_id(DEMO_EMAIL)
        total_before = _user_total(uid)
        logged_in.post(_url(target_id), data=_form(amount="600", category="Food"))
        assert _user_total(uid) == pytest.approx(total_before + 500)

    def test_edited_amount_shown_in_recent_transactions(self, logged_in, target_id):
        uid = _user_id(DEMO_EMAIL)
        logged_in.post(
            _url(target_id), data=_form(amount="777.25", description="RENAMEDROW")
        )
        recent = db_module.get_recent_transactions(uid)
        match = [t for t in recent if t["id"] == target_id]
        assert match, "Edited expense should be in recent transactions"
        assert match[0]["description"] == "RENAMEDROW"
        assert float(match[0]["amount"]) == pytest.approx(777.25)

    def test_edited_date_respects_profile_date_filter(self, client, other_user):
        _login(client, OTHER_EMAIL, OTHER_PASSWORD)
        db_module.create_expense(other_user, 10.0, "Food", "2025-03-04", "FILTERROW")
        eid = _id_by_description("FILTERROW")
        client.post(_url(eid), data=_form(date="2025-05-05", description="FILTERROW"))
        in_old = client.get(
            "/profile?date_from=2025-03-01&date_to=2025-03-31"
        ).get_data(as_text=True)
        in_new = client.get(
            "/profile?date_from=2025-05-01&date_to=2025-05-31"
        ).get_data(as_text=True)
        assert "FILTERROW" not in in_old
        assert "FILTERROW" in in_new


# ---------------------------------------------------------------- validation
INVALID_CASES = [
    pytest.param({"amount": "0"}, ERR_AMOUNT, id="amount-zero"),
    pytest.param({"amount": "-5"}, ERR_AMOUNT, id="amount-negative"),
    pytest.param({"amount": "abc"}, ERR_AMOUNT, id="amount-non-numeric"),
    pytest.param({"amount": None}, ERR_AMOUNT, id="amount-missing"),
    pytest.param({"amount": ""}, ERR_AMOUNT, id="amount-empty"),
    pytest.param({"amount": "10000000.01"}, ERR_AMOUNT, id="amount-too-large"),
    pytest.param({"amount": "nan"}, ERR_AMOUNT, id="amount-nan"),
    pytest.param({"amount": "inf"}, ERR_AMOUNT, id="amount-inf"),
    pytest.param({"category": "Travel"}, ERR_CATEGORY, id="category-invalid"),
    pytest.param({"category": "food"}, ERR_CATEGORY, id="category-wrong-case"),
    pytest.param({"category": ""}, ERR_CATEGORY, id="category-empty"),
    pytest.param({"category": None}, ERR_CATEGORY, id="category-missing"),
    pytest.param({"date": TOMORROW}, ERR_DATE, id="date-future"),
    pytest.param({"date": "2999-01-01"}, ERR_DATE, id="date-far-future"),
    pytest.param({"date": "04/03/2025"}, ERR_DATE, id="date-malformed-slash"),
    pytest.param({"date": "not-a-date"}, ERR_DATE, id="date-garbage"),
    pytest.param({"date": "2025-02-30"}, ERR_DATE, id="date-impossible"),
    pytest.param({"date": ""}, ERR_DATE, id="date-empty"),
    pytest.param({"date": None}, ERR_DATE, id="date-missing"),
    pytest.param({"description": "x" * 201}, ERR_DESC, id="description-201"),
    pytest.param({"description": "x" * 1000}, ERR_DESC, id="description-1000"),
]


class TestValidationErrors:
    @pytest.mark.parametrize("overrides, message", INVALID_CASES)
    def test_invalid_returns_400_with_error_and_no_change(
        self, logged_in, target_id, overrides, message
    ):
        before = _snapshot(target_id)
        count = _count_all()
        response = logged_in.post(_url(target_id), data=_form(**overrides))
        assert response.status_code == 400, "Validation errors must be 400"
        assert message in response.get_data(as_text=True)
        assert _snapshot(target_id) == before, "Stored expense must not change"
        assert _count_all() == count

    def test_error_block_rendered(self, logged_in, target_id):
        html = logged_in.post(_url(target_id), data=_form(amount="0")).get_data(
            as_text=True
        )
        assert "auth-error" in html

    def test_amount_error_keeps_other_submitted_values(self, logged_in, target_id):
        html = logged_in.post(
            _url(target_id),
            data=_form(
                amount="0", category="Health", date="2025-05-06", description="KEEPME"
            ),
        ).get_data(as_text=True)
        assert 'value="0"' in html, "Submitted amount should be kept"
        assert 'value="2025-05-06"' in html
        assert 'value="KEEPME"' in html
        assert _selected(html, "Health"), "Submitted category should be kept"
        assert (
            ORIG["description"] not in html
        ), "Stored values must not override submitted ones"

    def test_non_numeric_amount_repopulated(self, logged_in, target_id):
        html = logged_in.post(_url(target_id), data=_form(amount="abc")).get_data(
            as_text=True
        )
        assert 'value="abc"' in html

    def test_date_error_keeps_submitted_values(self, logged_in, target_id):
        html = logged_in.post(
            _url(target_id),
            data=_form(
                date=TOMORROW,
                amount="33.25",
                category="Bills",
                description="FUTUREDESC",
            ),
        ).get_data(as_text=True)
        assert 'value="33.25"' in html
        assert f'value="{TOMORROW}"' in html
        assert 'value="FUTUREDESC"' in html
        assert _selected(html, "Bills")

    def test_description_error_keeps_description(self, logged_in, target_id):
        desc = "y" * 201
        html = logged_in.post(_url(target_id), data=_form(description=desc)).get_data(
            as_text=True
        )
        assert desc in html

    def test_error_response_form_still_targets_edit_url(self, logged_in, target_id):
        html = logged_in.post(_url(target_id), data=_form(amount="0")).get_data(
            as_text=True
        )
        assert f'action="{_url(target_id)}"' in html
        assert 'name="amount"' in html

    def test_only_first_error_shown(self, logged_in, target_id):
        html = logged_in.post(
            _url(target_id), data=_form(amount="0", category="Bogus")
        ).get_data(as_text=True)
        assert ERR_AMOUNT in html
        assert ERR_CATEGORY not in html

    def test_error_does_not_flash_success(self, logged_in, target_id):
        logged_in.post(_url(target_id), data=_form(amount="0"))
        with logged_in.session_transaction() as sess:
            flashes = [tuple(f) for f in sess.get("_flashes", [])]
        assert ("success", "Expense updated") not in flashes

    def test_xss_in_description_escaped_on_error_rerender(self, logged_in, target_id):
        payload = "<script>alert(1)</script>" + "x" * 200
        html = logged_in.post(
            _url(target_id), data=_form(description=payload)
        ).get_data(as_text=True)
        assert "<script>alert(1)</script>" not in html


# ---------------------------------------------------------------- ownership / 404
class TestOwnershipAndNotFound:
    def test_get_nonexistent_id_returns_404(self, logged_in):
        assert logged_in.get(_url(999999)).status_code == 404

    def test_post_nonexistent_id_returns_404(self, logged_in):
        before = _count_all()
        assert logged_in.post(_url(999999), data=_form()).status_code == 404
        assert _count_all() == before

    def test_get_other_users_expense_returns_404(self, logged_in, other_expense_id):
        response = logged_in.get(_url(other_expense_id))
        assert response.status_code == 404
        assert "OTHERSECRET" not in response.get_data(as_text=True)

    def test_post_other_users_expense_returns_404_and_unchanged(
        self, logged_in, other_expense_id
    ):
        before = _snapshot(other_expense_id)
        response = logged_in.post(_url(other_expense_id), data=_form())
        assert response.status_code == 404
        assert _snapshot(other_expense_id) == before

    def test_invalid_post_to_other_users_expense_still_404(
        self, logged_in, other_expense_id
    ):
        response = logged_in.post(_url(other_expense_id), data=_form(amount="0"))
        assert response.status_code == 404, "Must not reveal id existence"

    def test_other_and_missing_responses_are_indistinguishable(
        self, logged_in, other_expense_id
    ):
        other = logged_in.get(_url(other_expense_id))
        missing = logged_in.get(_url(999999))
        assert other.status_code == missing.status_code == 404
        assert other.get_data() == missing.get_data()

    def test_user_id_form_field_cannot_steal_expense(
        self, logged_in, other_user, other_expense_id
    ):
        before = _snapshot(other_expense_id)
        data = _form()
        data["user_id"] = str(other_user)
        response = logged_in.post(_url(other_expense_id), data=data)
        assert response.status_code == 404
        assert _snapshot(other_expense_id) == before

    def test_user_id_form_field_cannot_reassign_own_expense(
        self, logged_in, target_id, other_user
    ):
        data = _form()
        data["user_id"] = str(other_user)
        logged_in.post(_url(target_id), data=data)
        assert _row_by_id(target_id)["user_id"] == _user_id(DEMO_EMAIL)

    def test_other_user_can_edit_own_expense(self, client, other_expense_id):
        _login(client, OTHER_EMAIL, OTHER_PASSWORD)
        response = client.post(
            _url(other_expense_id), data=_form(description="OTHERNEW")
        )
        assert response.status_code == 302
        assert _row_by_id(other_expense_id)["description"] == "OTHERNEW"

    def test_demo_cannot_edit_after_switching_users(
        self, client, target_id, other_user
    ):
        _login(client, OTHER_EMAIL, OTHER_PASSWORD)
        before = _snapshot(target_id)
        assert client.get(_url(target_id)).status_code == 404
        assert client.post(_url(target_id), data=_form()).status_code == 404
        assert _snapshot(target_id) == before

    def test_non_integer_id_returns_404(self, logged_in):
        assert logged_in.get("/expenses/abc/edit").status_code == 404


# ---------------------------------------------------------------- db helpers
class TestDbHelpers:
    def test_get_expense_by_id_returns_expected_shape(self, target_id):
        uid = _user_id(DEMO_EMAIL)
        result = db_module.get_expense_by_id(target_id, uid)
        assert result is not None
        for key in ("id", "amount", "category", "date", "description"):
            assert key in result, f"Missing key {key}"
        assert result["id"] == target_id
        assert isinstance(result["amount"], float)
        assert result["amount"] == pytest.approx(100.0)
        assert result["category"] == "Food"
        assert result["date"] == ORIG["date"]
        assert result["description"] == ORIG["description"]

    def test_get_expense_by_id_wrong_user_returns_none(self, target_id, other_user):
        assert db_module.get_expense_by_id(target_id, other_user) is None

    def test_get_expense_by_id_missing_returns_none(self, app):
        assert db_module.get_expense_by_id(999999, _user_id(DEMO_EMAIL)) is None

    def test_get_expense_by_id_null_description_is_empty_string(self, app):
        uid = _user_id(DEMO_EMAIL)
        db_module.create_expense(uid, 3.0, "Other", "2025-06-06", "")
        conn = db_module.get_db()
        try:
            eid = conn.execute(
                "SELECT id FROM expenses WHERE date = ? AND user_id = ?",
                ("2025-06-06", uid),
            ).fetchone()[0]
        finally:
            conn.close()
        assert db_module.get_expense_by_id(eid, uid)["description"] == ""

    def test_update_expense_success_returns_true_and_persists(self, target_id):
        uid = _user_id(DEMO_EMAIL)
        assert (
            db_module.update_expense(
                target_id, uid, 42.5, "Bills", "2025-07-07", "NEWDESC"
            )
            is True
        )
        row = _row_by_id(target_id)
        assert float(row["amount"]) == pytest.approx(42.5)
        assert row["category"] == "Bills"
        assert row["date"] == "2025-07-07"
        assert row["description"] == "NEWDESC"

    def test_update_expense_empty_description_stored_as_null(self, target_id):
        uid = _user_id(DEMO_EMAIL)
        db_module.update_expense(target_id, uid, 1.0, "Food", "2025-07-07", "")
        assert _row_by_id(target_id)["description"] is None

    def test_update_expense_wrong_user_returns_false_and_unchanged(
        self, target_id, other_user
    ):
        before = _snapshot(target_id)
        assert (
            db_module.update_expense(
                target_id, other_user, 1.0, "Food", "2025-07-07", "HACK"
            )
            is False
        )
        assert _snapshot(target_id) == before

    def test_update_expense_missing_returns_false(self, app):
        assert (
            db_module.update_expense(
                999999, _user_id(DEMO_EMAIL), 1.0, "Food", "2025-07-07", "x"
            )
            is False
        )


# ---------------------------------------------------------------- misc
class TestMisc:
    def test_delete_route_still_a_step9_stub(self, logged_in, target_id):
        before = _snapshot(target_id)
        logged_in.get(f"/expenses/{target_id}/delete")
        assert _snapshot(target_id) == before, "Delete must not be implemented"

    def test_cancel_flow_changes_nothing(self, logged_in, target_id):
        before = _snapshot(target_id)
        assert logged_in.get(_url(target_id)).status_code == 200
        assert logged_in.get("/profile").status_code == 200
        assert _snapshot(target_id) == before

    def test_edit_endpoint_url_is_stable(self, app, target_id):
        from flask import url_for

        with app.test_request_context():
            assert url_for("edit_expense", id=target_id) == _url(target_id)
