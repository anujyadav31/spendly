import os
import sqlite3
from datetime import date, datetime

from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get("SPENDLY_DB_PATH") or os.path.join(
    BASE_DIR, "expense_tracker.db"
)

CATEGORIES = (
    "Food",
    "Transport",
    "Bills",
    "Health",
    "Entertainment",
    "Shopping",
    "Other",
)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS expenses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    amount      REAL NOT NULL,
    category    TEXT NOT NULL,
    date        TEXT NOT NULL,
    description TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);
"""


def get_db():
    """Return a SQLite connection with dict-like rows and FK enforcement."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create all tables. Safe to call multiple times."""
    conn = get_db()
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()


def get_user_by_email(email):
    """Return the user row for an already-normalised email, or None."""
    conn = get_db()
    try:
        return conn.execute(
            "SELECT id, name, email, password_hash, created_at "
            "FROM users WHERE email = ?",
            (email,),
        ).fetchone()
    finally:
        conn.close()


def create_user(name, email, password):
    """Insert a user with a hashed password and return the new id.

    Expects an already-normalised email. Raises sqlite3.IntegrityError
    if the email is already registered.
    """
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, generate_password_hash(password)),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def authenticate_user(email, password):
    """Return the user row if the password matches, otherwise None.

    Expects an already-normalised email.
    """
    user = get_user_by_email(email)
    if user is None or not check_password_hash(user["password_hash"], password):
        return None
    return user


def get_user_by_id(user_id):
    """Return {id, name, email, member_since} for the user, or None."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, name, email, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    created = datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S")
    return {
        "id": row["id"],
        "name": row["name"],
        "email": row["email"],
        "member_since": created.strftime("%B %Y"),
    }


def get_recent_transactions(user_id, limit=10):
    """Return the user's newest expenses as {date, description, category, amount}.

    Ordered by date (newest first), ties broken by id descending.
    Dates are ISO strings; formatting is left to the template.
    """
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT date, description, category, amount FROM expenses "
            "WHERE user_id = ? ORDER BY date DESC, id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "date": row["date"],
            "description": row["description"] or "",
            "category": row["category"],
            "amount": float(row["amount"]),
        }
        for row in rows
    ]


def get_summary_stats(user_id):
    """Return {total_spent, transaction_count, top_category, top_category_total}.

    All-time figures for the user. Top-category ties resolve alphabetically.
    """
    conn = get_db()
    try:
        totals = conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(amount), 0) AS total "
            "FROM expenses WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        top = conn.execute(
            "SELECT category, SUM(amount) AS total FROM expenses "
            "WHERE user_id = ? GROUP BY category "
            "ORDER BY total DESC, category ASC LIMIT 1",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()
    return {
        "total_spent": round(float(totals["total"]), 2),
        "transaction_count": int(totals["n"]),
        "top_category": top["category"] if top else "—",
        "top_category_total": round(float(top["total"]), 2) if top else 0.0,
    }


def get_category_breakdown(user_id):
    """Return [{name, total, percent}] by total desc; percents sum to 100."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT category AS name, SUM(amount) AS total FROM expenses "
            "WHERE user_id = ? GROUP BY category "
            "ORDER BY total DESC, name ASC",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()
    grand = sum(row["total"] for row in rows)
    if not rows or grand <= 0:
        return []
    breakdown = [
        {
            "name": row["name"],
            "total": round(row["total"], 2),
            "percent": int(round(row["total"] * 100 / grand)),
        }
        for row in rows
    ]
    # Largest category absorbs rounding drift so percents sum to exactly 100.
    breakdown[0]["percent"] += 100 - sum(item["percent"] for item in breakdown)
    return breakdown


def _sample_expenses(user_id, today):
    """Build 8 sample expenses dated from the 1st of this month to today."""
    samples = [
        ("Bills", 1850.00, "Electricity bill"),
        ("Food", 420.50, "Groceries from local market"),
        ("Transport", 250.00, "Uber ride to office"),
        ("Health", 680.00, "Pharmacy - vitamins"),
        ("Entertainment", 499.00, "Movie tickets"),
        ("Shopping", 1299.00, "New headphones"),
        ("Food", 340.00, "Dinner at restaurant"),
        ("Other", 150.00, "Gift wrapping"),
    ]
    rows = []
    for i, (category, amount, description) in enumerate(samples):
        day = 1 + round(i * (today.day - 1) / (len(samples) - 1))
        expense_date = date(today.year, today.month, day).isoformat()
        rows.append((user_id, amount, category, expense_date, description))
    return rows


def seed_db():
    """Insert a demo user and sample expenses, only if no users exist yet."""
    conn = get_db()
    try:
        user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if user_count > 0:
            return

        cur = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Demo User", "demo@spendly.com", generate_password_hash("demo123")),
        )
        user_id = cur.lastrowid

        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            _sample_expenses(user_id, date.today()),
        )
        conn.commit()
    finally:
        conn.close()
