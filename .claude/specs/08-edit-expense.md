# Spec: Edit Expense

## Overview
Step 8 replaces the `/expenses/<id>/edit` placeholder with a working form that
lets a signed-in user correct one of their own expenses (amount, category,
date, description). Step 7 made it possible to add expenses, but a typo in the
amount or a wrong category could only be fixed by editing the database by
hand. This step adds an "Edit" link to every row of the profile page's
Transaction history, opens a form pre-filled with the expense's current
values, validates the changes with the same rules as Step 7, and saves them.
On success the user is redirected to `/profile` with a confirmation flash, and
the stats, transaction list and category breakdown reflect the edited values.
Users can only ever see or change their own expenses.

## Depends on
- Step 1: Database setup (`expenses` table and `CATEGORIES` tuple)
- Step 3: Login and logout (`session["user_id"]` identifies the owner)
- Steps 4–6: Profile page with live data and date filter (where the Edit links
  live and where the redirect lands)
- Step 7: Add expense (`validate_expense`, `parse_amount`, `parse_iso_date`,
  the expense form layout and `add_expense.css`)

## Routes
- `GET /expenses/<int:id>/edit` — render the edit form pre-filled with the
  expense's current amount, category, date and description — logged-in
- `POST /expenses/<int:id>/edit` — validate the form, update the expense,
  flash `"Expense updated"` (category `"success"`) and redirect to `/profile`;
  on validation error re-render the form with the error and the submitted
  values, status 400 — logged-in

Both methods:
- redirect to `/login` when signed out, and clear the session then redirect to
  `/login` when the session's user no longer exists (use `get_signed_in_user()`,
  same pattern as `/profile`, `/analytics` and `/expenses/add`)
- `abort(404)` when the expense doesn't exist **or belongs to another user** —
  the response must not reveal whether another user's expense id exists

The existing placeholder already uses the `edit_expense` endpoint name and the
`/expenses/<int:id>/edit` URL; keep both, just add `methods=["GET", "POST"]`.

## Database changes
No database changes. The existing `expenses` table already has every column
needed.

New helpers in `database/db.py`:
- `get_expense_by_id(expense_id, user_id)` — returns
  `{id, amount, category, date, description}` for the expense only if it
  belongs to `user_id` (`WHERE id = ? AND user_id = ?`), otherwise `None`.
  `description` is returned as `""` when `NULL`; `amount` as a float.
- `update_expense(expense_id, user_id, amount, category, expense_date, description)`
  — parameterised `UPDATE expenses SET amount = ?, category = ?, date = ?,
  description = ? WHERE id = ? AND user_id = ?`; stores an empty description as
  `NULL` (same as `create_expense`); returns `True` if a row was updated
  (`cur.rowcount == 1`), otherwise `False`.

Modified helper:
- `get_recent_transactions()` — also select and return `id` in each dict so the
  profile template can build Edit links. Existing keys and ordering unchanged.

## Templates
- **Create:** `templates/edit_expense.html` — extends `base.html`; loads the
  existing `add_expense.css` via `{% block head %}`; same layout and fields as
  `add_expense.html` (`amount`, `category`, `date`, `description`) with:
  - Title "Edit expense" and subtitle e.g. "Update the details of this expense"
  - Form `action="{{ url_for('edit_expense', id=expense_id) }}"`, `method="POST"`
  - All fields pre-filled from the stored expense on GET, and from the
    submitted values after a validation error (selected category kept)
  - Category options built from the `categories` list passed by the route
  - Date input `max="{{ today }}"`
  - Submit button "Save changes" and a "Cancel" link (`.btn-ghost`) back to `/profile`
  - Error block (`.auth-error`) shown when `error` is set
- **Modify:** `templates/profile.html`
  - Add a fifth column to the Transaction history table: header
    `<th scope="col"><span class="visually-hidden">Actions</span></th>` and a
    cell per row with an "Edit" link to `url_for('edit_expense', id=expense.id)`
    (add an `aria-label` that includes the description or date)
  - Update the empty-state row's `colspan` from 4 to 5; keep the exact text
    `No expenses yet.`
  - Do **not** add a Delete link (Step 9)

## Files to change
- `app.py`
  - Import `get_expense_by_id` and `update_expense` from `database.db`
  - Add an `EXPENSE_UPDATED = "Expense updated"` message constant
  - Replace the `edit_expense` placeholder with a `GET`/`POST` route that
    reuses `parse_amount`, `parse_iso_date` and `validate_expense`
  - Import `abort` from `flask`
- `database/db.py` — add `get_expense_by_id()` and `update_expense()`; return
  `id` from `get_recent_transactions()`
- `templates/profile.html` — Actions column with Edit links, colspan 5
- `static/css/profile.css` — style for the row Edit link (e.g. `.tx-action`,
  `.tx-edit-link`), using existing CSS variables
- `CLAUDE.md` — mark `GET/POST /expenses/<id>/edit` as implemented in the
  routes table and add `get_expense_by_id`, `update_expense` to the list of
  existing helpers

## Files to create
- `templates/edit_expense.html`

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
- DB logic stays in `database/db.py`; the route only loads, validates, calls
  `update_expense`, flashes and redirects
- Ownership is enforced in SQL (`AND user_id = ?`) in both the fetch and the
  update — `user_id` comes from the session only, never from a form field or
  the URL
- A missing or other user's expense → `abort(404)` (not 403, not a redirect,
  not a raw string)
- Reuse `validate_expense` unchanged so add and edit share identical rules and
  error messages (amount > 0 and ≤ 10,000,000; category in `CATEGORIES`; valid
  ISO date not in the future; description ≤ 200 chars after stripping)
- Validation errors re-render with status 400 and change nothing in the DB;
  success redirects (POST → redirect → GET)
- Money shown in ₹ via the `inr` filter; no `$` anywhere
- Do not implement the delete (Step 9) stub

## Definition of done
- [ ] Visiting `/expenses/1/edit` while signed out redirects to `/login`
- [ ] Every row in the profile page's Transaction history shows an "Edit" link
  pointing to `/expenses/<id>/edit` for that expense
- [ ] Clicking "Edit" opens a form pre-filled with that expense's amount,
  category, date and description
- [ ] Changing the amount and saving redirects to `/profile`, shows
  "Expense updated", and the row shows the new ₹ amount
- [ ] Total spent, transaction count and category breakdown on `/profile`
  reflect the edit (e.g. changing a category moves its total to the new category)
- [ ] Editing does not create a new expense — the transaction count is unchanged
- [ ] Clearing the description and saving succeeds and the row shows an empty
  description
- [ ] Submitting amount `0`, a negative amount, or `abc` re-renders the form
  (status 400) with the amount error, keeps the other submitted values, and the
  stored expense is unchanged
- [ ] A tampered category, a future date, a malformed date, or a description
  over 200 characters each show their Step 7 error message and change nothing
- [ ] Visiting or POSTing to `/expenses/<id>/edit` for another user's expense
  returns 404 and leaves that expense unchanged
- [ ] Visiting `/expenses/999999/edit` (non-existent id) returns 404
- [ ] Clicking "Cancel" returns to `/profile` without changing anything
- [ ] `/expenses/<id>/delete` is still the Step 9 placeholder
- [ ] Existing tests still pass (`pytest`)
