import calendar
import os
import sqlite3
from datetime import date, datetime

from flask import Flask, flash, redirect, render_template, request, session, url_for

from database.db import (
    authenticate_user,
    create_user,
    get_category_breakdown,
    get_db,
    get_recent_transactions,
    get_summary_stats,
    get_user_by_email,
    get_user_by_id,
    init_db,
    seed_db,
)

app = Flask(__name__)
app.secret_key = os.environ.get("SPENDLY_SECRET_KEY", "dev-only-insecure-change-me")

with app.app_context():
    init_db()
    seed_db()


# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #

DUPLICATE_EMAIL_ERROR = "An account with that email already exists."
REGISTER_SUCCESS = "Account created — please sign in"
LOGIN_ERROR = "Invalid email or password."
LOGOUT_SUCCESS = "You've been signed out"
DATE_RANGE_ERROR = "Start date must be before end date."


@app.template_filter("inr")
def format_inr(amount):
    return f"₹{(amount or 0):,.2f}"


@app.template_filter("display_date")
def format_display_date(value):
    """Render an ISO date (YYYY-MM-DD) as 'DD Mon YYYY'."""
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d %b %Y")
    except (TypeError, ValueError):
        return value


def parse_iso_date(value):
    """Return value if it is a valid YYYY-MM-DD date, otherwise None."""
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except (TypeError, ValueError):
        return None


def resolve_date_filter(args):
    """Return (date_from, date_to, error) from query args.

    Malformed or partial ranges fall back silently to (None, None, None);
    a reversed range falls back to (None, None, DATE_RANGE_ERROR).
    """
    date_from = parse_iso_date(args.get("date_from"))
    date_to = parse_iso_date(args.get("date_to"))
    if date_from is None or date_to is None:
        return None, None, None
    if date_from > date_to:
        return None, None, DATE_RANGE_ERROR
    return date_from, date_to, None


def months_ago(today, months):
    """Return the date `months` calendar months before today.

    The day is clamped to the target month's length, so 31 Aug minus
    6 months gives 28 Feb (29 Feb in a leap year).
    """
    month_index = today.year * 12 + today.month - 1 - months
    year, month = divmod(month_index, 12)
    month += 1
    day = min(today.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def build_presets(today, date_from, date_to):
    """Return the quick-select presets, marking the one matching the filter."""
    end = today.isoformat()
    ranges = [
        ("This Month", today.replace(day=1).isoformat(), end),
        ("Last 3 Months", months_ago(today, 3).isoformat(), end),
        ("Last 6 Months", months_ago(today, 6).isoformat(), end),
        ("All Time", None, None),
    ]
    return [
        {
            "label": label,
            "date_from": start,
            "date_to": stop,
            "active": (start, stop) == (date_from, date_to),
        }
        for label, start, stop in ranges
    ]


def format_period(date_from, date_to):
    """Return the stat-note label for the active date range."""
    if date_from is None:
        return "All time"
    return f"{format_display_date(date_from)} – {format_display_date(date_to)}"


def normalize_email(raw):
    return (raw or "").strip().lower()


def validate_registration(name, email, password, confirm_password):
    """Return the first validation error message, or None if all valid."""
    if not name:
        return "Please enter your name."
    if len(name) > 100:
        return "Name must be 100 characters or fewer."

    local, sep, domain = email.partition("@")
    if not sep or not local or "." not in domain:
        return "Please enter a valid email address."

    if len(password) < 8:
        return "Password must be at least 8 characters."
    if password != confirm_password:
        return "Passwords do not match."

    if get_user_by_email(email) is not None:
        return DUPLICATE_EMAIL_ERROR
    return None


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("profile"))

    if request.method == "GET":
        return render_template("register.html")

    name = request.form.get("name", "").strip()
    email = normalize_email(request.form.get("email", ""))
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    error = validate_registration(name, email, password, confirm_password)
    if error is None:
        try:
            create_user(name, email, password)
        except sqlite3.IntegrityError:
            error = DUPLICATE_EMAIL_ERROR

    if error:
        return render_template(
            "register.html", error=error, name=name, email=email
        ), 400

    flash(REGISTER_SUCCESS, "success")
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if "user_id" in session:
            return redirect(url_for("profile"))
        return render_template("login.html")

    email = normalize_email(request.form.get("email", ""))
    password = request.form.get("password", "")

    user = authenticate_user(email, password) if email and password else None
    if user is None:
        return render_template("login.html", error=LOGIN_ERROR, email=email), 401

    session.clear()
    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    return redirect(url_for("profile"))


@app.route("/logout")
def logout():
    session.clear()
    flash(LOGOUT_SUCCESS, "info")
    return redirect(url_for("landing"))


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/profile")
def profile():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    user = get_user_by_id(user_id)
    if user is None:
        session.clear()
        return redirect(url_for("login"))

    date_from, date_to, filter_error = resolve_date_filter(request.args)
    if filter_error:
        flash(filter_error, "error")
    presets = build_presets(date.today(), date_from, date_to)

    expenses = get_recent_transactions(
        user_id, date_from=date_from, date_to=date_to
    )
    stats = get_summary_stats(user_id, date_from=date_from, date_to=date_to)
    categories = get_category_breakdown(
        user_id, date_from=date_from, date_to=date_to
    )

    return render_template(
        "profile.html",
        user=user,
        stats=stats,
        expenses=expenses,
        categories=categories,
        presets=presets,
        date_from=date_from,
        date_to=date_to,
        custom_active=not any(preset["active"] for preset in presets),
        period_label=format_period(date_from, date_to),
    )


@app.route("/analytics")
def analytics():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if get_user_by_id(session["user_id"]) is None:
        session.clear()
        return redirect(url_for("login"))

    return render_template("analytics.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
