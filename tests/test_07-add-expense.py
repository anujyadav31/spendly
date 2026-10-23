"""Tests for Step 7: GET/POST /expenses/add."""
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


def _rows_by_description(description):
    conn = db_module.get_db()
    try:
        return conn.execute(
            "SELECT * FROM expenses WHERE description = ?", (description,)
        ).fetchall()
    finally:
        conn.close()


def _form(**overrides):
    data = {
        "amount": "12.50",
        "category": "Food",
        "date": TODAY,
        "description": "UNIQUEITEM",
    }
    data.update(overrides)
    return {k: v for k, v in data.items() if v is not None}


@pytest.fixture
def logged_in(client, app):
    _login(client)
    return client


@pytest.fixture
def other_user(app):
    return db_module.create_user("Other User", OTHER_EMAIL, OTHER_PASSWORD)


# ---------------------------------------------------------------- auth guard
class TestAuthGuard:
    def test_get_signed_out_redirects_to_login(self, client):
        response = client.get("/expenses/add")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_post_signed_out_redirects_to_login_and_inserts_nothing(self, client):
        before = _count_all()
        response = client.post("/expenses/add", data=_form())
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]
        assert _count_all() == before, "Signed-out POST must not insert"

    @pytest.mark.parametrize("method", ["get", "post"])
    def test_session_user_deleted_redirects_to_login(self, client, method):
        _login(client)
        uid = _user_id(DEMO_EMAIL)
        conn = db_module.get_db()
        try:
            conn.execute("DELETE FROM expenses WHERE user_id = ?", (uid,))
            conn.execute("DELETE FROM users WHERE id = ?", (uid,))
            conn.commit()
        finally:
            conn.close()
        before = _count_all()
        if method == "post":
            response = client.post("/expenses/add", data=_form())
        else:
            response = client.get("/expenses/add")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]
        assert _count_all() == before
        with client.session_transaction() as sess:
            assert "user_id" not in sess, "Session should be cleared"


# ---------------------------------------------------------------- GET form
class TestForm:
    def test_get_returns_200(self, logged_in):
        assert logged_in.get("/expenses/add").status_code == 200

    def test_date_prefilled_with_today(self, logged_in):
        html = logged_in.get("/expenses/add").get_data(as_text=True)
        assert f'value="{TODAY}"' in html, "Date should default to today"

    def test_all_categories_in_dropdown(self, logged_in):
        html = logged_in.get("/expenses/add").get_data(as_text=True)
        assert len(db_module.CATEGORIES) == 7
        for category in db_module.CATEGORIES:
            assert re.search(
                r'<option[^>]*value="%s"' % re.escape(category), html
            ), f"Missing category option {category}"

    def test_form_has_expected_fields(self, logged_in):
        html = logged_in.get("/expenses/add").get_data(as_text=True)
        for name in ("amount", "category", "date", "description"):
            assert f'name="{name}"' in html, f"Missing field {name}"

    def test_form_posts_to_add_expense(self, logged_in):
        html = logged_in.get("/expenses/add").get_data(as_text=True)
        match = re.search(r"<form\b[^>]*>", html)
        assert match, "Expected a form"
        tag = match.group(0)
        assert re.search(r'action="/expenses/add"', tag)
        assert re.search(r'method="post"', tag, re.IGNORECASE)

    def test_cancel_link_points_to_profile(self, logged_in):
        html = logged_in.get("/expenses/add").get_data(as_text=True)
        assert re.search(
            r'<a\b[^>]*href="/profile"[^>]*>\s*Cancel\s*</a>', html
        ), "Expected Cancel link to /profile"

    def test_submit_button_label(self, logged_in):
        html = logged_in.get("/expenses/add").get_data(as_text=True)
        assert "Add expense" in html

    def test_no_error_block_on_fresh_get(self, logged_in):
        html = logged_in.get("/expenses/add").get_data(as_text=True)
        for msg in (ERR_AMOUNT, ERR_CATEGORY, ERR_DATE, ERR_DESC):
            assert msg not in html


# ---------------------------------------------------------------- happy path
class TestValidPost:
    def test_redirects_to_profile(self, logged_in):
        response = logged_in.post("/expenses/add", data=_form())
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/profile")

    def test_row_inserted_with_correct_values(self, logged_in):
        before = _count_all()
        logged_in.post(
            "/expenses/add",
            data=_form(amount="45.5", category="Transport",
                       date="2025-03-04", description="CABRIDE"),
        )
        assert _count_all() == before + 1
        rows = _rows_by_description("CABRIDE")
        assert len(rows) == 1
        row = rows[0]
        assert row["user_id"] == _user_id(DEMO_EMAIL)
        assert float(row["amount"]) == pytest.approx(45.5)
        assert row["category"] == "Transport"
        assert row["date"] == "2025-03-04"

    def test_amount_rounded_to_two_decimals(self, logged_in):
        logged_in.post("/expenses/add", data=_form(amount="10.126",
                                                   description="ROUNDME"))
        rows = _rows_by_description("ROUNDME")
        assert len(rows) == 1
        assert float(rows[0]["amount"]) == pytest.approx(10.13)

    def test_flash_shown_after_redirect(self, logged_in):
        response = logged_in.post("/expenses/add", data=_form(),
                                  follow_redirects=True)
        assert response.status_code == 200
        assert "Expense added" in response.get_data(as_text=True)

    def test_flash_uses_success_category(self, logged_in):
        logged_in.post("/expenses/add", data=_form())
        with logged_in.session_transaction() as sess:
            flashes = sess.get("_flashes", [])
        assert ("success", "Expense added") in [tuple(f) for f in flashes]

    def test_expense_appears_on_profile(self, logged_in):
        response = logged_in.post(
            "/expenses/add",
            data=_form(amount="777.00", description="PROFILEVISIBLE"),
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)
        assert "PROFILEVISIBLE" in html
        assert "₹" in html

    def test_refreshing_profile_does_not_duplicate(self, logged_in):
        logged_in.post("/expenses/add", data=_form(description="NODUP"),
                       follow_redirects=True)
        logged_in.get("/profile")
        logged_in.get("/profile")
        assert len(_rows_by_description("NODUP")) == 1

    def test_blank_description_stored_as_null(self, logged_in):
        before = _count_all()
        response = logged_in.post("/expenses/add",
                                  data=_form(description=""))
        assert response.status_code == 302
        assert _count_all() == before + 1
        conn = db_module.get_db()
        try:
            row = conn.execute(
                "SELECT description FROM expenses ORDER BY id DESC LIMIT 1"
            ).fetchone()
        finally:
            conn.close()
        assert row["description"] is None

    def test_whitespace_only_description_stored_as_null(self, logged_in):
        before = _count_all()
        response = logged_in.post("/expenses/add",
                                  data=_form(description="   "))
        assert response.status_code == 302
        assert _count_all() == before + 1
        conn = db_module.get_db()
        try:
            row = conn.execute(
                "SELECT description FROM expenses ORDER BY id DESC LIMIT 1"
            ).fetchone()
        finally:
            conn.close()
        assert row["description"] is None

    def test_missing_description_field_succeeds(self, logged_in):
        before = _count_all()
        response = logged_in.post("/expenses/add",
                                  data=_form(description=None))
        assert response.status_code == 302
        assert _count_all() == before + 1

    def test_description_is_stripped(self, logged_in):
        logged_in.post("/expenses/add",
                       data=_form(description="  PADDED  "))
        assert len(_rows_by_description("PADDED")) == 1

    def test_description_of_exactly_200_chars_accepted(self, logged_in):
        desc = "d" * 200
        response = logged_in.post("/expenses/add",
                                  data=_form(description=desc))
        assert response.status_code == 302
        assert len(_rows_by_description(desc)) == 1

    def test_today_date_accepted(self, logged_in):
        response = logged_in.post("/expenses/add", data=_form(date=TODAY))
        assert response.status_code == 302

    def test_max_amount_accepted(self, logged_in):
        response = logged_in.post(
            "/expenses/add",
            data=_form(amount="10000000", description="MAXAMT"),
        )
        assert response.status_code == 302
        assert len(_rows_by_description("MAXAMT")) == 1

    @pytest.mark.parametrize("category", list(db_module.CATEGORIES))
    def test_every_category_accepted(self, logged_in, category):
        response = logged_in.post(
            "/expenses/add",
            data=_form(category=category, description=f"CAT-{category}"),
        )
        assert response.status_code == 302
        assert len(_rows_by_description(f"CAT-{category}")) == 1


# ---------------------------------------------------------------- validation
INVALID_CASES = [
    pytest.param({"amount": "0"}, ERR_AMOUNT, id="amount-zero"),
    pytest.param({"amount": "-5"}, ERR_AMOUNT, id="amount-negative"),
    pytest.param({"amount": "abc"}, ERR_AMOUNT, id="amount-non-numeric"),
    pytest.param({"amount": None}, ERR_AMOUNT, id="amount-missing"),
    pytest.param({"amount": ""}, ERR_AMOUNT, id="amount-empty"),
    pytest.param({"amount": "10000000.01"}, ERR_AMOUNT, id="amount-too-large"),
    pytest.param({"amount": "99999999"}, ERR_AMOUNT, id="amount-way-too-large"),
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
    def test_invalid_returns_400_with_error_and_no_insert(
        self, logged_in, overrides, message
    ):
        before = _count_all()
        response = logged_in.post("/expenses/add", data=_form(**overrides))
        assert response.status_code == 400, "Validation errors must be 400"
        assert message in response.get_data(as_text=True)
        assert _count_all() == before, "Nothing should be inserted"

    def test_error_block_rendered(self, logged_in):
        html = logged_in.post(
            "/expenses/add", data=_form(amount="0")
        ).get_data(as_text=True)
        assert "auth-error" in html

    def test_amount_error_repopulates_other_values(self, logged_in):
        html = logged_in.post(
            "/expenses/add",
            data=_form(amount="0", category="Health", date="2025-05-06",
                       description="KEEPME"),
        ).get_data(as_text=True)
        assert 'value="0"' in html, "Amount should be re-populated"
        assert 'value="2025-05-06"' in html, "Date should be re-populated"
        assert 'value="KEEPME"' in html, "Description should be re-populated"
        assert re.search(
            r'<option[^>]*value="Health"[^>]*selected|'
            r'<option[^>]*selected[^>]*value="Health"', html
        ), "Selected category should be kept"

    def test_non_numeric_amount_repopulated(self, logged_in):
        html = logged_in.post(
            "/expenses/add", data=_form(amount="abc")
        ).get_data(as_text=True)
        assert 'value="abc"' in html

    def test_date_error_repopulates_values(self, logged_in):
        html = logged_in.post(
            "/expenses/add",
            data=_form(date=TOMORROW, amount="33.25", category="Bills",
                       description="FUTUREDESC"),
        ).get_data(as_text=True)
        assert 'value="33.25"' in html
        assert f'value="{TOMORROW}"' in html
        assert 'value="FUTUREDESC"' in html
        assert re.search(
            r'<option[^>]*value="Bills"[^>]*selected|'
            r'<option[^>]*selected[^>]*value="Bills"', html
        )

    def test_description_error_repopulates_description(self, logged_in):
        desc = "y" * 201
        html = logged_in.post(
            "/expenses/add", data=_form(description=desc)
        ).get_data(as_text=True)
        assert desc in html, "Over-long description should be re-populated"

    def test_error_response_still_has_form(self, logged_in):
        html = logged_in.post(
            "/expenses/add", data=_form(amount="0")
        ).get_data(as_text=True)
        assert 'name="amount"' in html
        assert re.search(r'action="/expenses/add"', html)

    def test_amount_checked_before_category(self, logged_in):
        response = logged_in.post(
            "/expenses/add", data=_form(amount="0", category="Bogus")
        )
        html = response.get_data(as_text=True)
        assert ERR_AMOUNT in html
        assert ERR_CATEGORY not in html, "Only first error should be shown"

    def test_sql_injection_in_description_stored_literally(self, logged_in):
        payload = "x'); DROP TABLE expenses;--"
        before = _count_all()
        response = logged_in.post("/expenses/add",
                                  data=_form(description=payload))
        assert response.status_code == 302
        assert _count_all() == before + 1
        assert len(_rows_by_description(payload)) == 1


# ---------------------------------------------------------------- isolation
class TestOwnership:
    def test_user_id_cannot_be_spoofed_via_form(self, logged_in, other_user):
        demo_id = _user_id(DEMO_EMAIL)
        data = _form(description="SPOOFATTEMPT")
        data["user_id"] = str(other_user)
        response = logged_in.post("/expenses/add", data=data)
        assert response.status_code == 302
        rows = _rows_by_description("SPOOFATTEMPT")
        assert len(rows) == 1
        assert rows[0]["user_id"] == demo_id
        assert rows[0]["user_id"] != other_user

    def test_expense_not_on_other_users_profile(self, client, other_user):
        _login(client)
        client.post("/expenses/add", data=_form(description="DEMOONLYITEM"))
        client.get("/logout")
        _login(client, OTHER_EMAIL, OTHER_PASSWORD)
        html = client.get("/profile").get_data(as_text=True)
        assert "DEMOONLYITEM" not in html

    def test_other_users_expense_not_on_demo_profile(self, client, other_user):
        _login(client, OTHER_EMAIL, OTHER_PASSWORD)
        client.post("/expenses/add", data=_form(description="OTHERONLYITEM"))
        client.get("/logout")
        _login(client)
        html = client.get("/profile").get_data(as_text=True)
        assert "OTHERONLYITEM" not in html

    def test_new_user_first_expense_appears_on_own_profile(self, client,
                                                           other_user):
        _login(client, OTHER_EMAIL, OTHER_PASSWORD)
        response = client.post(
            "/expenses/add", data=_form(description="FIRSTONE"),
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)
        assert "FIRSTONE" in html
        assert "Expense added" in html


# ---------------------------------------------------------------- profile link
class TestProfileLink:
    def test_profile_has_add_expense_link(self, logged_in):
        html = logged_in.get("/profile").get_data(as_text=True)
        assert re.search(
            r'<a\b[^>]*href="/expenses/add"[^>]*>\s*(?:\+\s*)?Add expense',
            html, re.IGNORECASE,
        ), "Profile should link to /expenses/add with 'Add expense'"

    def test_add_expense_page_has_no_dollar_sign(self, logged_in):
        html = logged_in.get("/expenses/add").get_data(as_text=True)
        assert "$" not in html, "Currency is INR; no $ allowed"

    def test_empty_state_links_to_add_expense(self, client, other_user):
        _login(client, OTHER_EMAIL, OTHER_PASSWORD)
        html = client.get("/profile").get_data(as_text=True)
        assert "No expenses yet." in html
        assert 'href="/expenses/add"' in html


# ---------------------------------------------------------------- input attrs
class TestFormAttributes:
    def _html(self, client):
        return client.get("/expenses/add").get_data(as_text=True)

    def _tag(self, html, name):
        match = re.search(r'<(?:input|select)\b[^>]*name="%s"[^>]*>' % name, html)
        assert match, f"Missing field {name}"
        return match.group(0)

    def test_amount_input_attributes(self, logged_in):
        tag = self._tag(self._html(logged_in), "amount")
        assert 'type="number"' in tag
        assert 'step="0.01"' in tag
        assert 'min="0.01"' in tag
        assert "required" in tag

    def test_date_input_is_date_type_and_required(self, logged_in):
        tag = self._tag(self._html(logged_in), "date")
        assert 'type="date"' in tag
        assert "required" in tag

    def test_description_input_maxlength_200_and_optional(self, logged_in):
        tag = self._tag(self._html(logged_in), "description")
        assert 'maxlength="200"' in tag
        assert "required" not in tag

    def test_category_is_required_select(self, logged_in):
        html = self._html(logged_in)
        assert re.search(r'<select\b[^>]*name="category"', html)
        assert "required" in self._tag(html, "category")

    def test_page_extends_base_layout(self, logged_in):
        html = self._html(logged_in)
        assert "<html" in html and "</html>" in html

    def test_no_inline_style_attributes(self, logged_in):
        html = self._html(logged_in)
        assert "<style" not in html
        assert 'style="' not in html


# ---------------------------------------------------------------- profile integration
class TestProfileIntegration:
    def test_new_expense_listed_first_in_history(self, client, other_user):
        _login(client, OTHER_EMAIL, OTHER_PASSWORD)
        client.post("/expenses/add", data=_form(
            date="2025-01-01", description="OLDERENTRY"))
        client.post("/expenses/add", data=_form(
            date=TODAY, description="NEWERENTRY"))
        html = client.get("/profile").get_data(as_text=True)
        assert "NEWERENTRY" in html and "OLDERENTRY" in html
        assert html.index("NEWERENTRY") < html.index("OLDERENTRY"), \
            "Newest expense should be at the top of Transaction history"

    def test_amount_shown_with_rupee_symbol(self, client, other_user):
        _login(client, OTHER_EMAIL, OTHER_PASSWORD)
        client.post("/expenses/add", data=_form(amount="250.00"))
        html = client.get("/profile").get_data(as_text=True)
        assert re.search(r"₹\s*250", html), "Expected ₹250 on profile"
        assert "$" not in html

    def test_total_spent_includes_new_expense(self, client, other_user):
        _login(client, OTHER_EMAIL, OTHER_PASSWORD)
        client.post("/expenses/add", data=_form(amount="100.00"))
        client.post("/expenses/add", data=_form(amount="50.50",
                                                category="Bills"))
        html = client.get("/profile").get_data(as_text=True)
        assert re.search(r"₹\s*150\.5", html), "Total should be ₹150.50"

    def test_category_breakdown_includes_new_category(self, client, other_user):
        _login(client, OTHER_EMAIL, OTHER_PASSWORD)
        html_before = client.get("/profile").get_data(as_text=True)
        client.post("/expenses/add", data=_form(category="Shopping"))
        html_after = client.get("/profile").get_data(as_text=True)
        assert html_after.count("Shopping") > html_before.count("Shopping"), \
            "Shopping should now appear in breakdown/history"

    def test_transaction_count_updates_for_demo_user(self, logged_in):
        conn = db_module.get_db()
        try:
            uid = _user_id(DEMO_EMAIL)
            before = conn.execute(
                "SELECT COUNT(*) FROM expenses WHERE user_id = ?", (uid,)
            ).fetchone()[0]
        finally:
            conn.close()
        logged_in.post("/expenses/add", data=_form(description="COUNTME"))
        conn = db_module.get_db()
        try:
            after = conn.execute(
                "SELECT COUNT(*) FROM expenses WHERE user_id = ?", (uid,)
            ).fetchone()[0]
        finally:
            conn.close()
        assert after == before + 1

    def test_new_expense_respects_date_filter_inside_range(self, client,
                                                           other_user):
        _login(client, OTHER_EMAIL, OTHER_PASSWORD)
        client.post("/expenses/add", data=_form(
            date="2025-03-04", description="INRANGE"))
        html = client.get(
            "/profile?date_from=2025-03-01&date_to=2025-03-31"
        ).get_data(as_text=True)
        assert "INRANGE" in html

    def test_new_expense_respects_date_filter_outside_range(self, client,
                                                            other_user):
        _login(client, OTHER_EMAIL, OTHER_PASSWORD)
        client.post("/expenses/add", data=_form(
            date="2025-03-04", description="OUTRANGE"))
        html = client.get(
            "/profile?date_from=2025-04-01&date_to=2025-04-30"
        ).get_data(as_text=True)
        assert "OUTRANGE" not in html


# ---------------------------------------------------------------- misc
class TestMiscBehavior:
    def test_cancel_get_profile_inserts_nothing(self, logged_in):
        before = _count_all()
        assert logged_in.get("/expenses/add").status_code == 200
        assert logged_in.get("/profile").status_code == 200
        assert _count_all() == before

    def test_blank_description_row_renders_on_profile(self, client, other_user):
        _login(client, OTHER_EMAIL, OTHER_PASSWORD)
        response = client.post("/expenses/add", data=_form(description=""),
                               follow_redirects=True)
        assert response.status_code == 200
        assert "No expenses yet." not in response.get_data(as_text=True)

    def test_category_error_does_not_insert_tampered_category(self, logged_in):
        logged_in.post("/expenses/add", data=_form(
            category="Hacking", description="TAMPERED"))
        assert _rows_by_description("TAMPERED") == []

    def test_amount_with_surrounding_whitespace_or_comma_not_crash(
        self, logged_in
    ):
        response = logged_in.post("/expenses/add", data=_form(amount="1,00"))
        assert response.status_code in (302, 400)

    @pytest.mark.parametrize("amount", ["nan", "inf", "-inf"])
    def test_non_finite_amount_rejected(self, logged_in, amount):
        before = _count_all()
        response = logged_in.post("/expenses/add", data=_form(amount=amount))
        assert response.status_code == 400
        assert ERR_AMOUNT in response.get_data(as_text=True)
        assert _count_all() == before

    def test_xss_in_description_is_escaped_on_error_rerender(self, logged_in):
        payload = "<script>alert(1)</script>" + "x" * 200
        html = logged_in.post(
            "/expenses/add", data=_form(description=payload)
        ).get_data(as_text=True)
        assert "<script>alert(1)</script>" not in html
