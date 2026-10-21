import os
import sqlite3

from flask import Flask, flash, redirect, render_template, request, session, url_for

from database.db import (
    authenticate_user,
    create_user,
    get_db,
    get_user_by_email,
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

# Hardcoded profile data for Step 4 — mirrors the seed data in database/db.py.
# Step 5 replaces these with real queries.
PROFILE_USER = {
    "email": "demo@spendly.com",
    "member_since": "October 2026",
}

PROFILE_STATS = {
    "total_spent": 5488.50,
    "transaction_count": 8,
    "top_category": "Bills",
    "top_category_total": 1850.00,
}

PROFILE_EXPENSES = [
    {"date": "21 Oct 2026", "description": "Gift wrapping", "category": "Other", "amount": 150.00},
    {"date": "19 Oct 2026", "description": "Dinner at restaurant", "category": "Food", "amount": 340.00},
    {"date": "16 Oct 2026", "description": "New headphones", "category": "Shopping", "amount": 1299.00},
    {"date": "13 Oct 2026", "description": "Movie tickets", "category": "Entertainment", "amount": 499.00},
    {"date": "10 Oct 2026", "description": "Pharmacy - vitamins", "category": "Health", "amount": 680.00},
    {"date": "07 Oct 2026", "description": "Uber ride to office", "category": "Transport", "amount": 250.00},
    {"date": "04 Oct 2026", "description": "Groceries from local market", "category": "Food", "amount": 420.50},
    {"date": "01 Oct 2026", "description": "Electricity bill", "category": "Bills", "amount": 1850.00},
]

PROFILE_CATEGORIES = [
    {"name": "Bills", "total": 1850.00, "percent": 34},
    {"name": "Shopping", "total": 1299.00, "percent": 24},
    {"name": "Food", "total": 760.50, "percent": 14},
    {"name": "Health", "total": 680.00, "percent": 12},
    {"name": "Entertainment", "total": 499.00, "percent": 9},
    {"name": "Transport", "total": 250.00, "percent": 5},
    {"name": "Other", "total": 150.00, "percent": 3},
]


@app.template_filter("inr")
def format_inr(amount):
    return f"₹{amount:,.2f}"


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

    user = {**PROFILE_USER, "name": session["user_name"]}
    return render_template(
        "profile.html",
        user=user,
        stats=PROFILE_STATS,
        expenses=PROFILE_EXPENSES,
        categories=PROFILE_CATEGORIES,
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
