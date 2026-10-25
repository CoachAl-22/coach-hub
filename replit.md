# Power2ADAPT Coach Hub

## Project Overview

A coaching staff management system for Power2ADAPT Athletics. Manages session rosters, coach availability, and SMS alerts.

## Features

- **Dashboard** - Weekly session overview with staffing status; automatically shows next term's first week when between terms
- **Roster management** - Term-by-term coach assignments with auto-generation; supports session cancellations (cancel/restore per date)
- **Availability** - SMS-based availability collection from coaches
- **SMS Alerts** - Timesheet reminders and custom messages via Twilio
- **Admin** - Manage coaches (activate/deactivate) and sessions (edit min/max coaches, toggle active)
- **Fixtures** - Weekend competitions and school fixtures calendar with coach assignments (weekday events go on the Roster instead)
- **Athlete Board** (`/athlete-board`) - Card grid of all active athletes; highlights today's sessions (by day_of_week) in orange; shows other sessions and latest PB results; links to Profile and Performance pages
- **Session Library** (`/performance/sessions`) - Searchable, filterable training session library; slide-out detail panel with Description/Structure/Tags/Notes tabs; inline session editor (name, type, event, phase, intensity, description, tags, structure targets, coach notes); duplicate button; `public.training_sessions` has `target_sets`, `target_reps`, `target_recovery_secs`, `target_intensity_pct`, `target_notes`; id column has sequence `public.training_sessions_id_seq`
- **Athlete Performance Dashboard** (`/athletes/<id>/performance`) - Chart.js line charts with Good/State/National benchmark reference lines, stats cards, results table; linked from athlete profile

## Coach Sign-in

- Coaches sign in with their existing username and password. Passwords are stored as hashes, not readable text.
- Coaches can change their own password under **Change Password** in the sidebar; admins can set a new password on the **Coaches** page.
- New coach passwords must be at least 12 characters. Failed sign-ins are limited per username and source address.
- Do not put live or default passwords in this file. Previously shared initial passwords should be rotated by an admin.
- Admins can send individual, 24-hour, one-use password setup links on **Coaches**. Inactive coaches can choose a password but remain inactive; admin accounts are excluded.
- Setup links carry their private token in the URL fragment, not the request path/query. Store only token hashes and setup timestamps, never passwords/private links in SMS logs.
- New authentication feature tables live in `public`, while existing coach accounts remain in `ch.coaches`. Custom `ch` changes were not included in the managed Publish diff during verification.
- The new schema source is `migrations/coach_password_setup.sql`, applied in development by `scripts/apply-dev-schema.py`. Verify the actual Publish diff includes new public tables; do not add production startup DDL.
- Password changes increment the version in `public.coach_auth_state`, invalidating older sessions. Sending a setup link does not change an existing password.
- Setup SMS prefers existing `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` secrets, or uses the Twilio connector via a Node bridge when neither is configured. It has no simulated-success fallback.
- `COACH_AUTH_BASE_URL` is production-only and must be the verified published URL. Keep `COACH_AUTH_SMS_ENABLED=0` until a read-only sender/authentication check succeeds; then enable only in production.

## Coaches

- Alistair Tait (Head Coach, Admin) — active
- Sami Merhi (Level 3) — active
- Georgia Middleton (Level 2) — active
- Sarai Hughes (Level 2) — active
- Geena Davy (Level 2) — active
- Declyn Tanner (Level 2) — active
- Miah Noble (Level 1) — active
- Blake Ireland (Level 2, Standby) — **inactive**
- Ella Wilson (Level 1) — **inactive**

## Session Min Coaches (production)

- Ballam Park Mon 17:30, Tue 16:30, Tue 17:30 → min 1
- Toorak College Thu 15:00 → min 3
- All others → default seeded values

## Tech Stack

- **Framework:** Flask 3.0 with Flask-Login
- **Database:** PostgreSQL via `DATABASE_URL` (schema: `ch`) — persistent across republishes
  - Dev: local `heliumdb` (Replit built-in PostgreSQL)
  - Production: separate database visible through Replit's production read-only queries; new public-schema feature tables use the managed Publish diff
- **SMS:** Twilio
- **Scheduling:** APScheduler with file lock (fcntl) to prevent double-sends with multiple Gunicorn workers
- **Google Sheets:** Service account integration for availability reference

## Access Control Rules

### Nav visibility (base.html)
- **All logged-in coaches:** Dashboard, Learning Hub, Roster, Fixtures
- **Admin only (nav + route):** Availability, Alerts, Performance section (Athlete Board, Athletes, Session Library)

### Route-level guards
- `@login_required` — all routes except `/availability/<token>` (public, no login needed — the SMS link coaches receive)
- `@admin_required` decorator — all `/athletes/*` and `/performance/sessions*` routes
- Fixtures write routes (`/fixtures/add`, `/fixtures/<id>/coaches`, `/fixtures/<id>/delete`) — inline `if not current_user.is_admin` check returning 403; GET `/fixtures` is all-coaches

### Pattern to follow for future routes
- View-only for all coaches: `@login_required` only
- Admin-only page: `@login_required` + `@admin_required`
- Admin-only action within a shared page: inline `if not current_user.is_admin: return ..., 403`
- Public (no login): no decorators (e.g. availability form, login page)

## Important Notes

- `database.py` `_Connection.execute()` auto-converts `?` → `%s` for PostgreSQL compatibility
- `NOT is_active` does not work in PostgreSQL (integer column) — use `1 - is_active` instead
- Dev and production databases are **separate** — data changes must be made via the production API after publishing
- `session_cancellations` table: `(session_id, date, reason)` PRIMARY KEY `(session_id, date)`
- Session overrides: sessions 1, 3, 8 end June 19 for Term 2
- `public.training_sessions` — 79 seeded training sessions (from coach_hub.jsx); separate from `public.sessions` (Setmore appointments) and `ch.sessions` (coaching schedule)
- `public.athletes.is_active` is BOOLEAN (use `WHERE is_active = true`), unlike `ch.coaches.is_active` which is INTEGER
- Production Neon DB public-schema tables created via `_init_public_schema()` in `database.py` (runs at startup with `CREATE TABLE IF NOT EXISTS`) — never recreates existing tables like `public.sessions`, `public.clients`, etc.

## Required Secrets

- `SECRET_KEY` - Flask session secret (**required in production** — app logs a CRITICAL warning if missing; falls back to `SESSION_SECRET`)
- `SESSION_SECRET` - Alternative name for Flask session secret (used if `SECRET_KEY` is absent)
- `GOOGLE_CREDENTIALS_JSON` - Google service account JSON
- `GOOGLE_SHEET_ID` - Google Sheet ID (has default)
- `TWILIO_ACCOUNT_SID` - Twilio account SID
- `TWILIO_AUTH_TOKEN` - Twilio auth token
- `TWILIO_FROM_NUMBER` - Twilio phone number (has default: +19786253879)
- `APP_URL` - Public URL for availability form links
- `APP_ADMIN_PASSWORD` - Required to create the initial admin account when seeding a fresh database. Never print it to logs.
- `DEFAULT_COACH_PASSWORD` - Optional initial shared password on a fresh database. If omitted, coaches must be assigned individual passwords by an admin before signing in.

**Note:** The seed passwords (`APP_ADMIN_PASSWORD`, `DEFAULT_COACH_PASSWORD`) only matter on a **fresh database** (when the `coaches` table is empty). Existing production passwords are stored as hashed values and are unaffected by these env vars.

**Note:** Set `FLASK_TESTING=1` to suppress APScheduler startup (useful for test runs that import `main.py`).

## Project Structure

```
main.py           - Flask app and all routes
config.py         - Configuration from environment variables
database.py       - PostgreSQL connection wrapper + seed data (schema: ch)
app.py            - Entry point (imports main.py)
services/
  term_dates.py   - Term date utilities
  google_sheets.py - Google Sheets integration
  twilio_service.py - SMS sending
  scheduler.py    - Background task scheduler (file-locked)
templates/        - Jinja2 HTML templates (dark theme)
static/css/       - Custom styles
```
