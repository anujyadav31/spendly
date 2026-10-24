"""Tests for Step 9: POST /expenses/<id>/delete (spec: 09-delete-expense.md).

Approved deviations from the spec text that these tests encode:
- helper is database.db.delete_expense(expense_id, user_id) -> bool, never raises
- form action built with url_for; loop variable is `expense`
- no inline style=/onsubmit; form has class="tx-delete-form" and data-confirm,
  button has class="btn-delete"; static/js/main.js calls confirm(
- success flashes "Expense deleted" on /profile
- guard also redirects to /login when the session's user no longer exists
"""

import re

import pytest

import database.db as db_module

DEMO_EMAIL = "demo@spendly.com"
DEMO_PASSWORD = "demo123"
OTHER_EMAIL = "other@spendly.com"
OTHER_PASSWORD = "secret123"


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


def _url(expense_id):
    return f"/expenses/{expense_id}/delete"


def _delete_forms(html):
    return re.findall(r'<form\b[^>]*class="tx-delete-form"[^>]*>', html)


def _edit_links(html):
    return re.findall(r'href="/expenses/\d+/edit"', html)


@pytest.fixture
def logged_in(client, app):
    _login(client)
    return client


@pytest.fixture
def target_id(app):
    """A known expense owned by the demo user."""
    db_module.create_expense(
        _user_id(DEMO_EMAIL), 100.0, "Food", "2025-02-10", "DELETETARGET"
    )
    return _id_by_description("DELETETARGET")


@pytest.fixture
def other_user(app):
    return db_module.create_user("Other User", OTHER_EMAIL, OTHER_PASSWORD)


@pytest.fixture
def other_expense_id(other_user):
    db_module.create_expense(other_user, 55.5, "Bills", "2025-01-15", "OTHERSECRET")
    return _id_by_description("OTHERSECRET")


# ---------------------------------------------------------------- DB helper
class TestDeleteExpenseHelper:
    def test_own_row_removed_and_returns_true(self, app, target_id):
        # Spec unit test: valid id + correct user -> row removed
        assert db_module.delete_expense(target_id, _user_id(DEMO_EMAIL)) is True
        assert _row_by_id(target_id) is None

    def test_removes_exactly_one_row(self, app, target_id):
        before = _count_all()
        db_module.delete_expense(target_id, _user_id(DEMO_EMAIL))
        assert _count_all() == before - 1

    def test_wrong_user_returns_false_and_keeps_row(self, app, target_id, other_user):
        # Spec unit test: wrong user -> row remains, no error
        assert db_module.delete_expense(target_id, other_user) is False
        assert _row_by_id(target_id) is not None

    def test_unknown_user_returns_false_without_raising(self, app, target_id):
        assert db_module.delete_expense(target_id, 999999) is False
        assert _row_by_id(target_id) is not None

    def test_missing_id_returns_false_and_db_unchanged(self, app):
        # Spec unit test: non-existent id -> no error, DB unchanged
        before = _count_all()
        assert db_module.delete_expense(999999, _user_id(DEMO_EMAIL)) is False
        assert _count_all() == before

    def test_other_rows_untouched(self, app, target_id):
        uid = _user_id(DEMO_EMAIL)
        db_module.create_expense(uid, 5.0, "Other", "2025-02-11", "SIBLING")
        sibling = _id_by_description("SIBLING")
        sibling_before = tuple(_row_by_id(sibling))
        db_module.delete_expense(target_id, uid)
        assert tuple(_row_by_id(sibling)) == sibling_before

    def test_second_delete_returns_false(self, app, target_id):
        uid = _user_id(DEMO_EMAIL)
        assert db_module.delete_expense(target_id, uid) is True
        assert db_module.delete_expense(target_id, uid) is False

    def test_sql_injection_like_ids_do_not_raise(self, app, target_id):
        # Parameterised query: odd values must be handled safely
        result = db_module.delete_expense("1 OR 1=1", _user_id(DEMO_EMAIL))
        assert result is False
        assert _row_by_id(target_id) is not None


# ---------------------------------------------------------------- auth guard
class TestAuthGuard:
    def test_signed_out_redirects_to_login_and_keeps_row(self, client, target_id):
        response = client.post(_url(target_id))
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]
        assert _row_by_id(target_id) is not None

    def test_signed_out_nonexistent_id_redirects_not_404(self, client, app):
        response = client.post(_url(999999))
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_session_user_no_longer_exists_redirects_to_login(self, client, app):
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
        response = client.post(_url(first_id))
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]


# ---------------------------------------------------------------- route
class TestDeleteRoute:
    def test_own_expense_redirects_to_profile(self, logged_in, target_id):
        response = logged_in.post(_url(target_id))
        assert response.status_code == 302
        assert "/profile" in response.headers["Location"]

    def test_own_expense_row_removed_exactly_one(self, logged_in, target_id):
        before = _count_all()
        logged_in.post(_url(target_id))
        assert _row_by_id(target_id) is None, "Row should be gone"
        assert _count_all() == before - 1

    def test_redirect_shows_flash_and_hides_deleted_expense(self, logged_in, target_id):
        page = logged_in.get("/profile").get_data(as_text=True)
        assert "DELETETARGET" in page, "Precondition: row visible before delete"
        response = logged_in.post(_url(target_id), follow_redirects=True)
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "Expense deleted" in html, "Expected success flash"
        assert "DELETETARGET" not in html

    def test_profile_row_count_drops_by_one(self, client, other_user):
        for i in range(3):
            db_module.create_expense(
                other_user, 10.0 + i, "Food", f"2025-01-1{i}", f"CNT{i}"
            )
        _login(client, OTHER_EMAIL, OTHER_PASSWORD)
        before = len(_delete_forms(client.get("/profile").get_data(as_text=True)))
        assert before == 3
        client.post(_url(_id_by_description("CNT1")))
        after = len(_delete_forms(client.get("/profile").get_data(as_text=True)))
        assert after == before - 1

    def test_no_flash_on_failed_delete(self, logged_in, other_expense_id):
        logged_in.post(_url(other_expense_id))
        html = logged_in.get("/profile").get_data(as_text=True)
        assert "Expense deleted" not in html

    def test_other_users_expense_404_and_kept(self, logged_in, other_expense_id):
        before = tuple(_row_by_id(other_expense_id))
        response = logged_in.post(_url(other_expense_id))
        assert response.status_code == 404
        assert tuple(_row_by_id(other_expense_id)) == before

    def test_nonexistent_id_404(self, logged_in):
        assert logged_in.post(_url(999999)).status_code == 404

    def test_second_delete_is_404(self, logged_in, target_id):
        assert logged_in.post(_url(target_id)).status_code == 302
        assert logged_in.post(_url(target_id)).status_code == 404

    def test_non_integer_id_404(self, logged_in):
        assert logged_in.post("/expenses/abc/delete").status_code == 404

    @pytest.mark.parametrize("method", ["get", "put", "patch", "delete"])
    def test_non_post_methods_405_and_keep_row(self, logged_in, target_id, method):
        response = getattr(logged_in, method)(_url(target_id))
        assert response.status_code == 405
        assert _row_by_id(target_id) is not None

    def test_get_405_when_signed_out_not_deleting(self, client, target_id):
        response = client.get(_url(target_id))
        assert response.status_code in (302, 405)
        assert _row_by_id(target_id) is not None

    def test_url_for_builds_expected_path(self, app):
        from flask import url_for

        with app.test_request_context():
            assert url_for("delete_expense", id=5) == "/expenses/5/delete"


# ---------------------------------------------------------------- profile template
class TestProfileTemplate:
    def test_delete_form_posts_to_delete_url(self, logged_in, target_id):
        html = logged_in.get("/profile").get_data(as_text=True)
        pattern = (
            r'<form\b(?=[^>]*method="post")(?=[^>]*action="%s")[^>]*>'
            % re.escape(_url(target_id))
        )
        match = re.search(pattern, html, re.IGNORECASE)
        assert match, "Expected a POST delete form for the expense"
        tag = match.group(0)
        assert 'class="tx-delete-form"' in tag
        assert re.search(r'data-confirm="[^"]+"', tag), "Expected data-confirm text"

    def test_delete_button_markup(self, logged_in, target_id):
        html = logged_in.get("/profile").get_data(as_text=True)
        assert re.search(
            r'<button\b[^>]*class="btn-delete"[^>]*>\s*Delete\s*</button>', html
        ), "Expected a btn-delete button labelled Delete"
        assert re.search(
            r'<button\b(?=[^>]*type="submit")(?=[^>]*class="btn-delete")[^>]*>', html
        ), "Delete button should be a submit button"

    def test_every_row_has_edit_link_and_delete_form(self, logged_in, app):
        html = logged_in.get("/profile").get_data(as_text=True)
        forms = _delete_forms(html)
        assert forms, "Seeded demo user should have rows"
        assert len(forms) == len(_edit_links(html)), "Edit and Delete per row"

    def test_edit_link_remains(self, logged_in, target_id):
        html = logged_in.get("/profile").get_data(as_text=True)
        assert f"/expenses/{target_id}/edit" in html

    def test_no_inline_handlers_or_styles(self, logged_in, target_id):
        html = logged_in.get("/profile").get_data(as_text=True)
        assert "onsubmit=" not in html, "No inline onsubmit"
        assert "onclick=" not in html, "No inline onclick"
        assert "style=" not in html, "No inline style attributes"

    def test_other_users_expense_not_exposed(self, logged_in, other_expense_id):
        html = logged_in.get("/profile").get_data(as_text=True)
        assert _url(other_expense_id) not in html
        assert "OTHERSECRET" not in html

    def test_empty_state_has_no_delete_forms(self, client, other_user):
        _login(client, OTHER_EMAIL, OTHER_PASSWORD)
        html = client.get("/profile").get_data(as_text=True)
        assert "No expenses yet." in html
        assert _delete_forms(html) == []


# ---------------------------------------------------------------- static JS
class TestStaticJs:
    def test_main_js_has_confirm_listener(self, client):
        response = client.get("/static/js/main.js")
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        response.close()
        assert "data-confirm" in body, "Listener should read data-confirm"
        assert "confirm(" in body, "Listener should call confirm("
