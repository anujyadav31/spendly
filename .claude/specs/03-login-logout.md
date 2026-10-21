# Spec: Login and Logout

## Overview
Let registered users sign in and out. Today `GET /login` only renders a form whose
POST has nowhere to go (and its `action` is hard-coded), and `GET /logout` is a raw
string stub. This step adds a `POST /login` handler that checks the submitted email and
password against the werkzeug hash stored by Step 2, starts a Flask session holding the
user's id and name, and makes the navbar reflect signed-in state. `GET /logout` clears
the session and sends the user back to the landing page. This is the first point where
Spendly knows *who* is using it — Step 4 (Profile) and every expense step build on the
session established here. Protecting routes with a "login required" guard is **not**
part of this step; there are no private pages yet.

## Depends on
- **Step 1 — Database setup**: `users` table, `get_db()`, seeded demo user
  (`demo@spendly.com` / `demo123`).
- **Step 2 — Registration**: `get_user_by_email()`, `create_user()` with werkzeug
  hashing, `app.secret_key`, `normalize_email()`, success flash on `/login`, and the
  pytest fixtures in `tests/conftest.py`.

## Routes
- `GET /login` — render the sign-in form (exists; now redirects to `/` if already
  signed in) — public
- `POST /login` — validate credentials; on success clear and populate the session,
  flash a welcome message and redirect to `/`; on failure re-render `login.html` with
  a generic error and the entered email — public
- `GET /logout` — clear the session, flash "You've been signed out", redirect to `/`
  (replaces the Step 3 stub; safe to hit when not signed in) — public

`/login` becomes one view function: `@app.route("/login", methods=["GET", "POST"])`.

Post-login redirect target is `landing` for now because `/profile` is still a Step 4
stub; Step 4 will change it.

## Database changes
No database changes — the `users` table already has `email` and `password_hash`.

New helper in `database/db.py` (no schema change):
- `authenticate_user(email, password)` → the user `sqlite3.Row` if the email exists
  and `check_password_hash(row["password_hash"], password)` is true, otherwise `None`.
  Expects an already-normalised email. Reuses `get_user_by_email()`; keeps all
  password-hash handling in `db.py` next to `create_user()`.

## Templates
- **Create:** none
- **Modify:**
  - `templates/login.html`
    - `action="/login"` → `action="{{ url_for('login') }}"` (fixes hard-coded URL)
    - Re-populate email on error: `value="{{ email or '' }}"` (never the password)
    - Remove the local `get_flashed_messages` loop — flashes move to `base.html`
  - `templates/base.html`
    - Render flashed messages (with categories) once, at the top of `<main>`, so the
      landing page can show "Welcome back" / "You've been signed out" and `/login`
      still shows the Step 2 "Account created" message
    - Navbar: when `session.user_id` is set, show the user's name and a "Sign out"
      link (`url_for('logout')`, styled `nav-cta` so it stays visible on mobile);
      otherwise keep the existing "Sign in" / "Get started" links

## Files to change
- `app.py` — import `session`; make `/login` accept POST with the authenticate +
  session + redirect flow; redirect already-signed-in users away from `GET /login`;
  replace the `/logout` stub with session clear + flash + redirect
- `database/db.py` — add `authenticate_user()`; import `check_password_hash`
- `templates/login.html` — see Templates
- `templates/base.html` — see Templates
- `static/css/style.css` — add a `.flash` container (and `.flash-success` /
  `.flash-info` variants if needed) plus a `.nav-user` style, using existing CSS
  variables only
- `CLAUDE.md` — route table: mark `POST /login` and `GET /logout` as implemented

## Files to create
- `tests/test_auth.py` — tests covering every Definition of Done item below, using the
  existing `app` / `client` fixtures from `tests/conftest.py`

## New dependencies
No new dependencies — `flask` sessions and `werkzeug.security.check_password_hash`
are already available.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only (`?` placeholders) — never f-strings or `%` in SQL
- Passwords hashed with werkzeug — verify with `check_password_hash`, never compare
  plaintext, never log or re-render the password
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- All DB access lives in `database/db.py`; routes only call helpers
- `url_for()` for every internal link, form action and redirect
- Normalise the submitted email with the existing `normalize_email()` before lookup
- Failure message is the **same** generic text for unknown email, wrong password and
  blank fields: "Invalid email or password." — do not reveal which part was wrong
- Failed login re-renders `login.html` with HTTP **401**
- On success call `session.clear()` *before* setting `session["user_id"]` and
  `session["user_name"]` (avoids session fixation); store nothing else, never the hash
- Use Post/Redirect/Get: `flash(...)` then `redirect(url_for(...))` for both login
  success and logout
- `/logout` uses `session.clear()` and works whether or not a user is signed in
- Do not implement `/profile` or any Step 4+ stub, and do not add a `login_required`
  decorator yet
- Currency/locale is INR — any user-facing copy that mentions money uses ₹

## Definition of done
- [ ] `python app.py` starts on port 5001 with no errors
- [ ] `GET /login` renders the form; the form's `action` is generated by `url_for`
- [ ] Signing in as `demo@spendly.com` / `demo123` redirects (302) to `/`, and the
      landing page shows a one-time "Welcome back" message (gone on refresh)
- [ ] Email is matched case- and whitespace-insensitively (`  DEMO@Spendly.com `
      signs in)
- [ ] After signing in, the navbar shows the user's name and "Sign out" instead of
      "Sign in" / "Get started"
- [ ] A newly registered user (via `/register`) can sign in with their password
- [ ] Wrong password, unknown email, or blank fields each return 401 with
      "Invalid email or password." and set no session
- [ ] After a failed submit the email field keeps its value; the password field is empty
- [ ] Visiting `GET /login` while signed in redirects to `/`
- [ ] `GET /logout` clears the session, redirects to `/`, shows "You've been signed out"
      once, and the navbar returns to "Sign in" / "Get started"
- [ ] `GET /logout` while not signed in still redirects to `/` without error
- [ ] The "Account created — please sign in" flash from Step 2 still appears on `/login`
      exactly once
- [ ] New CSS uses variables only (no hex values)
- [ ] `pytest` passes (existing registration tests + new auth tests), and the test run
      does not modify `expense_tracker.db`
