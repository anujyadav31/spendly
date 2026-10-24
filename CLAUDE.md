# CLAUDE.md

## Project overview

Spendly is a lightweight personal expense tracker built with Flask and SQLite.

---

## Architecture
```
spendly/
├── app.py              # All routes — single file, no blueprints
├── database/
│   └── db.py           # SQLite helpers: get_db(), init_db(), seed_db()
├── templates/
│   ├── base.html       # Shared layout — all templates must extend this
│   └── *.html          # One template per page
├── static/
│   ├── css/
│   │   ├── style.css       # Global styles
│   │   └── landing.css     # Landing-page-only styles
│   └── js/
│       └── main.js         # Vanilla JS only
└── requirements.txt
```

**Where things belong:**
- New routes → `app.py` only, no blueprints
- DB logic → `database/db.py` only, never inline in routes
- New pages → new `.html` file extending `base.html`
- Page-specific styles → new `.css` file, not inline `<style>` tags

---

## Code style

- Python: PEP 8, snake_case for all variables and functions
- Templates: Jinja2 with `url_for()` for every internal link — never hardcode URLs
- Route functions: one responsibility only — fetch data, render template, done
- DB queries: always use parameterized queries (`?` placeholders) — never f-strings in SQL
- Error handling: use `abort()` for HTTP errors, not bare `return "error string"`

---

## Tech constraints

- **Flask only** — no FastAPI, no Django, no other web frameworks
- **SQLite only** — no PostgreSQL, no SQLAlchemy ORM, no external DB
- **Vanilla JS only** — no React, no jQuery, no npm packages
- **No new pip packages** — work within `requirements.txt` as-is unless explicitly told otherwise
- Python 3.10+ assumed — f-strings and `match` statements are fine

---

## Subagent Policy
- Always use a builtin explore subagent for codebase exploration 
  before implementing any new feature
- Always use a subagent to verify test results 
  after any implementation
- When asked to plan, delegate codebase research 
  to a subagent before presenting the plan
- always use a builtin plan subagent in plan mode

---

## Commands
```bash
# Setup
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Run dev server (port 5001)
python app.py

# Run all tests
pytest

# Run a specific test file
pytest tests/test_foo.py

# Run a specific test by name
pytest -k "test_name"

# Run tests with output visible
pytest -s
```

---

## Implemented vs stub routes

| Route | Status |
|---|---|
| `GET /` | Implemented — renders `landing.html` |
| `GET/POST /register` | Implemented — redirects to `/profile` if signed in; GET renders `register.html`; POST validates, creates user, flashes and redirects to `/login` |
| `GET/POST /login` | Implemented — GET renders `login.html` (redirects to `/profile` if signed in); POST authenticates, sets `session["user_id"]`/`session["user_name"]` and redirects to `/profile` (no welcome flash) |
| `GET /logout` | Implemented — clears session, flashes and redirects to `/` |
| `GET /profile` | Implemented (Steps 5–6) — redirects to `/login` if signed out or the session's user no longer exists; renders `profile.html` with live data from `get_user_by_id`, `get_summary_stats`, `get_recent_transactions` (10 newest) and `get_category_breakdown`, optionally filtered by date (see below) |
| `GET /analytics` | Implemented — redirects to `/login` if signed out or the session's user no longer exists; renders the `analytics.html` coming-soon page. Navbar shows an "Analytics" link (signed-in only) with an `active` class via `request.endpoint` |
| `GET/POST /expenses/add` | Implemented (Step 7) — redirects to `/login` if signed out or the session's user no longer exists; GET renders `add_expense.html` (date defaults to today, categories from `CATEGORIES`); POST validates amount/category/date/description, calls `create_expense`, flashes "Expense added" and redirects to `/profile`; validation errors re-render with 400. Profile's Transaction history card links here |
| `GET/POST /expenses/<id>/edit` | Implemented (Step 8) — redirects to `/login` if signed out or the session's user no longer exists; 404 if the expense is missing or belongs to another user (ownership enforced in SQL); GET renders `edit_expense.html` pre-filled; POST validates with `validate_expense`, calls `update_expense`, flashes "Expense updated" and redirects to `/profile`; validation errors re-render with 400. Each profile transaction row has an Edit link |
| `POST /expenses/<id>/delete` | Implemented (Step 9) — POST-only (GET → 405); redirects to `/login` if signed out or the session's user no longer exists; calls `delete_expense` (ownership enforced in SQL, 404 if missing or another user's); flashes "Expense deleted" and redirects to `/profile`. Each profile transaction row has a Delete button whose form carries `data-confirm`, handled by a JS `confirm()` listener in `main.js` |

**`/profile` date filter (Step 6):** optional `?date_from=&date_to=` (ISO, inclusive, both required) filters stats, transactions and categories. Malformed or partial ranges fall back to all-time; a reversed range also flashes an error. Presets: This Month, Last 3 Months, Last 6 Months, All Time.

**Do not implement a stub route unless the active task explicitly targets that step.**

---

## Warnings and things to avoid

- **Never use raw string returns for stub routes** once a step is implemented — always render a template
- **Never hardcode URLs** in templates — always use `url_for()`
- **Never put DB logic in route functions** — it belongs in `database/db.py`
- **Never install new packages** mid-feature without flagging it — keep `requirements.txt` in sync
- **Never use JS frameworks** — the frontend is intentionally vanilla
- **`database/db.py` only has helpers from completed steps** — `get_db`, `init_db`, `seed_db`, `get_user_by_email`, `create_user`, `authenticate_user`, `get_user_by_id`, `create_expense`, `get_expense_by_id`, `update_expense`, `delete_expense`, `get_recent_transactions` (rows include `id`), `get_summary_stats`, `get_category_breakdown`; do not assume others exist until the step that implements them
- **Dates are stored as ISO `YYYY-MM-DD`** — format them in templates with the `display_date` filter; render money with the `inr` filter (handles `None`)
- **FK enforcement is manual** — SQLite foreign keys are off by default; `get_db()` must run `PRAGMA foreign_keys = ON` on every connection
- The app runs on **port 5001**, not the Flask default 5000 — don't change this