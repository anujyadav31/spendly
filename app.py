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
LOGIN_SUCCESS = "Welcome back, {name}!"
LOGOUT_SUCCESS = "You've been signed out"


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
        return redirect(url_for("landing"))

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
            return redirect(url_for("landing"))
        return render_template("login.html")

    email = normalize_email(request.form.get("email", ""))
    password = request.form.get("password", "")

    user = authenticate_user(email, password) if email and password else None
    if user is None:
        return render_template("login.html", error=LOGIN_ERROR, email=email), 401

    session.clear()
    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    flash(LOGIN_SUCCESS.format(name=user["name"]), "success")
    return redirect(url_for("landing"))


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


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/profile")
def profile():
    return "Profile page — coming in Step 4"


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
