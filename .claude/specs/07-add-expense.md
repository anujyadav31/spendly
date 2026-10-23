# Spec: Add Expense

## Overview
Step 7 replaces the `/expenses/add` placeholder with a working form that lets a
signed-in user record a new expense (amount, category, date, optional
description). Until now every expense in the app came from `seed_db()`; this is
the first step where users create their own data, which makes the profile
page's stats, transaction list and category breakdown (Steps 5–6) reflect real
activity. On success the user is redirected to `/profile` with a confirmation
flash, and the new expense appears immediately in all three sections.

## Depends on
- Step 1: Database setup (`expenses` table and `CATEGORIES` tuple in `database/db.py`)
- Step 3: Login and logout (`session["user_id"]` identifies the owner)
- Step 4–5: Profile page with live data (the redirect target that shows the new expense)
- Step 6: Date filter on profile (new expenses must respect the active filter)

## Routes
- `GET /expenses/add` — render the add-expense form, with the date pre-filled to
  today and the category list built from `CATEGORIES` — logged-in
- `POST /expenses/add` — validate the form, insert the expense for the session
  user, flash `"Expense added"` (category `"success"`) and redirect to
  `/profile`; on validation error re-render the form with the error and the
  submitted values, status 400 — logged-in

Both methods redirect to `/login` when signed out, and clear the session then
redirect to `/login` when the session's user no longer exists (same pattern as
`/profile` and `/analytics`).

## Database changes
No database changes. The existing `expenses` table already has every column
needed (`user_id`, `amount`, `category`, `date`, `description`, `created_at`).

New helper in `database/db.py`:
- `create_expense(user_id, amount, category, expense_date, description)` —
  inserts one row with a parameterised `INSERT` and returns the new id.
  `description` is stored as `NULL` when empty.

## Templates
- **Create:** `templates/add_expense.html` — extends `base.html`; loads
  `add_expense.css` via `{% block head %}`; reuses the auth card layout
  (`.auth-section` / `.auth-container` / `.auth-card`, `.form-group`,
  `.form-input`, `.btn-submit`) with a form containing:
  - `amount` — `<input type="number" step="0.01" min="0.01">`, required
  - `category` — `<select class="form-input">` populated from the `categories`
    list passed by the route (never hardcoded in the template), required
  - `date` — `<input type="date">`, defaults to today, required
  - `description` — `<input type="text" maxlength="200">`, optional
  - Submit button "Add expense" and a "Cancel" link (`.btn-ghost`) back to `/profile`
  - Error block (`.auth-error`) shown when `error` is set
  - All submitted values re-populated after a validation error
    (`value="{{ amount or '' }}"` pattern, selected category kept)
- **Modify:** `templates/profile.html`
  - Wrap the "Transaction history" `<h2>` in a flex header with an
    "Add expense" button (`url_for('add_expense')`)
  - Empty-state row: keep the exact text `No expenses yet.` (existing tests
    assert it) and append a link to the add-expense page

## Files to change
- `app.py`
  - Import `create_expense` and `CATEGORIES` from `database.db`
  - Add a `validate_expense(amount, category, expense_date, description)`
    helper that returns the first error message or `None`
  - Replace the `add_expense` placeholder with a `GET`/`POST` route
- `database/db.py` — add `create_expense()`
- `templates/profile.html` — card header with "Add expense" button, empty-state link
- `static/css/profile.css` — card-header layout and compact button modifier
- `CLAUDE.md` — mark `/expenses/add` as implemented in the routes table and add
  `create_expense` to the list of existing helpers

## Files to create
- `templates/add_expense.html`
- `static/css/add_expense.css` — page-specific form styles (select appearance,
  button row)

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` via `get_db()` only
- Parameterised queries only — `?` placeholders, never f-strings in SQL
- Passwords hashed with werkzeug (no auth changes in this step)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- No inline `<style>` tags or `style=""` attributes
- Use `url_for()` for every internal link and the form `action`
- DB logic stays in `database/db.py`; the route only validates, calls
  `create_expense`, flashes and redirects
- `user_id` comes from `session` only — never from a form field
- Server-side validation (do not rely on HTML `required`/`min`), in order:
  - Amount: must parse as a number, be > 0 and ≤ 10,000,000; round to 2 decimals
    → "Please enter an amount greater than zero."
  - Category: must be one of `CATEGORIES` → "Please choose a valid category."
  - Date: must be a valid ISO `YYYY-MM-DD` date (reuse `parse_iso_date`) and not
    in the future → "Please enter a valid date (not in the future)."
  - Description: stripped; at most 200 characters
    → "Description must be 200 characters or fewer."
- Validation errors re-render with status 400; success redirects (POST →
  redirect → GET) so refreshing doesn't resubmit
- Money shown in ₹ via the `inr` filter; no `$` anywhere
- Do not implement the edit (Step 8) or delete (Step 9) stubs

## Definition of done
- [ ] Visiting `/expenses/add` while signed out redirects to `/login`
- [ ] Visiting `/expenses/add` while signed in shows the form with today's date
  pre-filled and all seven categories in the dropdown
- [ ] The profile page shows an "Add expense" button that links to `/expenses/add`
- [ ] Submitting a valid expense redirects to `/profile`, shows "Expense added",
  and the expense appears at the top of Transaction history with the ₹ amount
- [ ] Total spent, transaction count and the category breakdown on `/profile`
  update to include the new expense
- [ ] Leaving the description blank succeeds and the row shows an empty description
- [ ] Submitting amount `0`, a negative amount, or `abc` re-renders the form with
  the amount error and keeps the other values filled in
- [ ] Submitting a category not in the list (via a tampered request) shows the
  category error and nothing is inserted
- [ ] Submitting a future date or a malformed date shows the date error
- [ ] Submitting a description over 200 characters shows the description error
- [ ] An expense added by one user never appears on another user's profile
- [ ] Refreshing `/profile` after adding does not create a duplicate expense
- [ ] Clicking "Cancel" returns to `/profile` without inserting anything
- [ ] Existing tests still pass (`pytest`)
