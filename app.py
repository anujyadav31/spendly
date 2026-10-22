import os
import sqlite3
from datetime import datetime

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

    expenses = get_recent_transactions(user_id)
    stats = get_summary_stats(user_id)
    categories = get_category_breakdown(user_id)

    return render_template(
        "profile.html",
        user=user,
        stats=stats,
        expenses=expenses,
        categories=categories,
    )


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
