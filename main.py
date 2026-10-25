import json
import os
import secrets
import hashlib
from datetime import datetime, timedelta, date
from functools import wraps

import pytz
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory, session
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Config
from database import get_db, init_db
from services.term_dates import get_session_dates_for_term, get_current_or_next_term
from services.session_schedule import (
    is_within_effective_session_bounds,
    load_week_session_schedules,
    session_occurs_in_week,
)
from services.google_sheets import get_sheet_availability
from services.twilio_service import send_sms
from services.sms_templates import SMS_TEMPLATES, personalize_sms
from services.scheduler import start_scheduler
from collections import OrderedDict
from services.coach_password_setup import coach_setup, setup_statuses, revoke_setup_links
from services.coach_auth_state import get_auth_version, bump_auth_version
from learning_content import INDUCTION_MODULES, LESSON_WEEKS, EMERGING_LESSON_WEEKS, EMERGING_T2_LESSON_WEEKS, FOUNDATION_T2_LESSON_WEEKS, PROGRESSION_LEVELS
app = Flask(__name__)
app.config.from_object(Config)
app.register_blueprint(coach_setup)
Config.validate()
# Replit forwards HTTP requests through one trusted proxy. Take only its
# rightmost forwarded client address, never an arbitrary client-supplied hop.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)
app.jinja_env.filters['from_json'] = json.loads

def _format_date(d):
    try:
        return date.fromisoformat(d).strftime('%-d %b %Y')
    except Exception:
        return d

def _days_until(d):
    try:
        delta = (date.fromisoformat(d) - date.today()).days
        if delta == 0:
            return 'Today'
        elif delta == 1:
            return 'Tomorrow'
        elif delta > 1:
            return f'In {delta} days'
        else:
            return f'{abs(delta)} days ago'
    except Exception:
        return ''

app.jinja_env.filters['format_date'] = _format_date
app.jinja_env.filters['days_until'] = _days_until

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

AEST = pytz.timezone('Australia/Melbourne')

DAY_ORDER = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']


# ---------------------------------------------------------------------------
# User model
# ---------------------------------------------------------------------------

class User(UserMixin):
    def __init__(self, row):
        self.id = row['id']
        self.name = row['name']
        self.username = row['username']
        self.is_admin = bool(row['is_admin'])
        self.is_standby = bool(row['is_standby'])
        self.auth_version = row.get('auth_version', 0)

    def get_id(self):
        return str(self.id)


@login_manager.user_loader
def load_user(user_id):
    db = get_db()
    try:
        row = db.execute('SELECT * FROM coaches WHERE id = %s', (user_id,)).fetchone()
        if row:
            row = dict(row)
            row['auth_version'] = get_auth_version(db, row['id'])
    finally:
        db.close()
    if not row or not row['is_active'] or session.get('auth_version', 0) != row['auth_version']:
        return None
    return User(row)


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_admin:
            return render_template('access_denied.html',
                title='Performance',
                message='Head Coach or Admin login required to access this section.'
            ), 403
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

MAX_LOGIN_FAILURES = 5


def _login_attempt_key(coach_id):
    # Unknown usernames share a bucket per source, rather than creating one
    # database row per attacker-supplied username. Only trust the socket peer,
    # not client-supplied forwarded headers.
    identity = f"{request.remote_addr or 'unknown'}:{coach_id or 'unknown'}"
    return hashlib.sha256(identity.encode('utf-8')).hexdigest()


def _valid_form_token(name):
    token = session.get(name, '')
    return bool(token) and secrets.compare_digest(
        token, request.form.get('csrf_token', '')
    )


@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('login.html')


@app.route('/apple-touch-icon.png')
@app.route('/apple-touch-icon-precomposed.png')
def apple_touch_icon():
    return send_from_directory(app.static_folder, 'apple-touch-icon.png')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        password = request.form.get('password', '')
        db = get_db()
        try:
            row = db.execute(
                '''SELECT c.*, COALESCE(a.auth_version, 0) AS auth_version
                   FROM coaches c LEFT JOIN public.coach_auth_state a ON a.coach_id = c.id
                   WHERE c.username = %s AND c.is_active = 1''', (username,)
            ).fetchone()
            attempt_key = _login_attempt_key(row['id'] if row else None)
            # The UPSERT is atomic, so simultaneous requests cannot all pass a
            # stale pre-check. A successful sign-in removes its attempt record.
            attempt = db.execute('''
                INSERT INTO login_attempts (attempt_key, failures, window_started)
                VALUES (%s, 1, NOW())
                ON CONFLICT (attempt_key) DO UPDATE SET
                    failures = CASE
                        WHEN login_attempts.window_started < NOW() - INTERVAL '15 minutes'
                        THEN 1 ELSE login_attempts.failures + 1 END,
                    window_started = CASE
                        WHEN login_attempts.window_started < NOW() - INTERVAL '15 minutes'
                        THEN NOW() ELSE login_attempts.window_started END
                RETURNING failures
            ''', (attempt_key,)).fetchone()
            if attempt['failures'] > MAX_LOGIN_FAILURES:
                db.commit()
                flash('Too many sign-in attempts. Please try again in 15 minutes.', 'error')
                return render_template('login.html'), 429
            if row and row['password_hash'] and check_password_hash(row['password_hash'], password):
                row = dict(row)
                db.execute('DELETE FROM login_attempts WHERE attempt_key = %s', (attempt_key,))
                db.commit()
                login_user(User(row))
                session['auth_version'] = row['auth_version']
                return redirect(url_for('dashboard'))
            if secrets.randbelow(100) == 0:
                db.execute(
                    "DELETE FROM login_attempts WHERE window_started < NOW() - INTERVAL '1 day'"
                )
            db.commit()
        finally:
            db.close()
        flash('Invalid username or password.', 'error')
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route('/account/password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'GET':
        session['password_csrf'] = secrets.token_urlsafe(32)
        return render_template('change_password.html')

    if not _valid_form_token('password_csrf'):
        flash('Please reload the page and try again.', 'error')
        return redirect(url_for('change_password'))

    current_password = request.form.get('current_password', '')
    new_password = request.form.get('new_password', '')
    confirmation = request.form.get('confirm_password', '')
    db = get_db()
    try:
        row = db.execute(
            'SELECT password_hash, is_active FROM coaches WHERE id = %s FOR UPDATE',
            (current_user.id,)
        ).fetchone()
        auth_version = get_auth_version(db, current_user.id) if row else 0
        if not row or not row['is_active'] or auth_version != session.get('auth_version', 0):
            logout_user()
            flash('Your account changed in another session. Please sign in again.', 'error')
            return redirect(url_for('login'))
        if not row['password_hash'] or not check_password_hash(
            row['password_hash'], current_password
        ):
            flash('Current password is incorrect.', 'error')
        elif len(new_password) < 12:
            flash('New password must be at least 12 characters.', 'error')
        elif new_password != confirmation:
            flash('New passwords do not match.', 'error')
        elif check_password_hash(row['password_hash'], new_password):
            flash('Choose a password different from your current one.', 'error')
        else:
            db.execute(
                'UPDATE coaches SET password_hash = %s WHERE id = %s',
                (generate_password_hash(new_password), current_user.id)
            )
            auth_version = bump_auth_version(db, current_user.id)
            revoke_setup_links(db, current_user.id)
            db.commit()
            session['auth_version'] = auth_version
            session.pop('password_csrf', None)
            flash('Your password has been changed.', 'success')
            return redirect(url_for('dashboard'))
    finally:
        db.close()
    return redirect(url_for('change_password'))


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.route('/dashboard')
@login_required
def dashboard():
    db = get_db()
    today = datetime.now(AEST).date()

    # Check if today falls within an active term
    in_term = db.execute(
        'SELECT 1 FROM terms WHERE start_date <= %s AND end_date >= %s LIMIT 1',
        (today.isoformat(), today.isoformat())
    ).fetchone()

    if in_term:
        week_start = today - timedelta(days=today.weekday())
        between_terms = False
    else:
        # Between terms — jump ahead to the next term's first week
        next_term = db.execute(
            'SELECT * FROM terms WHERE start_date > %s ORDER BY start_date LIMIT 1',
            (today.isoformat(),)
        ).fetchone()
        if next_term:
            next_start = date.fromisoformat(next_term['start_date'])
            week_start = next_start - timedelta(days=next_start.weekday())
            between_terms = True
        else:
            week_start = today - timedelta(days=today.weekday())
            between_terms = False

    week_end = week_start + timedelta(days=6)
    term_schedules = load_week_session_schedules(db, week_start, week_end)

    sessions = db.execute(
        'SELECT * FROM sessions WHERE is_active = 1 ORDER BY '
        "CASE day_of_week WHEN 'Monday' THEN 1 WHEN 'Tuesday' THEN 2 WHEN 'Wednesday' THEN 3 "
        "WHEN 'Thursday' THEN 4 WHEN 'Friday' THEN 5 ELSE 6 END, start_time"
    ).fetchall()

    # Load cancellations for this week
    cancellations = db.execute(
        'SELECT session_id, date FROM session_cancellations WHERE date >= %s AND date <= %s',
        (week_start.isoformat(), week_end.isoformat())
    ).fetchall()
    cancelled_set = {(r['session_id'], r['date']) for r in cancellations}

    # Build this week's schedule with roster info
    week_schedule = []
    for s in sessions:
        # Find the date this session falls on this week
        day_num = DAY_ORDER.index(s['day_of_week'])
        session_date = week_start + timedelta(days=day_num)
        if session_date > week_end:
            continue
        if not session_occurs_in_week(s['id'], session_date, term_schedules):
            continue
        if (s['id'], session_date.isoformat()) in cancelled_set:
            continue

        # Get roster entries for this session on this date
        entries = db.execute('''
            SELECT re.*, c.name as coach_name FROM roster_entries re
            JOIN coaches c ON re.coach_id = c.id
            WHERE re.session_id = %s AND re.date = %s
        ''', (s['id'], session_date.isoformat())).fetchall()

        assigned = len(entries)
        if assigned >= s['min_coaches']:
            status = 'staffed' if assigned >= s['min_coaches'] else 'partial'
            status = 'full' if assigned >= s['max_coaches'] else 'staffed'
        else:
            status = 'understaffed' if assigned > 0 else 'empty'

        week_schedule.append({
            'session': s,
            'date': session_date,
            'entries': entries,
            'assigned': assigned,
            'status': status,
            'is_today': session_date == today,
        })

    # Stats
    terms = db.execute('SELECT * FROM terms ORDER BY start_date').fetchall()
    current_term = get_current_or_next_term(db)

    total_this_week = len(week_schedule)
    gaps = sum(1 for w in week_schedule if w['status'] in ('understaffed', 'empty'))

    db.close()
    return render_template('dashboard.html',
                           week_schedule=week_schedule,
                           today=today,
                           week_start=week_start,
                           week_end=week_end,
                           terms=terms,
                           current_term=current_term,
                           total_this_week=total_this_week,
                           gaps=gaps,
                           between_terms=between_terms)


# ---------------------------------------------------------------------------
# Roster
# ---------------------------------------------------------------------------

@app.route('/roster')
@login_required
def roster():
    if not current_user.is_admin:
        return redirect(url_for('my_roster'))
    db = get_db()
    current_term = get_current_or_next_term(db)
    db.close()
    if current_term:
        return redirect(url_for('roster_term', term_id=current_term['id']))
    return redirect(url_for('roster_term', term_id=1))


@app.route('/my-roster')
@login_required
def my_roster():
    if current_user.is_admin:
        return redirect(url_for('roster'))

    db = get_db()
    current_term = get_current_or_next_term(db)
    if not current_term:
        current_term = db.execute('SELECT * FROM terms ORDER BY start_date LIMIT 1').fetchone()

    if not current_term:
        db.close()
        return render_template('my_roster.html', weeks=[], term=None)

    term_id = current_term['id']

    rows = db.execute('''
        SELECT re.date, s.id AS session_id, s.day_of_week,
               s.start_time, s.end_time, s.location, s.programs,
               sc.reason AS cancel_reason,
               CASE WHEN sc.session_id IS NOT NULL THEN TRUE ELSE FALSE END AS is_cancelled
        FROM roster_entries re
        JOIN sessions s ON re.session_id = s.id
        LEFT JOIN session_cancellations sc
            ON sc.session_id = s.id AND sc.date = re.date
        WHERE re.coach_id = %s AND re.term_id = %s
        ORDER BY re.date, s.start_time
    ''', (current_user.id, term_id)).fetchall()

    co_coach_rows = db.execute('''
        SELECT re.session_id, re.date, c.name
        FROM roster_entries re
        JOIN coaches c ON re.coach_id = c.id
        WHERE re.term_id = %s
          AND re.coach_id != %s
          AND (re.session_id, re.date) IN (
              SELECT session_id, date FROM roster_entries
              WHERE coach_id = %s AND term_id = %s
          )
        ORDER BY re.date, re.session_id, c.name
    ''', (term_id, current_user.id, current_user.id, term_id)).fetchall()

    co_coaches_map = {}
    for row in co_coach_rows:
        d = row['date'] if isinstance(row['date'], date) else date.fromisoformat(str(row['date'])[:10])
        key = (row['session_id'], d.isoformat())
        first_name = row['name'].split()[0] if row['name'] else row['name']
        co_coaches_map.setdefault(key, []).append(first_name)

    db.close()

    week_map = {}
    for r in rows:
        d = r['date']
        session_date = d if isinstance(d, date) else date.fromisoformat(str(d)[:10])
        week_start = session_date - timedelta(days=session_date.weekday())
        key = week_start.isoformat()
        if key not in week_map:
            week_map[key] = {'week_start': week_start, 'sessions': []}
        co_key = (r['session_id'], session_date.isoformat())
        week_map[key]['sessions'].append({
            'date': session_date,
            'day_of_week': r['day_of_week'],
            'start_time': r['start_time'],
            'end_time': r['end_time'],
            'location': r['location'],
            'programs': r['programs'],
            'is_cancelled': bool(r['is_cancelled']),
            'cancel_reason': r['cancel_reason'] or '',
            'co_coaches': co_coaches_map.get(co_key, []),
        })

    weeks = [week_map[k] for k in sorted(week_map.keys())]
    return render_template('my_roster.html', weeks=weeks, term=current_term)


@app.route('/team-roster')
@login_required
def team_roster():
    db = get_db()
    terms = db.execute('SELECT * FROM terms ORDER BY start_date').fetchall()
    current_term = get_current_or_next_term(db)
    if not current_term:
        current_term = db.execute('SELECT * FROM terms ORDER BY start_date LIMIT 1').fetchone()

    if not current_term:
        db.close()
        return render_template('team_roster.html', weeks=[], term=None, terms=[], current_term_id=None)

    term_id = current_term['id']

    sessions = db.execute(
        'SELECT * FROM sessions WHERE is_active = 1 ORDER BY '
        "CASE day_of_week WHEN 'Monday' THEN 1 WHEN 'Tuesday' THEN 2 WHEN 'Wednesday' THEN 3 "
        "WHEN 'Thursday' THEN 4 WHEN 'Friday' THEN 5 ELSE 6 END, start_time"
    ).fetchall()

    override_rows = db.execute(
        'SELECT session_id, start_date, end_date FROM session_overrides WHERE term_id = %s', (term_id,)
    ).fetchall()
    session_end_overrides = {r['session_id']: date.fromisoformat(r['end_date']) for r in override_rows}
    session_start_overrides = {r['session_id']: date.fromisoformat(r['start_date']) for r in override_rows if r['start_date']}

    cancel_rows = db.execute(
        'SELECT session_id, date, reason FROM session_cancellations'
    ).fetchall()
    cancelled_map = {}
    for r in cancel_rows:
        cancelled_map[(r['session_id'], r['date'])] = r['reason'] or ''

    term_start = date.fromisoformat(current_term['start_date'])
    term_end = date.fromisoformat(current_term['end_date'])

    all_entries = db.execute('''
        SELECT re.session_id, re.date, c.name as coach_name
        FROM roster_entries re
        JOIN coaches c ON re.coach_id = c.id
        WHERE re.term_id = %s
        ORDER BY re.date, re.session_id, c.name
    ''', (term_id,)).fetchall()

    entries_map = {}
    for row in all_entries:
        d = row['date'] if isinstance(row['date'], date) else date.fromisoformat(str(row['date'])[:10])
        key = (row['session_id'], d.isoformat())
        first_name = row['coach_name'].split()[0] if row['coach_name'] else row['coach_name']
        entries_map.setdefault(key, []).append(first_name)

    db.close()

    weeks = []
    week_start = term_start - timedelta(days=term_start.weekday())

    while week_start <= term_end:
        week_sessions = []
        for s in sessions:
            day_num = DAY_ORDER.index(s['day_of_week'])
            session_date = week_start + timedelta(days=day_num)
            session_start = session_start_overrides.get(s['id'], term_start)
            session_end = session_end_overrides.get(s['id'], term_end)
            if session_date < session_start or session_date > session_end:
                continue

            is_cancelled = (s['id'], session_date.isoformat()) in cancelled_map
            cancel_reason = cancelled_map.get((s['id'], session_date.isoformat()), '')
            coaches_on = entries_map.get((s['id'], session_date.isoformat()), [])

            week_sessions.append({
                'session': s,
                'date': session_date,
                'coaches': coaches_on,
                'is_cancelled': is_cancelled,
                'cancel_reason': cancel_reason,
            })

        if week_sessions:
            weeks.append({
                'week_start': week_start,
                'sessions': sorted(week_sessions, key=lambda x: (DAY_ORDER.index(x['session']['day_of_week']), x['session']['start_time']))
            })
        week_start += timedelta(days=7)

    current_coach_name = current_user.name.split()[0] if current_user.name else ''
    return render_template('team_roster.html',
                           weeks=weeks,
                           term=current_term,
                           terms=terms,
                           current_term_id=term_id,
                           current_coach_name=current_coach_name)


@app.route('/team-roster/<int:term_id>')
@login_required
def team_roster_term(term_id):
    db = get_db()
    terms = db.execute('SELECT * FROM terms ORDER BY start_date').fetchall()
    term = db.execute('SELECT * FROM terms WHERE id = %s', (term_id,)).fetchone()
    if not term:
        db.close()
        flash('Term not found.', 'error')
        return redirect(url_for('team_roster'))

    sessions = db.execute(
        'SELECT * FROM sessions WHERE is_active = 1 ORDER BY '
        "CASE day_of_week WHEN 'Monday' THEN 1 WHEN 'Tuesday' THEN 2 WHEN 'Wednesday' THEN 3 "
        "WHEN 'Thursday' THEN 4 WHEN 'Friday' THEN 5 ELSE 6 END, start_time"
    ).fetchall()

    override_rows = db.execute(
        'SELECT session_id, start_date, end_date FROM session_overrides WHERE term_id = %s', (term_id,)
    ).fetchall()
    session_end_overrides = {r['session_id']: date.fromisoformat(r['end_date']) for r in override_rows}
    session_start_overrides = {r['session_id']: date.fromisoformat(r['start_date']) for r in override_rows if r['start_date']}

    cancel_rows = db.execute(
        'SELECT session_id, date, reason FROM session_cancellations'
    ).fetchall()
    cancelled_map = {}
    for r in cancel_rows:
        cancelled_map[(r['session_id'], r['date'])] = r['reason'] or ''

    term_start = date.fromisoformat(term['start_date'])
    term_end = date.fromisoformat(term['end_date'])

    all_entries = db.execute('''
        SELECT re.session_id, re.date, c.name as coach_name
        FROM roster_entries re
        JOIN coaches c ON re.coach_id = c.id
        WHERE re.term_id = %s
        ORDER BY re.date, re.session_id, c.name
    ''', (term_id,)).fetchall()

    entries_map = {}
    for row in all_entries:
        d = row['date'] if isinstance(row['date'], date) else date.fromisoformat(str(row['date'])[:10])
        key = (row['session_id'], d.isoformat())
        first_name = row['coach_name'].split()[0] if row['coach_name'] else row['coach_name']
        entries_map.setdefault(key, []).append(first_name)

    db.close()

    weeks = []
    week_start = term_start - timedelta(days=term_start.weekday())

    while week_start <= term_end:
        week_sessions = []
        for s in sessions:
            day_num = DAY_ORDER.index(s['day_of_week'])
            session_date = week_start + timedelta(days=day_num)
            session_start = session_start_overrides.get(s['id'], term_start)
            session_end = session_end_overrides.get(s['id'], term_end)
            if session_date < session_start or session_date > session_end:
                continue

            is_cancelled = (s['id'], session_date.isoformat()) in cancelled_map
            cancel_reason = cancelled_map.get((s['id'], session_date.isoformat()), '')
            coaches_on = entries_map.get((s['id'], session_date.isoformat()), [])

            week_sessions.append({
                'session': s,
                'date': session_date,
                'coaches': coaches_on,
                'is_cancelled': is_cancelled,
                'cancel_reason': cancel_reason,
            })

        if week_sessions:
            weeks.append({
                'week_start': week_start,
                'sessions': sorted(week_sessions, key=lambda x: (DAY_ORDER.index(x['session']['day_of_week']), x['session']['start_time']))
            })
        week_start += timedelta(days=7)

    current_coach_name = current_user.name.split()[0] if current_user.name else ''
    return render_template('team_roster.html',
                           weeks=weeks,
                           term=term,
                           terms=terms,
                           current_term_id=term_id,
                           current_coach_name=current_coach_name)


@app.route('/roster/<int:term_id>')
@login_required
def roster_term(term_id):
    if not current_user.is_admin:
        return redirect(url_for('my_roster'))
    db = get_db()
    terms = db.execute('SELECT * FROM terms ORDER BY start_date').fetchall()
    term = db.execute('SELECT * FROM terms WHERE id = %s', (term_id,)).fetchone()
    if not term:
        db.close()
        flash('Term not found.', 'error')
        return redirect(url_for('dashboard'))

    sessions = db.execute(
        'SELECT * FROM sessions WHERE is_active = 1 ORDER BY '
        "CASE day_of_week WHEN 'Monday' THEN 1 WHEN 'Tuesday' THEN 2 WHEN 'Wednesday' THEN 3 "
        "WHEN 'Thursday' THEN 4 WHEN 'Friday' THEN 5 ELSE 6 END, start_time"
    ).fetchall()

    coaches = db.execute(
        'SELECT * FROM coaches WHERE is_active = 1 ORDER BY name'
    ).fetchall()

    # Load any session-specific date overrides for this term
    override_rows = db.execute(
        'SELECT session_id, start_date, end_date FROM session_overrides WHERE term_id = %s', (term_id,)
    ).fetchall()
    session_end_overrides = {r['session_id']: date.fromisoformat(r['end_date']) for r in override_rows}
    session_start_overrides = {r['session_id']: date.fromisoformat(r['start_date']) for r in override_rows if r['start_date']}

    # Load cancellations for this term's date range
    cancel_rows = db.execute(
        'SELECT session_id, date, reason FROM session_cancellations'
    ).fetchall()
    cancelled_map = {}   # (session_id, date_str) -> reason
    for r in cancel_rows:
        cancelled_map[(r['session_id'], r['date'])] = r['reason'] or ''

    # Build week-by-week roster
    term_start = date.fromisoformat(term['start_date'])
    term_end = date.fromisoformat(term['end_date'])

    weeks = []
    week_start = term_start - timedelta(days=term_start.weekday())

    while week_start <= term_end:
        week_sessions = []
        for s in sessions:
            day_num = DAY_ORDER.index(s['day_of_week'])
            session_date = week_start + timedelta(days=day_num)
            session_start = session_start_overrides.get(s['id'], term_start)
            session_end = session_end_overrides.get(s['id'], term_end)
            if session_date < session_start or session_date > session_end:
                continue

            is_cancelled = (s['id'], session_date.isoformat()) in cancelled_map
            cancel_reason = cancelled_map.get((s['id'], session_date.isoformat()), '')

            entries = db.execute('''
                SELECT re.*, c.name as coach_name, c.id as coach_id
                FROM roster_entries re
                JOIN coaches c ON re.coach_id = c.id
                WHERE re.session_id = %s AND re.date = %s AND re.term_id = %s
            ''', (s['id'], session_date.isoformat(), term_id)).fetchall()

            assigned = len(entries)
            if is_cancelled:
                status = 'cancelled'
            elif assigned == 0:
                status = 'empty'
            elif assigned < s['min_coaches']:
                status = 'understaffed'
            elif assigned >= s['max_coaches']:
                status = 'full'
            else:
                status = 'staffed'

            week_sessions.append({
                'session': s,
                'date': session_date,
                'entries': entries,
                'assigned': assigned,
                'status': status,
                'is_cancelled': is_cancelled,
                'cancel_reason': cancel_reason,
            })

        if week_sessions:
            weeks.append({
                'week_start': week_start,
                'sessions': sorted(week_sessions, key=lambda x: (DAY_ORDER.index(x['session']['day_of_week']), x['session']['start_time']))
            })
        week_start += timedelta(days=7)

    db.close()
    return render_template('roster.html',
                           term=term,
                           terms=terms,
                           weeks=weeks,
                           coaches=coaches,
                           is_admin=current_user.is_admin)


@app.route('/roster/<int:term_id>/assign', methods=['POST'])
@login_required
def roster_assign(term_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorised'}), 403

    data = request.get_json()
    session_id = data.get('session_id')
    coach_id = data.get('coach_id')
    roster_date = data.get('date')
    force = data.get('force', False)

    db = get_db()
    try:
        schedule = db.execute('''
            SELECT t.start_date AS term_start, t.end_date AS term_end,
                   so.start_date AS override_start, so.end_date AS override_end
            FROM terms t
            JOIN sessions s ON s.id = %s
            LEFT JOIN session_overrides so ON so.session_id = s.id AND so.term_id = t.id
            WHERE t.id = %s
        ''', (session_id, term_id)).fetchone()
        if not schedule:
            db.close()
            return jsonify({'error': 'Term or session not found.'}), 404

        try:
            assignment_date = date.fromisoformat(roster_date)
        except (TypeError, ValueError):
            db.close()
            return jsonify({'error': 'Invalid assignment date.'}), 400

        if not is_within_effective_session_bounds(
                assignment_date, schedule['term_start'], schedule['term_end'], schedule):
            db.close()
            return jsonify({'error': 'Assignment date is outside this term or session dates.'}), 400

        coach = db.execute('SELECT name FROM coaches WHERE id = %s', (coach_id,)).fetchone()

        # Check availability unless admin is forcing the assignment
        warning = None
        if not force:
            resp = db.execute(
                'SELECT * FROM availability_responses WHERE coach_id = %s AND term_id = %s',
                (coach_id, term_id)
            ).fetchone()
            if resp:
                unavailable_dates = json.loads(resp['unavailable_dates'] or '[]')
                weekly = json.loads(resp['weekly_availability'] or '{}')
                day_name = date.fromisoformat(roster_date).strftime('%A')

                if roster_date in unavailable_dates:
                    warning = f"{coach['name']} marked {roster_date} as unavailable."
                else:
                    time_pref = weekly.get(day_name, 'all')
                    if time_pref is False or time_pref == 'unavailable':
                        warning = f"{coach['name']} marked {day_name}s as unavailable this term."
                    elif time_pref == 'standby':
                        warning = f"{coach['name']} is standby only on {day_name}s."
                    elif time_pref in ('am', 'pm'):
                        session = db.execute('SELECT start_time FROM sessions WHERE id = %s', (session_id,)).fetchone()
                        if session:
                            session_hour = int(session['start_time'].split(':')[0])
                            if time_pref == 'am' and session_hour >= 12:
                                warning = f"{coach['name']} is only available AM on {day_name}s — this session starts at {session['start_time']}."
                            elif time_pref == 'pm' and session_hour < 12:
                                warning = f"{coach['name']} is only available PM/Eve on {day_name}s — this session starts at {session['start_time']}."

        if warning and not force:
            db.close()
            return jsonify({'warning': warning, 'coach_name': coach['name']})

        db.execute('''
            INSERT INTO roster_entries (term_id, session_id, date, coach_id)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (term_id, session_id, date, coach_id) DO NOTHING
        ''', (term_id, session_id, roster_date, coach_id))
        db.commit()
        db.close()
        return jsonify({'success': True, 'coach_name': coach['name']})
    except Exception as e:
        db.close()
        return jsonify({'error': str(e)}), 500


@app.route('/roster/<int:term_id>/fill_term', methods=['POST'])
@login_required
def roster_fill_term(term_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorised'}), 403

    data = request.get_json()
    session_id = data.get('session_id')
    coach_id = data.get('coach_id')

    db = get_db()
    try:
        term = db.execute('SELECT * FROM terms WHERE id = %s', (term_id,)).fetchone()
        sess = db.execute('SELECT * FROM sessions WHERE id = %s', (session_id,)).fetchone()
        coach = db.execute('SELECT name FROM coaches WHERE id = %s', (coach_id,)).fetchone()

        if not term or not sess or not coach:
            db.close()
            return jsonify({'error': 'Not found'}), 404

        override = db.execute(
            'SELECT end_date FROM session_overrides WHERE session_id = %s AND term_id = %s',
            (session_id, term_id)
        ).fetchone()

        term_start = date.fromisoformat(term['start_date'])
        term_end = date.fromisoformat(override['end_date'] if override else term['end_date'])
        day_name = sess['day_of_week']

        cancel_rows_ft = db.execute('SELECT session_id, date FROM session_cancellations').fetchall()
        cancelled_ft = {(r['session_id'], r['date']) for r in cancel_rows_ft}

        all_dates = []
        current = term_start
        while current <= term_end:
            if current.strftime('%A') == day_name:
                if (session_id, current.isoformat()) not in cancelled_ft:
                    all_dates.append(current.isoformat())
            current += timedelta(days=1)

        added = 0
        for d in all_dates:
            existing = db.execute(
                'SELECT 1 FROM roster_entries WHERE term_id=%s AND session_id=%s AND date=%s AND coach_id=%s',
                (term_id, session_id, d, coach_id)
            ).fetchone()
            if not existing:
                db.execute(
                    'INSERT INTO roster_entries (term_id, session_id, date, coach_id) VALUES (%s,%s,%s,%s) ON CONFLICT (term_id, session_id, date, coach_id) DO NOTHING',
                    (term_id, session_id, d, coach_id)
                )
                added += 1

        db.commit()
        db.close()
        return jsonify({'success': True, 'added': added, 'total': len(all_dates), 'coach_name': coach['name']})
    except Exception as e:
        db.close()
        return jsonify({'error': str(e)}), 500


@app.route('/roster/<int:term_id>/cancel_date', methods=['POST'])
@login_required
def roster_cancel_date(term_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorised'}), 403
    data = request.get_json()
    session_id = data.get('session_id')
    roster_date = data.get('date')
    reason = data.get('reason', '')
    db = get_db()
    result = db.execute(
        'INSERT INTO session_cancellations (session_id, date, reason) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING',
        (session_id, roster_date, reason)
    )
    db.commit()
    is_new_cancellation = result.rowcount > 0

    # Send SMS to each assigned coach with a mobile number (only for new cancellations)
    if is_new_cancellation:
        try:
            from datetime import datetime as _dt
            sess_row = db.execute(
                'SELECT location, day_of_week, start_time FROM sessions WHERE id = %s',
                (session_id,)
            ).fetchone()
            coaches_rows = db.execute(
                '''SELECT c.name, c.mobile
                   FROM roster_entries re
                   JOIN coaches c ON c.id = re.coach_id
                   WHERE re.term_id = %s AND re.session_id = %s AND re.date = %s
                     AND c.mobile IS NOT NULL AND c.mobile <> \'\'
                ''',
                (term_id, session_id, roster_date)
            ).fetchall()

            if sess_row and coaches_rows:
                parsed_date = _dt.strptime(roster_date, '%Y-%m-%d')
                friendly_date = parsed_date.strftime('%A %-d %B')
                location = sess_row['location']
                start_time = sess_row['start_time']
                msg = f"Your {location} session on {friendly_date} at {start_time} has been cancelled."
                if reason:
                    msg += f" Reason: {reason}."
                for coach in coaches_rows:
                    ok = send_sms(
                        app.config['TWILIO_ACCOUNT_SID'],
                        app.config['TWILIO_AUTH_TOKEN'],
                        app.config['TWILIO_FROM_NUMBER'],
                        coach['mobile'],
                        msg
                    )
                    if not ok:
                        app.logger.warning(
                            '[cancel SMS] Failed to send cancellation SMS to coach=%s mobile=%s '
                            'session_id=%s date=%s',
                            coach['name'], coach['mobile'], session_id, roster_date
                        )
        except Exception as e:
            app.logger.error(
                '[cancel SMS] Unexpected error sending cancellation SMS: %s — '
                'session_id=%s date=%s',
                e, session_id, roster_date
            )

    db.close()
    return jsonify({'success': True})


@app.route('/roster/<int:term_id>/restore_date', methods=['POST'])
@login_required
def roster_restore_date(term_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorised'}), 403
    data = request.get_json()
    session_id = data.get('session_id')
    roster_date = data.get('date')
    db = get_db()
    result = db.execute(
        'DELETE FROM session_cancellations WHERE session_id = %s AND date = %s',
        (session_id, roster_date)
    )
    db.commit()

    # Only send SMS if a cancellation record actually existed (not a no-op restore)
    if result.rowcount > 0:
        try:
            from datetime import datetime as _dt
            sess_row = db.execute(
                'SELECT location, day_of_week, start_time FROM sessions WHERE id = %s',
                (session_id,)
            ).fetchone()
            coaches_rows = db.execute(
                '''SELECT c.name, c.mobile
                   FROM roster_entries re
                   JOIN coaches c ON c.id = re.coach_id
                   WHERE re.term_id = %s AND re.session_id = %s AND re.date = %s
                     AND c.mobile IS NOT NULL AND c.mobile <> \'\'
                ''',
                (term_id, session_id, roster_date)
            ).fetchall()

            if sess_row and coaches_rows:
                parsed_date = _dt.strptime(roster_date, '%Y-%m-%d')
                friendly_date = parsed_date.strftime('%A %-d %B')
                location = sess_row['location']
                start_time = sess_row['start_time']
                msg = f"Good news — your {location} session on {friendly_date} at {start_time} is back on."
                for coach in coaches_rows:
                    ok = send_sms(
                        app.config['TWILIO_ACCOUNT_SID'],
                        app.config['TWILIO_AUTH_TOKEN'],
                        app.config['TWILIO_FROM_NUMBER'],
                        coach['mobile'],
                        msg
                    )
                    if not ok:
                        app.logger.warning(
                            '[restore SMS] Failed to send restore SMS to coach=%s mobile=%s '
                            'session_id=%s date=%s',
                            coach['name'], coach['mobile'], session_id, roster_date
                        )
        except Exception as e:
            app.logger.error(
                '[restore SMS] Unexpected error sending restore SMS: %s — '
                'session_id=%s date=%s',
                e, session_id, roster_date
            )

    db.close()
    return jsonify({'success': True})


@app.route('/roster/<int:term_id>/unassign', methods=['POST'])
@login_required
def roster_unassign(term_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorised'}), 403

    data = request.get_json()
    session_id = data.get('session_id')
    coach_id = data.get('coach_id')
    roster_date = data.get('date')

    db = get_db()
    db.execute('''
        DELETE FROM roster_entries
        WHERE term_id = %s AND session_id = %s AND date = %s AND coach_id = %s
    ''', (term_id, session_id, roster_date, coach_id))
    db.commit()
    db.close()
    return jsonify({'success': True})


@app.route('/roster/<int:term_id>/generate', methods=['POST'])
@login_required
def roster_generate(term_id):
    if not current_user.is_admin:
        flash('Admin access required.', 'error')
        return redirect(url_for('roster_term', term_id=term_id))

    db = get_db()
    term = db.execute('SELECT * FROM terms WHERE id = %s', (term_id,)).fetchone()
    sessions = db.execute('SELECT * FROM sessions WHERE is_active = 1').fetchall()
    coaches = db.execute(
        'SELECT * FROM coaches WHERE is_active = 1 AND is_standby = 0'
    ).fetchall()

    # Get availability responses for this term
    availability = {}
    responded_ids = set()
    for c in coaches:
        resp = db.execute(
            'SELECT * FROM availability_responses WHERE coach_id = %s AND term_id = %s',
            (c['id'], term_id)
        ).fetchone()
        if resp:
            responded_ids.add(c['id'])
            availability[c['id']] = {
                'weekly': json.loads(resp['weekly_availability'] or '{}'),
                'unavailable_dates': json.loads(resp['unavailable_dates'] or '[]'),
            }

    # Clear existing entries for this term
    db.execute('DELETE FROM roster_entries WHERE term_id = %s', (term_id,))

    term_start = date.fromisoformat(term['start_date'])
    term_end = date.fromisoformat(term['end_date'])

    # Load session-specific date overrides
    override_rows = db.execute(
        'SELECT session_id, start_date, end_date FROM session_overrides WHERE term_id = %s', (term_id,)
    ).fetchall()
    session_end_overrides = {r['session_id']: date.fromisoformat(r['end_date']) for r in override_rows}
    session_start_overrides = {r['session_id']: date.fromisoformat(r['start_date']) for r in override_rows if r['start_date']}

    # Load cancellations
    cancel_rows_gen = db.execute('SELECT session_id, date FROM session_cancellations').fetchall()
    cancelled_gen = {(r['session_id'], r['date']) for r in cancel_rows_gen}

    # Track assignments per coach for load balancing
    coach_assignment_count = {c['id']: 0 for c in coaches}

    entries_to_insert = []
    understaffed_sessions = 0
    current_date = term_start

    while current_date <= term_end:
        day_name = current_date.strftime('%A')
        date_str = current_date.isoformat()
        day_sessions = [s for s in sessions if s['day_of_week'] == day_name
                        and current_date >= session_start_overrides.get(s['id'], term_start)
                        and current_date <= session_end_overrides.get(s['id'], term_end)
                        and (s['id'], date_str) not in cancelled_gen]

        for s in day_sessions:
            # Determine available coaches for this specific date
            available = []
            for c in coaches:
                avail = availability.get(c['id'], {})
                weekly = avail.get('weekly', {})
                unavailable_dates = avail.get('unavailable_dates', [])

                # Exclude if this specific date is marked unavailable
                if date_str in unavailable_dates:
                    continue
                # Check weekly time preference
                if weekly:
                    time_pref = weekly.get(day_name, 'all')
                    # Handle old boolean format
                    if time_pref is False:
                        continue
                    elif time_pref == 'unavailable':
                        continue
                    elif time_pref in ('am', 'pm'):
                        session_hour = int(s['start_time'].split(':')[0])
                        if time_pref == 'am' and session_hour >= 12:
                            continue
                        if time_pref == 'pm' and session_hour < 12:
                            continue
                available.append(c)

            # Prefer Level 2+ for school program sessions
            is_school = s['location'] in ('Peninsula Grammar', 'Toorak College')
            if is_school:
                preferred = [c for c in available if c['level'] in ('Level 2', 'Level 3')]
                others = [c for c in available if c not in preferred]
                ordered = (sorted(preferred, key=lambda c: coach_assignment_count[c['id']]) +
                           sorted(others,    key=lambda c: coach_assignment_count[c['id']]))
            else:
                ordered = sorted(available, key=lambda c: coach_assignment_count[c['id']])

            assigned = 0
            for c in ordered:
                if assigned >= s['max_coaches']:
                    break
                entries_to_insert.append((term_id, s['id'], date_str, c['id']))
                coach_assignment_count[c['id']] += 1
                assigned += 1

            if assigned < s['min_coaches']:
                understaffed_sessions += 1

        current_date += timedelta(days=1)

    for entry in entries_to_insert:
        try:
            db.execute(
                'INSERT INTO roster_entries (term_id, session_id, date, coach_id) VALUES (%s, %s, %s, %s) ON CONFLICT (term_id, session_id, date, coach_id) DO NOTHING',
                entry
            )
        except Exception:
            pass

    db.commit()
    db.close()

    responded = len(responded_ids)
    total_coaches = len(coaches)
    msg = (f'Roster generated for {term["name"]} — '
           f'{len(entries_to_insert)} assignments across {total_coaches} coaches '
           f'({responded} had submitted availability).')
    if understaffed_sessions:
        msg += f' ⚠ {understaffed_sessions} session(s) are still understaffed — check availability responses.'
    flash(msg, 'success' if not understaffed_sessions else 'warning')
    return redirect(url_for('roster_term', term_id=term_id))


@app.route('/roster/<int:term_id>/clear', methods=['POST'])
@login_required
def roster_clear(term_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorised'}), 403
    db = get_db()
    db.execute('DELETE FROM roster_entries WHERE term_id = %s', (term_id,))
    db.commit()
    db.close()
    flash('Roster cleared.', 'success')
    return redirect(url_for('roster_term', term_id=term_id))


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------

@app.route('/availability')
@login_required
def availability():
    if not current_user.is_admin:
        flash('Admin access required.', 'error')
        return redirect(url_for('dashboard'))

    db = get_db()
    terms = db.execute('SELECT * FROM terms ORDER BY start_date').fetchall()
    coaches = db.execute(
        'SELECT * FROM coaches WHERE is_active = 1 AND is_standby = 0 ORDER BY name'
    ).fetchall()

    # Get responses per term
    responses = {}
    for t in terms:
        term_responses = {}
        for c in coaches:
            resp = db.execute(
                'SELECT * FROM availability_responses WHERE coach_id = %s AND term_id = %s',
                (c['id'], t['id'])
            ).fetchone()
            term_responses[c['id']] = dict(resp) if resp else None
        responses[t['id']] = term_responses

    # Try to load Google Sheets availability as reference
    sheet_data = []
    try:
        sheet_data = get_sheet_availability(app.config['GOOGLE_CREDENTIALS_JSON'],
                                            app.config['GOOGLE_SHEET_ID'])
    except Exception:
        pass

    db.close()
    return render_template('availability.html',
                           terms=terms,
                           coaches=coaches,
                           responses=responses,
                           sheet_data=sheet_data)


@app.route('/availability/send-requests', methods=['POST'])
@login_required
def send_availability_requests():
    if not current_user.is_admin:
        flash('Admin access required.', 'error')
        return redirect(url_for('availability'))

    term_id = request.form.get('term_id', type=int)
    coach_ids = request.form.getlist('coach_ids')
    db = get_db()
    term = db.execute('SELECT * FROM terms WHERE id = %s', (term_id,)).fetchone()
    if coach_ids:
        coaches = db.execute(
            f'SELECT * FROM coaches WHERE id IN ({",".join("%s" * len(coach_ids))}) AND mobile IS NOT NULL',
            coach_ids
        ).fetchall()
    else:
        coaches = db.execute(
            'SELECT * FROM coaches WHERE is_active = 1 AND is_standby = 0 AND mobile IS NOT NULL'
        ).fetchall()

    sent = 0
    for coach in coaches:
        token = secrets.token_urlsafe(24)
        expires = datetime.utcnow() + timedelta(days=14)
        db.execute('''
            INSERT INTO availability_tokens (coach_id, term_id, token, expires_at)
            VALUES (%s, %s, %s, %s)
        ''', (coach['id'], term_id, token, expires.strftime('%Y-%m-%dT%H:%M:%S')))

        form_url = f"{app.config['APP_URL']}/availability/{token}"
        message = (
            f"Hi {coach['name'].split()[0]}, Power2ADAPT {term['name']} is coming up! "
            f"Please fill in your availability here: {form_url} "
            f"Takes 2 mins. Thanks, Alistair"
        )
        result = send_sms(
            app.config['TWILIO_ACCOUNT_SID'],
            app.config['TWILIO_AUTH_TOKEN'],
            app.config['TWILIO_FROM_NUMBER'],
            coach['mobile'],
            message
        )
        db.execute('''
            INSERT INTO sms_log (coach_id, mobile, message, type, status)
            VALUES (%s, %s, %s, %s, %s)
        ''', (coach['id'], coach['mobile'], message, 'availability_request',
              'sent' if result else 'failed'))
        if result:
            sent += 1

    db.commit()
    db.close()
    flash(f'Availability requests sent to {sent} coaches for {term["name"]}.', 'success')
    return redirect(url_for('availability'))


@app.route('/availability/<token>')
def availability_form(token):
    db = get_db()
    tok = db.execute('''
        SELECT at.*, c.name as coach_name, t.name as term_name,
               t.start_date, t.end_date, t.id as term_id
        FROM availability_tokens at
        JOIN coaches c ON at.coach_id = c.id
        JOIN terms t ON at.term_id = t.id
        WHERE at.token = %s
    ''', (token,)).fetchone()

    if not tok:
        db.close()
        return render_template('availability_form.html', error='Invalid link.')

    if tok['expires_at']:
        try:
            exp = tok['expires_at'] if isinstance(tok['expires_at'], datetime) else datetime.fromisoformat(str(tok['expires_at']).split('+')[0].split('Z')[0])
            if datetime.utcnow() > exp:
                db.close()
                return render_template('availability_form.html', error='This link has expired. Please contact Alistair for a new one.')
        except Exception:
            pass

    if tok['used']:
        # Load existing response to show it
        existing = db.execute(
            'SELECT * FROM availability_responses WHERE coach_id = %s AND term_id = %s',
            (tok['coach_id'], tok['term_id'])
        ).fetchone()
        db.close()
        return render_template('availability_form.html',
                               tok=tok,
                               already_submitted=True,
                               existing=existing)

    # Generate term dates grouped by week
    sessions = db.execute(
        'SELECT DISTINCT day_of_week FROM sessions WHERE is_active = 1'
    ).fetchall()
    session_days = {s['day_of_week'] for s in sessions}

    term_start = date.fromisoformat(tok['start_date'])
    term_end = date.fromisoformat(tok['end_date'])

    term_dates = []
    current = term_start
    while current <= term_end:
        if current.strftime('%A') in session_days:
            term_dates.append(current)
        current += timedelta(days=1)

    expires_display = None
    if tok['expires_at']:
        try:
            exp_utc = tok['expires_at'] if isinstance(tok['expires_at'], datetime) else datetime.fromisoformat(str(tok['expires_at']).split('+')[0].split('Z')[0])
            exp_aest = exp_utc + timedelta(hours=11)
            expires_display = exp_aest.strftime('%-d %B %Y')
        except Exception:
            pass

    db.close()
    return render_template('availability_form.html',
                           tok=tok,
                           token=token,
                           term_dates=term_dates,
                           days_of_week=['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'],
                           expires_display=expires_display)


@app.route('/availability/<token>/submit', methods=['POST'])
def availability_submit(token):
    db = get_db()
    tok = db.execute(
        'SELECT * FROM availability_tokens WHERE token = %s', (token,)
    ).fetchone()

    if not tok or tok['used']:
        db.close()
        flash('This link has already been used or is invalid.', 'error')
        return redirect(url_for('availability_form', token=token))

    weekly = {}
    for day in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']:
        weekly[day] = request.form.get(f'weekly_{day}', 'all')

    unavailable_dates = request.form.getlist('unavailable_dates')
    notes = request.form.get('notes', '')

    db.execute('''
        INSERT INTO availability_responses
        (coach_id, term_id, weekly_availability, unavailable_dates, notes, submitted_at)
        VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (coach_id, term_id) DO UPDATE SET
            weekly_availability = EXCLUDED.weekly_availability,
            unavailable_dates = EXCLUDED.unavailable_dates,
            notes = EXCLUDED.notes,
            submitted_at = CURRENT_TIMESTAMP
    ''', (tok['coach_id'], tok['term_id'],
          json.dumps(weekly), json.dumps(unavailable_dates), notes))

    db.execute('UPDATE availability_tokens SET used = 1 WHERE token = %s', (token,))
    db.commit()
    db.close()

    return render_template('availability_form.html', submitted=True, token=token)


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

@app.route('/fixtures')
@login_required
def fixtures():
    db = get_db()
    rows = db.execute('''
        SELECT f.*, STRING_AGG(c.name, ', ') as coach_names
        FROM fixtures f
        LEFT JOIN fixture_coaches fc ON f.id = fc.fixture_id
        LEFT JOIN coaches c ON fc.coach_id = c.id
        GROUP BY f.id
        ORDER BY f.date ASC
    ''').fetchall()
    all_coaches = db.execute('SELECT * FROM coaches WHERE is_active = 1 ORDER BY name').fetchall()
    assigned = db.execute('SELECT fixture_id, coach_id FROM fixture_coaches').fetchall()
    db.close()
    assigned_map = {}
    for a in assigned:
        assigned_map.setdefault(a['fixture_id'], set()).add(a['coach_id'])

    coach_name_map = {c['id']: c['name'] for c in all_coaches}
    co_coaches_map = {}
    for a in assigned:
        if a['coach_id'] != current_user.id:
            fid = a['fixture_id']
            name = coach_name_map.get(a['coach_id'], '')
            first_name = name.split()[0] if name else ''
            if first_name:
                co_coaches_map.setdefault(fid, []).append(first_name)

    today = date.today().isoformat()
    return render_template('fixtures.html', fixtures=rows, all_coaches=all_coaches,
                           assigned_map=assigned_map, co_coaches_map=co_coaches_map,
                           today=today, is_admin=current_user.is_admin,
                           current_user_id=current_user.id)


@app.route('/fixtures/add', methods=['POST'])
@login_required
def fixtures_add():
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorised'}), 403
    data = request.form
    db = get_db()
    row = db.execute(
        'INSERT INTO fixtures (title, date, location, school, notes) VALUES (%s,%s,%s,%s,%s) RETURNING id',
        (data['title'], data['date'], data.get('location',''), data.get('school',''), data.get('notes',''))
    ).fetchone()
    fid = row['id']
    for cid in request.form.getlist('coach_ids'):
        db.execute('INSERT INTO fixture_coaches (fixture_id, coach_id) VALUES (%s,%s) ON CONFLICT DO NOTHING', (fid, cid))
    db.commit()
    db.close()
    flash('Fixture added.', 'success')
    return redirect(url_for('fixtures'))


@app.route('/fixtures/<int:fixture_id>/coaches', methods=['POST'])
@login_required
def fixtures_update_coaches(fixture_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorised'}), 403
    db = get_db()
    db.execute('DELETE FROM fixture_coaches WHERE fixture_id = %s', (fixture_id,))
    for cid in request.form.getlist('coach_ids'):
        db.execute('INSERT INTO fixture_coaches (fixture_id, coach_id) VALUES (%s,%s) ON CONFLICT DO NOTHING', (fixture_id, cid))
    db.commit()
    db.close()
    flash('Coaches updated.', 'success')
    return redirect(url_for('fixtures'))


@app.route('/fixtures/<int:fixture_id>/edit', methods=['POST'])
@login_required
def fixtures_edit(fixture_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorised'}), 403
    data = request.form
    db = get_db()
    db.execute(
        'UPDATE fixtures SET title=%s, date=%s, location=%s, school=%s, notes=%s WHERE id=%s',
        (data['title'], data['date'], data.get('location', ''), data.get('school', ''), data.get('notes', ''), fixture_id)
    )
    db.commit()
    db.close()
    flash('Fixture updated.', 'success')
    return redirect(url_for('fixtures'))


@app.route('/fixtures/<int:fixture_id>/add_coach', methods=['POST'])
@login_required
def fixtures_add_coach(fixture_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorised'}), 403
    coach_id = request.json.get('coach_id')
    if not coach_id:
        return jsonify({'error': 'No coach_id'}), 400
    db = get_db()
    db.execute('INSERT INTO fixture_coaches (fixture_id, coach_id) VALUES (%s,%s) ON CONFLICT DO NOTHING',
               (fixture_id, coach_id))
    coach = db.execute('SELECT name FROM coaches WHERE id=%s', (coach_id,)).fetchone()
    db.commit()
    db.close()
    return jsonify({'success': True, 'coach_name': coach['name']})


@app.route('/fixtures/<int:fixture_id>/remove_coach', methods=['POST'])
@login_required
def fixtures_remove_coach(fixture_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorised'}), 403
    coach_id = request.json.get('coach_id')
    db = get_db()
    db.execute('DELETE FROM fixture_coaches WHERE fixture_id=%s AND coach_id=%s', (fixture_id, coach_id))
    db.commit()
    db.close()
    return jsonify({'success': True})


@app.route('/fixtures/<int:fixture_id>/delete', methods=['POST'])
@login_required
def fixtures_delete(fixture_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorised'}), 403
    db = get_db()
    db.execute('DELETE FROM fixture_coaches WHERE fixture_id = %s', (fixture_id,))
    db.execute('DELETE FROM fixtures WHERE id = %s', (fixture_id,))
    db.commit()
    db.close()
    flash('Fixture deleted.', 'success')
    return redirect(url_for('fixtures'))


@app.route('/alerts')
@login_required
def alerts():
    if not current_user.is_admin:
        flash('Admin access required.', 'error')
        return redirect(url_for('dashboard'))

    db = get_db()
    coaches = db.execute(
        'SELECT * FROM coaches WHERE is_active = 1 ORDER BY name'
    ).fetchall()
    terms = db.execute('SELECT * FROM terms ORDER BY start_date').fetchall()
    log = db.execute(
        'SELECT sl.*, c.name as coach_name FROM sms_log sl '
        'LEFT JOIN coaches c ON sl.coach_id = c.id '
        'ORDER BY sl.sent_at DESC LIMIT 50'
    ).fetchall()
    db.close()
    return render_template(
        'alerts.html', coaches=coaches, terms=terms, log=log,
        sms_templates=SMS_TEMPLATES,
    )


@app.route('/alerts/send-timesheet', methods=['POST'])
@login_required
def send_timesheet_reminder():
    if not current_user.is_admin:
        flash('Admin access required.', 'error')
        return redirect(url_for('alerts'))

    coach_ids = request.form.getlist('coach_ids')
    db = get_db()

    if coach_ids:
        coaches = db.execute(
            f'SELECT * FROM coaches WHERE id IN ({",".join("%s" * len(coach_ids))}) AND mobile IS NOT NULL',
            coach_ids
        ).fetchall()
    else:
        coaches = db.execute(
            'SELECT * FROM coaches WHERE is_active = 1 AND mobile IS NOT NULL'
        ).fetchall()

    sent = 0
    for coach in coaches:
        message = (
            f"Hi {coach['name'].split()[0]}, friendly reminder to submit your timesheet "
            f"via Xero Me tonight. Thanks, Alistair"
        )
        result = send_sms(
            app.config['TWILIO_ACCOUNT_SID'],
            app.config['TWILIO_AUTH_TOKEN'],
            app.config['TWILIO_FROM_NUMBER'],
            coach['mobile'],
            message
        )
        db.execute('''
            INSERT INTO sms_log (coach_id, mobile, message, type, status)
            VALUES (%s, %s, %s, %s, %s)
        ''', (coach['id'], coach['mobile'], message, 'timesheet_reminder',
              'sent' if result else 'failed'))
        if result:
            sent += 1

    db.commit()
    db.close()
    flash(f'Timesheet reminder sent to {sent} coaches.', 'success')
    return redirect(url_for('alerts'))


@app.route('/alerts/send-custom', methods=['POST'])
@login_required
def send_custom_sms():
    if not current_user.is_admin:
        flash('Admin access required.', 'error')
        return redirect(url_for('alerts'))

    coach_ids = request.form.getlist('coach_ids')
    message_text = request.form.get('message', '').strip()

    if not message_text:
        flash('Message cannot be empty.', 'error')
        return redirect(url_for('alerts'))

    db = get_db()
    if coach_ids:
        coaches = db.execute(
            f'SELECT * FROM coaches WHERE id IN ({",".join("%s" * len(coach_ids))}) AND mobile IS NOT NULL',
            coach_ids
        ).fetchall()
    else:
        coaches = db.execute(
            'SELECT * FROM coaches WHERE is_active = 1 AND mobile IS NOT NULL'
        ).fetchall()

    sent = 0
    for coach in coaches:
        message = personalize_sms(message_text, coach['name'])
        result = send_sms(
            app.config['TWILIO_ACCOUNT_SID'],
            app.config['TWILIO_AUTH_TOKEN'],
            app.config['TWILIO_FROM_NUMBER'],
            coach['mobile'],
            message
        )
        db.execute('''
            INSERT INTO sms_log (coach_id, mobile, message, type, status)
            VALUES (%s, %s, %s, %s, %s)
        ''', (coach['id'], coach['mobile'], message, 'custom',
              'sent' if result else 'failed'))
        if result:
            sent += 1

    db.commit()
    db.close()
    flash(f'Message sent to {sent} coaches.', 'success')
    return redirect(url_for('alerts'))


# ---------------------------------------------------------------------------
# Admin -- Coaches
# ---------------------------------------------------------------------------

@app.route('/admin/coaches')
@login_required
def admin_coaches():
    if not current_user.is_admin:
        flash('Admin access required.', 'error')
        return redirect(url_for('dashboard'))
    db = get_db()
    coaches = [dict(c) for c in db.execute('''
        SELECT id, name, username, email, mobile, role, level, is_admin,
               is_standby, is_active
        FROM coaches ORDER BY is_active DESC, name
    ''').fetchall()]
    statuses = setup_statuses(db)
    for coach in coaches:
        coach.update(statuses.get(coach['id'], {
            'setup_status': 'Not sent', 'setup_sent_label': '',
            'setup_completed_label': '', 'setup_expires_label': '',
        }))
    db.close()
    session.setdefault('coach_admin_csrf', secrets.token_urlsafe(32))
    return render_template(
        'coaches.html', coaches=coaches,
        setup_send_enabled=bool(app.config['COACH_AUTH_BASE_URL']) and app.config['COACH_AUTH_SMS_ENABLED'],
        setup_send_note='Check the SMS connection before sending a setup link. The connection check does not send a text.',
    )


@app.route('/admin/coaches/add', methods=['POST'])
@login_required
def admin_coaches_add():
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorised'}), 403
    if not _valid_form_token('coach_admin_csrf'):
        return 'Invalid form token', 403

    name = request.form.get('name', '').strip()
    username = request.form.get('username', '').strip().lower()
    email = request.form.get('email', '').strip() or None
    mobile = request.form.get('mobile', '').strip() or None
    role = request.form.get('role', '').strip()
    level = request.form.get('level', '').strip()
    is_standby = 1 if request.form.get('is_standby') else 0
    password = request.form.get('password', '')
    if len(password) < 12:
        flash('Set a password of at least 12 characters for the new coach.', 'error')
        return redirect(url_for('admin_coaches'))

    db = get_db()
    try:
        db.execute('''
            INSERT INTO coaches (name, username, email, mobile, role, level, is_standby, password_hash)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ''', (name, username, email, mobile, role, level, is_standby,
              generate_password_hash(password)))
        db.commit()
        flash(f'{name} added successfully.', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'error')
    db.close()
    return redirect(url_for('admin_coaches'))


@app.route('/admin/coaches/<int:coach_id>/edit', methods=['POST'])
@login_required
def admin_coaches_edit(coach_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorised'}), 403
    if not _valid_form_token('coach_admin_csrf'):
        return 'Invalid form token', 403

    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip() or None
    mobile = request.form.get('mobile', '').strip() or None
    role = request.form.get('role', '').strip()
    level = request.form.get('level', '').strip()
    is_standby = 1 if request.form.get('is_standby') else 0
    new_password = request.form.get('new_password', '').strip()
    if new_password and len(new_password) < 12:
        flash('New password must be at least 12 characters.', 'error')
        return redirect(url_for('admin_coaches'))

    db = get_db()
    existing = db.execute('SELECT * FROM coaches WHERE id = %s FOR UPDATE', (coach_id,)).fetchone()
    if not existing:
        db.close()
        return 'Coach not found', 404
    if new_password:
        db.execute('''
            UPDATE coaches SET name=%s, email=%s, mobile=%s, role=%s, level=%s,
            is_standby=%s, password_hash=%s WHERE id=%s
        ''', (name, email, mobile, role, level, is_standby,
              generate_password_hash(new_password), coach_id))
        bump_auth_version(db, coach_id)
        revoke_setup_links(db, coach_id)
    else:
        db.execute('''
            UPDATE coaches SET name=%s, email=%s, mobile=%s, role=%s, level=%s,
            is_standby=%s WHERE id=%s
        ''', (name, email, mobile, role, level, is_standby, coach_id))
        if mobile != existing['mobile']:
            revoke_setup_links(db, coach_id)
    db.commit()
    db.close()
    flash('Coach updated.', 'success')
    return redirect(url_for('admin_coaches'))


@app.route('/admin/coaches/<int:coach_id>/toggle', methods=['POST'])
@login_required
def admin_coaches_toggle(coach_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorised'}), 403
    if not _valid_form_token('coach_admin_csrf'):
        return 'Invalid form token', 403
    db = get_db()
    db.execute('UPDATE coaches SET is_active = 1 - is_active WHERE id = %s', (coach_id,))
    db.commit()
    db.close()
    return redirect(url_for('admin_coaches'))


# ---------------------------------------------------------------------------
# Admin -- Sessions
# ---------------------------------------------------------------------------

@app.route('/admin/sessions')
@login_required
def admin_sessions():
    if not current_user.is_admin:
        flash('Admin access required.', 'error')
        return redirect(url_for('dashboard'))
    db = get_db()
    sessions = [dict(s) for s in db.execute(
        'SELECT * FROM sessions ORDER BY '
        "CASE day_of_week WHEN 'Monday' THEN 1 WHEN 'Tuesday' THEN 2 WHEN 'Wednesday' THEN 3 "
        "WHEN 'Thursday' THEN 4 WHEN 'Friday' THEN 5 ELSE 6 END, start_time"
    ).fetchall()]
    db.close()
    return render_template('sessions.html', sessions=sessions, days=DAY_ORDER[:5])


@app.route('/admin/sessions/add', methods=['POST'])
@login_required
def admin_sessions_add():
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorised'}), 403

    db = get_db()
    db.execute('''
        INSERT INTO sessions (day_of_week, start_time, end_time, location, programs,
        min_coaches, max_coaches, notes)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ''', (
        request.form.get('day_of_week'),
        request.form.get('start_time'),
        request.form.get('end_time'),
        request.form.get('location'),
        request.form.get('programs'),
        request.form.get('min_coaches', 1, type=int),
        request.form.get('max_coaches', 4, type=int),
        request.form.get('notes', ''),
    ))
    db.commit()
    db.close()
    flash('Session added.', 'success')
    return redirect(url_for('admin_sessions'))


@app.route('/admin/sessions/<int:session_id>/edit', methods=['POST'])
@login_required
def admin_sessions_edit(session_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorised'}), 403

    db = get_db()
    db.execute('''
        UPDATE sessions SET day_of_week=%s, start_time=%s, end_time=%s, location=%s,
        programs=%s, min_coaches=%s, max_coaches=%s, notes=%s WHERE id=%s
    ''', (
        request.form.get('day_of_week'),
        request.form.get('start_time'),
        request.form.get('end_time'),
        request.form.get('location'),
        request.form.get('programs'),
        request.form.get('min_coaches', 1, type=int),
        request.form.get('max_coaches', 4, type=int),
        request.form.get('notes', ''),
        session_id,
    ))
    db.commit()
    db.close()
    flash('Session updated.', 'success')
    return redirect(url_for('admin_sessions'))


@app.route('/admin/sessions/<int:session_id>/toggle', methods=['POST'])
@login_required
def admin_sessions_toggle(session_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorised'}), 403
    db = get_db()
    db.execute('UPDATE sessions SET is_active = 1 - is_active WHERE id = %s', (session_id,))
    db.commit()
    db.close()
    return redirect(url_for('admin_sessions'))


# ---------------------------------------------------------------------------
# Admin diagnostics
# ---------------------------------------------------------------------------

@app.route('/admin/db-info')
@login_required
def admin_db_info():
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorised'}), 403
    import os
    db = get_db()
    coaches = db.execute('SELECT COUNT(*) AS cnt FROM coaches').fetchone()['cnt']
    tokens  = db.execute('SELECT COUNT(*) AS cnt FROM availability_tokens').fetchone()['cnt']
    alistair = db.execute("SELECT id, name, mobile FROM coaches WHERE username='alistair'").fetchone()
    db.close()
    host = os.environ.get('PGHOST', 'unknown')
    dbname = os.environ.get('PGDATABASE', 'unknown')
    return jsonify({
        'db_host': host,
        'db_name': dbname,
        'coaches_count': coaches,
        'tokens_count': tokens,
        'alistair': dict(alistair) if alistair else None
    })


# ---------------------------------------------------------------------------
# Performance — Session Library
# ---------------------------------------------------------------------------

@app.route('/performance/sessions')
@login_required
@admin_required
def session_library():
    import re as _re
    db = get_db()
    sessions = db.execute('''
        SELECT id, name, description, session_type, event_group,
               training_phase, intensity_level, tags, source_year, coach_notes,
               target_sets, target_reps, target_recovery_secs,
               target_intensity_pct, target_notes
        FROM public.training_sessions
        WHERE NOT is_archived
        ORDER BY id
    ''').fetchall()
    db.close()
    sessions_data = []
    for s in sessions:
        d = dict(s)
        tags = d.get('tags')
        if tags is None:
            d['tags'] = []
        elif isinstance(tags, str):
            d['tags'] = [t.strip() for t in _re.sub(r'[{}]', '', tags).split(',') if t.strip()]
        sessions_data.append(d)
    return render_template('session_library.html',
                           sessions_json=json.dumps(sessions_data, default=str),
                           total=len(sessions_data))


@app.route('/performance/sessions/<int:session_id>/note', methods=['POST'])
@login_required
@admin_required
def save_session_note(session_id):
    note = request.form.get('note', '').strip()
    db = get_db()
    db.execute('UPDATE public.training_sessions SET coach_notes = ? WHERE id = ?', (note or None, session_id))
    db.commit()
    db.close()
    return ('', 204)


@app.route('/performance/sessions/<int:session_id>/update', methods=['POST'])
@login_required
@admin_required
def update_session(session_id):
    f = request.form
    name = f.get('name', '').strip()
    if not name:
        return json.dumps({'error': 'Name required'}), 400, {'Content-Type': 'application/json'}
    tags_raw = f.get('tags', '').strip()
    tags_list = [t.strip() for t in tags_raw.split(',') if t.strip()]
    tags_pg = '{' + ','.join(f'"{t}"' for t in tags_list) + '}'

    def _int(key):
        v = f.get(key, '').strip()
        return int(v) if v.isdigit() else None

    db = get_db()
    db.execute('''
        UPDATE public.training_sessions SET
            name = ?, description = ?, session_type = ?, event_group = ?,
            training_phase = ?, intensity_level = ?, tags = ?,
            target_sets = ?, target_reps = ?, target_recovery_secs = ?,
            target_intensity_pct = ?, target_notes = ?, coach_notes = ?
        WHERE id = ?
    ''', (
        name,
        f.get('description', '').strip() or None,
        f.get('session_type', '').strip(),
        f.get('event_group', '').strip() or None,
        f.get('training_phase', '').strip() or None,
        f.get('intensity_level', '').strip() or None,
        tags_pg,
        _int('target_sets'), _int('target_reps'),
        _int('target_recovery_secs'), _int('target_intensity_pct'),
        f.get('target_notes', '').strip() or None,
        f.get('coach_notes', '').strip() or None,
        session_id
    ))
    db.commit()
    # Return updated record
    row = db.execute('''
        SELECT id, name, description, session_type, event_group,
               training_phase, intensity_level, tags, source_year, coach_notes,
               target_sets, target_reps, target_recovery_secs,
               target_intensity_pct, target_notes
        FROM public.training_sessions WHERE id = ?
    ''', (session_id,)).fetchone()
    db.close()
    import re as _re
    d = dict(row)
    raw = d.get('tags')
    if raw is None:
        d['tags'] = []
    elif isinstance(raw, list):
        pass
    else:
        d['tags'] = [t.strip() for t in _re.sub(r'[{}"]', '', raw).split(',') if t.strip()]
    return json.dumps(d, default=str), 200, {'Content-Type': 'application/json'}


@app.route('/performance/sessions/<int:session_id>/duplicate', methods=['POST'])
@login_required
@admin_required
def duplicate_session(session_id):
    import re as _re
    db = get_db()
    orig = db.execute('''
        SELECT name, description, session_type, event_group, training_phase,
               intensity_level, tags, coach_notes, target_sets, target_reps,
               target_recovery_secs, target_intensity_pct, target_notes
        FROM public.training_sessions WHERE id = ?
    ''', (session_id,)).fetchone()
    if not orig:
        db.close()
        return json.dumps({'error': 'Not found'}), 404, {'Content-Type': 'application/json'}
    new_row = db.execute('''
        INSERT INTO public.training_sessions
            (name, description, session_type, event_group, training_phase,
             intensity_level, tags, coach_notes, target_sets, target_reps,
             target_recovery_secs, target_intensity_pct, target_notes)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        RETURNING id, name, description, session_type, event_group, training_phase,
                  intensity_level, tags, source_year, coach_notes,
                  target_sets, target_reps, target_recovery_secs,
                  target_intensity_pct, target_notes
    ''', (
        'Copy of ' + orig['name'],
        orig['description'], orig['session_type'], orig['event_group'],
        orig['training_phase'], orig['intensity_level'], orig['tags'],
        orig['coach_notes'], orig['target_sets'], orig['target_reps'],
        orig['target_recovery_secs'], orig['target_intensity_pct'], orig['target_notes']
    )).fetchone()
    db.commit()
    db.close()
    d = dict(new_row)
    raw = d.get('tags')
    if raw is None:
        d['tags'] = []
    elif isinstance(raw, list):
        pass
    else:
        d['tags'] = [t.strip() for t in _re.sub(r'[{}"]', '', raw).split(',') if t.strip()]
    return json.dumps(d, default=str), 200, {'Content-Type': 'application/json'}


# ---------------------------------------------------------------------------
# Performance — Athlete Dashboard
# ---------------------------------------------------------------------------

@app.route('/athletes/<int:athlete_id>/performance')
@login_required
@admin_required
def athlete_performance(athlete_id):
    db = get_db()
    all_athletes = db.execute('''
        SELECT id, name, initials, event_group
        FROM public.athletes
        WHERE is_active = true
        ORDER BY name
    ''').fetchall()
    athlete = db.execute('SELECT * FROM public.athletes WHERE id = ?', (athlete_id,)).fetchone()
    if not athlete:
        db.close()
        flash('Athlete not found.', 'error')
        return redirect(url_for('athletes'))
    test_data = db.execute('''
        SELECT pt.test_date, tr.metric, tr.value, tr.unit, tr.is_pb
        FROM public.performance_tests pt
        JOIN public.test_results tr ON tr.test_id = pt.id
        WHERE pt.athlete_id = ?
        ORDER BY pt.test_date ASC
    ''', (athlete_id,)).fetchall()
    benchmarks = db.execute('''
        SELECT metric, level, value, unit
        FROM public.performance_benchmarks
        WHERE age_group = 'U20' AND gender = 'M'
        ORDER BY metric, level
    ''').fetchall()
    db.close()
    metrics_data = {}
    for row in test_data:
        m = row['metric']
        if m not in metrics_data:
            metrics_data[m] = []
        metrics_data[m].append({
            'date': str(row['test_date']),
            'value': float(row['value']),
            'is_pb': bool(row['is_pb'])
        })
    bm_data = {}
    for bm in benchmarks:
        m = bm['metric']
        if m not in bm_data:
            bm_data[m] = {}
        bm_data[m][bm['level'].lower()] = float(bm['value'])
    return render_template('athlete_performance.html',
                           athlete=dict(athlete),
                           all_athletes=[dict(a) for a in all_athletes],
                           metrics_data_json=json.dumps(metrics_data),
                           benchmarks_json=json.dumps(bm_data),
                           athlete_id=athlete_id)


# ---------------------------------------------------------------------------
# Athlete Board
# ---------------------------------------------------------------------------

@app.route('/athlete-board')
@login_required
def athlete_board():
    if not current_user.is_admin:
        return render_template('access_denied.html',
            title='Athlete Board',
            message='Head Coach or Admin login required to access the Athlete Board.'
        ), 403
    db = get_db()
    athletes_raw = db.execute('''
        SELECT id, name, initials, event_group, squad
        FROM public.athletes
        WHERE is_active = true
        ORDER BY name
    ''').fetchall()

    plans = db.execute('''
        SELECT atp.athlete_id, ts.name AS session_name, ts.session_type,
               ts.intensity_level, atp.day_of_week
        FROM public.athlete_training_plans atp
        JOIN public.training_sessions ts ON ts.id = atp.training_session_id
        ORDER BY atp.day_of_week NULLS LAST, ts.session_type, ts.name
    ''').fetchall()

    latest_results = db.execute('''
        SELECT DISTINCT ON (pt.athlete_id, tr.metric)
               pt.athlete_id, tr.metric, tr.value, tr.unit, tr.is_pb, pt.test_date
        FROM public.performance_tests pt
        JOIN public.test_results tr ON tr.test_id = pt.id
        ORDER BY pt.athlete_id, tr.metric, pt.test_date DESC
    ''').fetchall()
    db.close()

    plan_map = {}
    for p in plans:
        plan_map.setdefault(p['athlete_id'], []).append(dict(p))

    results_map = {}
    for r in latest_results:
        results_map.setdefault(r['athlete_id'], []).append(dict(r))

    athletes_data = []
    for a in athletes_raw:
        d = dict(a)
        d['sessions'] = plan_map.get(a['id'], [])
        d['results'] = results_map.get(a['id'], [])
        athletes_data.append(d)

    today_dow = date.today().weekday()  # 0=Mon, 6=Sun
    return render_template('athlete_board.html', athletes=athletes_data, today_dow=today_dow)


# ---------------------------------------------------------------------------
# Athletes
# ---------------------------------------------------------------------------

@app.route('/athletes')
@login_required
@admin_required
def athletes():
    db = get_db()
    athlete_list = db.execute('''
        SELECT a.id, a.name, a.initials, a.event_group, a.squad,
               a.assessment_code, a.is_active,
               c.first_name AS client_first, c.last_name AS client_last
        FROM public.athletes a
        LEFT JOIN public.clients c ON a.assessment_code = c.setmore_customer_id
        ORDER BY a.name
    ''').fetchall()
    db.close()
    return render_template('athletes.html', athletes=athlete_list)


@app.route('/athletes/<int:athlete_id>')
@login_required
@admin_required
def athlete_view(athlete_id):
    db = get_db()

    athlete = db.execute('''
        SELECT a.*, c.first_name AS client_first, c.last_name AS client_last,
               c.email, c.phone, c.date_of_birth, c.age_group,
               c.primary_sport, c.focus_events
        FROM public.athletes a
        LEFT JOIN public.clients c ON a.assessment_code = c.setmore_customer_id
        WHERE a.id = ?
    ''', (athlete_id,)).fetchone()

    if not athlete:
        db.close()
        flash('Athlete not found.', 'error')
        return redirect(url_for('athletes'))

    today = date.today().isoformat()
    current_block = db.execute('''
        SELECT * FROM public.macrocycle_blocks
        WHERE start_date <= ? AND end_date >= ?
        ORDER BY start_date DESC LIMIT 1
    ''', (today, today)).fetchone()

    if not current_block:
        current_block = db.execute('''
            SELECT * FROM public.macrocycle_blocks
            WHERE start_date > ?
            ORDER BY start_date ASC LIMIT 1
        ''', (today,)).fetchone()

    tests = db.execute('''
        SELECT pt.*, array_agg(tr.metric || ': ' || tr.value || ' ' || tr.unit
               ORDER BY tr.metric) AS results_summary
        FROM public.performance_tests pt
        LEFT JOIN public.test_results tr ON tr.test_id = pt.id
        WHERE pt.athlete_id = ?
        GROUP BY pt.id
        ORDER BY pt.test_date DESC
        LIMIT 10
    ''', (athlete_id,)).fetchall()

    sc_logs = db.execute('''
        SELECT wl.*, t.name AS template_name, p.name AS phase_name
        FROM public.sc_workout_logs wl
        LEFT JOIN public.sc_workout_templates t ON t.id = wl.template_id
        LEFT JOIN public.sc_phases p ON p.id = wl.sc_phase_id
        WHERE wl.athlete_id = ?
        ORDER BY wl.workout_date DESC
        LIMIT 5
    ''', (athlete_id,)).fetchall()

    training_plan = db.execute('''
        SELECT atp.id, ts.name, ts.session_type, ts.event_group,
               ts.intensity_level, ts.training_phase, atp.notes, atp.day_of_week
        FROM public.athlete_training_plans atp
        JOIN public.training_sessions ts ON ts.id = atp.training_session_id
        WHERE atp.athlete_id = ?
        ORDER BY atp.day_of_week NULLS LAST, ts.session_type, ts.name
    ''', (athlete_id,)).fetchall()

    all_training_sessions = db.execute('''
        SELECT id, name, session_type, event_group, intensity_level, training_phase
        FROM public.training_sessions
        WHERE NOT is_archived
        ORDER BY session_type, name
    ''').fetchall()

    db.close()
    return render_template('athlete_view.html',
                           athlete=athlete,
                           current_block=current_block,
                           tests=tests,
                           sc_logs=sc_logs,
                           training_plan=training_plan,
                           all_training_sessions=all_training_sessions)


# ---------------------------------------------------------------------------
# Athlete management — add / deactivate / delete
# ---------------------------------------------------------------------------

@app.route('/athletes/add', methods=['POST'])
@login_required
@admin_required
def add_athlete():
    name = request.form.get('name', '').strip()
    if not name:
        flash('Athlete name is required.', 'error')
        return redirect(url_for('athletes'))
    initials = request.form.get('initials', '').strip().upper() or (name[:1] + name.split()[-1][:1]).upper()
    event_group   = request.form.get('event_group', '').strip() or None
    squad         = request.form.get('squad', '').strip() or None
    dob           = request.form.get('dob', '').strip() or None
    assessment    = request.form.get('assessment_code', '').strip() or None
    db = get_db()
    try:
        db.execute('''
            INSERT INTO public.athletes(name, initials, event_group, squad, dob, assessment_code)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (name, initials, event_group, squad, dob, assessment))
        flash(f'{name} added.', 'success')
    except Exception as e:
        flash(f'Error adding athlete: {e}', 'error')
    db.close()
    return redirect(url_for('athletes'))


@app.route('/athletes/<int:athlete_id>/deactivate', methods=['POST'])
@login_required
@admin_required
def deactivate_athlete(athlete_id):
    db = get_db()
    db.execute('UPDATE public.athletes SET is_active = false WHERE id = ?', (athlete_id,))
    db.commit()
    db.close()
    flash('Athlete deactivated.', 'success')
    return redirect(url_for('athletes'))


@app.route('/athletes/<int:athlete_id>/reactivate', methods=['POST'])
@login_required
@admin_required
def reactivate_athlete(athlete_id):
    db = get_db()
    db.execute('UPDATE public.athletes SET is_active = true WHERE id = ?', (athlete_id,))
    db.commit()
    db.close()
    flash('Athlete reactivated.', 'success')
    return redirect(url_for('athlete_view', athlete_id=athlete_id))


@app.route('/athletes/<int:athlete_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_athlete(athlete_id):
    db = get_db()
    db.execute('DELETE FROM public.athletes WHERE id = ?', (athlete_id,))
    db.commit()
    db.close()
    flash('Athlete deleted.', 'success')
    return redirect(url_for('athletes'))


# ---------------------------------------------------------------------------
# Training session assignment
# ---------------------------------------------------------------------------

@app.route('/athletes/<int:athlete_id>/assign-session', methods=['POST'])
@login_required
@admin_required
def assign_training_session(athlete_id):
    session_id = request.form.get('session_id', type=int)
    notes = request.form.get('notes', '').strip() or None
    dow_raw = request.form.get('day_of_week', '').strip()
    day_of_week = int(dow_raw) if dow_raw.isdigit() else None
    if not session_id:
        flash('No session selected.', 'error')
        return redirect(url_for('athlete_view', athlete_id=athlete_id))
    db = get_db()
    try:
        db.execute('''
            INSERT INTO public.athlete_training_plans(athlete_id, training_session_id, notes, day_of_week)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (athlete_id, training_session_id)
            DO UPDATE SET day_of_week = EXCLUDED.day_of_week
        ''', (athlete_id, session_id, notes, day_of_week))
        db.commit()
    except Exception as e:
        flash(f'Error: {e}', 'error')
    db.close()
    return redirect(url_for('athlete_view', athlete_id=athlete_id))


@app.route('/athletes/<int:athlete_id>/remove-session/<int:plan_id>', methods=['POST'])
@login_required
@admin_required
def remove_training_session(athlete_id, plan_id):
    db = get_db()
    db.execute('DELETE FROM public.athlete_training_plans WHERE id = ? AND athlete_id = ?', (plan_id, athlete_id))
    db.commit()
    db.close()
    return redirect(url_for('athlete_view', athlete_id=athlete_id))


# ---------------------------------------------------------------------------
# Performance test entry
# ---------------------------------------------------------------------------

def _recalculate_pbs(db, athlete_id):
    """After inserting new test results, recalculate which is the PB for each metric."""
    metrics = db.execute('''
        SELECT DISTINCT tr.metric FROM public.test_results tr
        JOIN public.performance_tests pt ON tr.test_id = pt.id
        WHERE pt.athlete_id = ?
    ''', (athlete_id,)).fetchall()
    lower_metrics = {'20m', '60m', '150m'}
    for row in metrics:
        m = row['metric']
        order = 'ASC' if m in lower_metrics else 'DESC'
        pb_row = db.execute(f'''
            SELECT tr.id FROM public.test_results tr
            JOIN public.performance_tests pt ON tr.test_id = pt.id
            WHERE pt.athlete_id = ? AND tr.metric = ?
            ORDER BY tr.value {order} LIMIT 1
        ''', (athlete_id, m)).fetchone()
        db.execute('''
            UPDATE public.test_results SET is_pb = false
            WHERE test_id IN (SELECT id FROM public.performance_tests WHERE athlete_id = ?)
            AND metric = ?
        ''', (athlete_id, m))
        if pb_row:
            db.execute('UPDATE public.test_results SET is_pb = true WHERE id = ?', (pb_row['id'],))


METRIC_UNITS = {'20m': 'seconds', '60m': 'seconds', '150m': 'seconds', 'slj': 'metres', 'vj': 'centimetres'}


@app.route('/athletes/<int:athlete_id>/add-test', methods=['POST'])
@login_required
@admin_required
def add_performance_test(athlete_id):
    test_date = request.form.get('test_date', '').strip()
    protocol   = request.form.get('protocol', '').strip() or None
    conditions = request.form.get('conditions', '').strip() or None
    notes      = request.form.get('notes', '').strip() or None
    if not test_date:
        flash('Test date is required.', 'error')
        return redirect(url_for('athlete_performance', athlete_id=athlete_id))
    db = get_db()
    try:
        test_row = db.execute('''
            INSERT INTO public.performance_tests(athlete_id, test_date, test_protocol, conditions, notes)
            VALUES (?, ?, ?, ?, ?)
            RETURNING id
        ''', (athlete_id, test_date, protocol, conditions, notes)).fetchone()
        test_id = test_row['id']
        for metric in ['20m', '60m', '150m', 'slj', 'vj']:
            val_str = request.form.get(f'metric_{metric}', '').strip()
            if val_str:
                try:
                    val = float(val_str)
                    db.execute('''
                        INSERT INTO public.test_results(test_id, metric, value, unit)
                        VALUES (?, ?, ?, ?)
                    ''', (test_id, metric, val, METRIC_UNITS[metric]))
                except ValueError:
                    pass
        _recalculate_pbs(db, athlete_id)
        flash('Test results saved.', 'success')
    except Exception as e:
        flash(f'Error saving test: {e}', 'error')
    db.close()
    return redirect(url_for('athlete_performance', athlete_id=athlete_id))


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------
# ============================================================
# LEARNING HUB ROUTES — Paste into main.py
#
# Also add this import near the top of main.py (after existing imports):
#   from learning_content import INDUCTION_MODULES, LESSON_WEEKS, EMERGING_LESSON_WEEKS, EMERGING_T2_LESSON_WEEKS, FOUNDATION_T2_LESSON_WEEKS, PROGRESSION_LEVELS
#
# And add this near the top (after existing imports):
#   from collections import OrderedDict
#
# Uses: current_user (flask_login), %s placeholders, no ch. prefix
# ============================================================


# ── LEARNING HUB DASHBOARD ────────────────────────────────────────────────

@app.route('/learning')
@login_required
def learning_hub():
    db = get_db()

    rows = db.execute(
        'SELECT module_key FROM module_completions WHERE coach_id = %s',
        (current_user.id,)
    ).fetchall()
    completed_keys = {r['module_key'] for r in rows}

    induction_total = len(INDUCTION_MODULES)
    induction_done  = sum(1 for m in INDUCTION_MODULES if m['key'] in completed_keys)

    lesson_total    = len(LESSON_WEEKS)
    lesson_done     = sum(1 for w in LESSON_WEEKS if f"lesson_week_{w['week']}" in completed_keys)

    emerging_total  = len(EMERGING_LESSON_WEEKS)
    emerging_done   = sum(1 for w in EMERGING_LESSON_WEEKS if f"emerging_week_{w['week']}" in completed_keys)

    emerging_t2_total = len(EMERGING_T2_LESSON_WEEKS)
    emerging_t2_done  = sum(1 for w in EMERGING_T2_LESSON_WEEKS if f"emerging_t2_week_{w['week']}" in completed_keys)

    foundation_t2_total = len(FOUNDATION_T2_LESSON_WEEKS)
    foundation_t2_done  = sum(1 for w in FOUNDATION_T2_LESSON_WEEKS if f"foundation_t2_week_{w['week']}" in completed_keys)

    prog_total = len(PROGRESSION_LEVELS)
    prog_done  = sum(1 for l in PROGRESSION_LEVELS if l['key'] in completed_keys)

    checklist_total = db.execute(
        'SELECT COUNT(*) AS c FROM induction_checklist_items'
    ).fetchone()['c']

    checklist_done = db.execute(
        'SELECT COUNT(*) AS c FROM induction_checklist_progress WHERE coach_id = %s AND completed_at IS NOT NULL',
        (current_user.id,)
    ).fetchone()['c']

    db.close()

    return render_template('learning_hub.html',
        is_admin=current_user.is_admin,
        induction_total=induction_total,
        induction_done=induction_done,
        lesson_total=lesson_total,
        lesson_done=lesson_done,
        emerging_total=emerging_total,
        emerging_done=emerging_done,
        emerging_t2_total=emerging_t2_total,
        emerging_t2_done=emerging_t2_done,
        foundation_t2_total=foundation_t2_total,
        foundation_t2_done=foundation_t2_done,
        prog_total=prog_total,
        prog_done=prog_done,
        checklist_total=checklist_total,
        checklist_done=checklist_done,
    )


@app.route('/learning/train-the-mind-t4')
@login_required
def learning_train_the_mind_t4():
    return render_template('learning_train_the_mind_t4.html')


@app.route('/learning/train-the-mind-t4/pdf')
@login_required
def learning_train_the_mind_t4_pdf():
    return send_from_directory(
        os.path.join(app.root_path, 'attached_assets'),
        'train-the-mind-t4-2026_1790054146542.pdf',
        as_attachment=True,
        download_name='Power2ADAPT-Train-the-Mind-Term-4-2026.pdf',
    )


# ── INDUCTION TRACK ───────────────────────────────────────────────────────

@app.route('/learning/induction')
@login_required
def learning_induction():
    db = get_db()
    rows = db.execute(
        'SELECT module_key FROM module_completions WHERE coach_id = %s',
        (current_user.id,)
    ).fetchall()
    completed_keys = {r['module_key'] for r in rows}
    db.close()

    modules_with_status = [
        {**m, 'completed': m['key'] in completed_keys}
        for m in INDUCTION_MODULES
    ]
    return render_template('learning_induction.html', modules=modules_with_status)


@app.route('/learning/induction/<module_key>')
@login_required
def learning_module(module_key):
    module = next((m for m in INDUCTION_MODULES if m['key'] == module_key), None)
    if not module:
        return redirect(url_for('learning_induction'))

    db = get_db()
    row = db.execute(
        'SELECT id FROM module_completions WHERE coach_id = %s AND module_key = %s',
        (current_user.id, module_key)
    ).fetchone()
    completed = row is not None
    db.close()

    idx = next(i for i, m in enumerate(INDUCTION_MODULES) if m['key'] == module_key)
    prev_module = INDUCTION_MODULES[idx - 1] if idx > 0 else None
    next_module = INDUCTION_MODULES[idx + 1] if idx < len(INDUCTION_MODULES) - 1 else None

    return render_template('learning_module.html',
        module=module,
        completed=completed,
        prev_module=prev_module,
        next_module=next_module,
    )


@app.route('/learning/induction/<module_key>/complete', methods=['POST'])
@login_required
def complete_module(module_key):
    db = get_db()
    db.execute(
        'INSERT INTO module_completions (coach_id, module_key) VALUES (%s, %s) ON CONFLICT DO NOTHING',
        (current_user.id, module_key)
    )
    db.commit()
    db.close()
    return redirect(url_for('learning_module', module_key=module_key))


# ── INDUCTION CHECKLIST ───────────────────────────────────────────────────

@app.route('/learning/checklist')
@login_required
def learning_checklist():
    db = get_db()

    items = db.execute(
        'SELECT * FROM induction_checklist_items ORDER BY sequence_order'
    ).fetchall()

    rows = db.execute(
        'SELECT item_id, completed_at, admin_signoff_at FROM induction_checklist_progress WHERE coach_id = %s',
        (current_user.id,)
    ).fetchall()
    progress = {r['item_id']: r for r in rows}

    grouped = OrderedDict()
    for item in items:
        cat = item['category']
        if cat not in grouped:
            grouped[cat] = []
        p = progress.get(item['id'])
        grouped[cat].append({
            'id':             item['id'],
            'text':           item['item_text'],
            'requires_admin': item['requires_admin_signoff'],
            'completed':      bool(p and p['completed_at']),
            'admin_signed':   bool(p and p['admin_signoff_at']),
        })

    db.close()
    return render_template('learning_checklist.html',
        grouped=grouped,
        is_admin=current_user.is_admin,
        coach_id=current_user.id,
    )


@app.route('/learning/checklist/<int:item_id>/complete', methods=['POST'])
@login_required
def complete_checklist_item(item_id):
    db = get_db()
    db.execute('''
        INSERT INTO induction_checklist_progress (coach_id, item_id, completed_at)
        VALUES (%s, %s, NOW())
        ON CONFLICT (coach_id, item_id) DO UPDATE SET completed_at = NOW()
    ''', (current_user.id, item_id))
    db.commit()
    db.close()
    return redirect(url_for('learning_checklist'))


@app.route('/learning/checklist/<int:item_id>/signoff', methods=['POST'])
@login_required
def signoff_checklist_item(item_id):
    if not current_user.is_admin:
        return redirect(url_for('learning_hub'))
    coach_id = request.form.get('coach_id', type=int)
    db = get_db()
    db.execute('''
        INSERT INTO induction_checklist_progress (coach_id, item_id, admin_signoff_at)
        VALUES (%s, %s, NOW())
        ON CONFLICT (coach_id, item_id) DO UPDATE SET admin_signoff_at = NOW()
    ''', (coach_id, item_id))
    db.commit()
    db.close()
    return redirect(url_for('admin_coach_induction', coach_id=coach_id))


# ── LESSON PLANS ──────────────────────────────────────────────────────────

@app.route('/learning/lesson-plans')
@login_required
def learning_lesson_plans():
    db = get_db()
    rows = db.execute(
        'SELECT module_key FROM module_completions WHERE coach_id = %s',
        (current_user.id,)
    ).fetchall()
    completed_keys = {r['module_key'] for r in rows}
    db.close()

    weeks_with_status = [
        {**w, 'completed': f"lesson_week_{w['week']}" in completed_keys}
        for w in LESSON_WEEKS
    ]
    emerging_with_status = [
        {**w, 'completed': f"emerging_week_{w['week']}" in completed_keys}
        for w in EMERGING_LESSON_WEEKS
    ]
    emerging_t2_with_status = [
        {**w, 'completed': f"emerging_t2_week_{w['week']}" in completed_keys}
        for w in EMERGING_T2_LESSON_WEEKS
    ]
    foundation_t2_with_status = [
        {**w, 'completed': f"foundation_t2_week_{w['week']}" in completed_keys}
        for w in FOUNDATION_T2_LESSON_WEEKS
    ]
    return render_template('learning_lesson_plans.html',
        weeks=weeks_with_status,
        emerging_weeks=emerging_with_status,
        emerging_t2_weeks=emerging_t2_with_status,
        foundation_t2_weeks=foundation_t2_with_status,
    )


@app.route('/learning/lesson-plans/<int:week_num>')
@login_required
def learning_lesson_week(week_num):
    week = next((w for w in LESSON_WEEKS if w['week'] == week_num), None)
    if not week:
        return redirect(url_for('learning_lesson_plans'))

    db = get_db()
    row = db.execute(
        'SELECT id FROM module_completions WHERE coach_id = %s AND module_key = %s',
        (current_user.id, f'lesson_week_{week_num}')
    ).fetchone()
    completed = row is not None
    db.close()

    prev_week = next((w for w in LESSON_WEEKS if w['week'] == week_num - 1), None)
    next_week = next((w for w in LESSON_WEEKS if w['week'] == week_num + 1), None)

    return render_template('learning_lesson_week.html',
        week=week,
        completed=completed,
        prev_week=prev_week,
        next_week=next_week,
        back_url=url_for('learning_lesson_plans'),
        complete_url=url_for('complete_lesson_week', week_num=week_num),
        prev_url=url_for('learning_lesson_week', week_num=prev_week['week']) if prev_week else None,
        next_url=url_for('learning_lesson_week', week_num=next_week['week']) if next_week else None,
    )


@app.route('/learning/lesson-plans/<int:week_num>/complete', methods=['POST'])
@login_required
def complete_lesson_week(week_num):
    db = get_db()
    db.execute(
        'INSERT INTO module_completions (coach_id, module_key) VALUES (%s, %s) ON CONFLICT DO NOTHING',
        (current_user.id, f'lesson_week_{week_num}')
    )
    db.commit()
    db.close()
    return redirect(url_for('learning_lesson_week', week_num=week_num))


# ── FOUNDATION T2 TRACK ────────────────────────────────────────────────────

@app.route('/learning/lesson-plans/foundation-t2/<int:week_num>')
@login_required
def learning_foundation_t2_week(week_num):
    week = next((w for w in FOUNDATION_T2_LESSON_WEEKS if w['week'] == week_num), None)
    if not week:
        return redirect(url_for('learning_lesson_plans'))
    db = get_db()
    row = db.execute(
        'SELECT id FROM module_completions WHERE coach_id = %s AND module_key = %s',
        (current_user.id, f'foundation_t2_week_{week_num}')
    ).fetchone()
    completed = row is not None
    db.close()
    prev_week = next((w for w in FOUNDATION_T2_LESSON_WEEKS if w['week'] == week_num - 1), None)
    next_week = next((w for w in FOUNDATION_T2_LESSON_WEEKS if w['week'] == week_num + 1), None)
    return render_template('learning_lesson_week.html',
        week=week, completed=completed,
        prev_week=prev_week, next_week=next_week,
        back_url=url_for('learning_lesson_plans') + '#foundation-t2',
        complete_url=url_for('complete_foundation_t2_week', week_num=week_num),
        prev_url=url_for('learning_foundation_t2_week', week_num=prev_week['week']) if prev_week else None,
        next_url=url_for('learning_foundation_t2_week', week_num=next_week['week']) if next_week else None,
    )


@app.route('/learning/lesson-plans/foundation-t2/<int:week_num>/complete', methods=['POST'])
@login_required
def complete_foundation_t2_week(week_num):
    db = get_db()
    db.execute(
        'INSERT INTO module_completions (coach_id, module_key) VALUES (%s, %s) ON CONFLICT DO NOTHING',
        (current_user.id, f'foundation_t2_week_{week_num}')
    )
    db.commit()
    db.close()
    return redirect(url_for('learning_foundation_t2_week', week_num=week_num))


# ── EMERGING PROGRAM TRACK ─────────────────────────────────────────────────

@app.route('/learning/lesson-plans/emerging/<int:week_num>')
@login_required
def learning_emerging_week(week_num):
    week = next((w for w in EMERGING_LESSON_WEEKS if w['week'] == week_num), None)
    if not week:
        return redirect(url_for('learning_lesson_plans'))

    db = get_db()
    row = db.execute(
        'SELECT id FROM module_completions WHERE coach_id = %s AND module_key = %s',
        (current_user.id, f'emerging_week_{week_num}')
    ).fetchone()
    completed = row is not None
    db.close()

    prev_week = next((w for w in EMERGING_LESSON_WEEKS if w['week'] == week_num - 1), None)
    next_week = next((w for w in EMERGING_LESSON_WEEKS if w['week'] == week_num + 1), None)

    return render_template('learning_lesson_week.html',
        week=week,
        completed=completed,
        prev_week=prev_week,
        next_week=next_week,
        back_url=url_for('learning_lesson_plans') + '#emerging',
        complete_url=url_for('complete_emerging_week', week_num=week_num),
        prev_url=url_for('learning_emerging_week', week_num=prev_week['week']) if prev_week else None,
        next_url=url_for('learning_emerging_week', week_num=next_week['week']) if next_week else None,
    )


@app.route('/learning/lesson-plans/emerging/<int:week_num>/complete', methods=['POST'])
@login_required
def complete_emerging_week(week_num):
    db = get_db()
    db.execute(
        'INSERT INTO module_completions (coach_id, module_key) VALUES (%s, %s) ON CONFLICT DO NOTHING',
        (current_user.id, f'emerging_week_{week_num}')
    )
    db.commit()
    db.close()
    return redirect(url_for('learning_emerging_week', week_num=week_num))


# ── EMERGING T2 TRACK ──────────────────────────────────────────────────────

@app.route('/learning/lesson-plans/emerging-t2/<int:week_num>')
@login_required
def learning_emerging_t2_week(week_num):
    week = next((w for w in EMERGING_T2_LESSON_WEEKS if w['week'] == week_num), None)
    if not week:
        return redirect(url_for('learning_lesson_plans'))
    db = get_db()
    row = db.execute(
        'SELECT id FROM module_completions WHERE coach_id = %s AND module_key = %s',
        (current_user.id, f'emerging_t2_week_{week_num}')
    ).fetchone()
    completed = row is not None
    db.close()
    prev_week = next((w for w in EMERGING_T2_LESSON_WEEKS if w['week'] == week_num - 1), None)
    next_week = next((w for w in EMERGING_T2_LESSON_WEEKS if w['week'] == week_num + 1), None)
    return render_template('learning_lesson_week.html',
        week=week, completed=completed,
        prev_week=prev_week, next_week=next_week,
        back_url=url_for('learning_lesson_plans') + '#emerging-t2',
        complete_url=url_for('complete_emerging_t2_week', week_num=week_num),
        prev_url=url_for('learning_emerging_t2_week', week_num=prev_week['week']) if prev_week else None,
        next_url=url_for('learning_emerging_t2_week', week_num=next_week['week']) if next_week else None,
    )


@app.route('/learning/lesson-plans/emerging-t2/<int:week_num>/complete', methods=['POST'])
@login_required
def complete_emerging_t2_week(week_num):
    db = get_db()
    db.execute(
        'INSERT INTO module_completions (coach_id, module_key) VALUES (%s, %s) ON CONFLICT DO NOTHING',
        (current_user.id, f'emerging_t2_week_{week_num}')
    )
    db.commit()
    db.close()
    return redirect(url_for('learning_emerging_t2_week', week_num=week_num))


# ── PROGRESSION TRACK ─────────────────────────────────────────────────────

@app.route('/learning/progression')
@login_required
def learning_progression():
    db = get_db()
    rows = db.execute(
        'SELECT module_key FROM module_completions WHERE coach_id = %s',
        (current_user.id,)
    ).fetchall()
    completed_keys = {r['module_key'] for r in rows}
    db.close()

    levels_with_status = [
        {**l, 'completed': l['key'] in completed_keys}
        for l in PROGRESSION_LEVELS
    ]
    return render_template('learning_progression.html', levels=levels_with_status)


@app.route('/learning/progression/<level_key>')
@login_required
def learning_progression_level(level_key):
    level = next((l for l in PROGRESSION_LEVELS if l['key'] == level_key), None)
    if not level:
        return redirect(url_for('learning_progression'))

    db = get_db()
    row = db.execute(
        'SELECT id FROM module_completions WHERE coach_id = %s AND module_key = %s',
        (current_user.id, level_key)
    ).fetchone()
    completed = row is not None
    db.close()

    idx = next(i for i, l in enumerate(PROGRESSION_LEVELS) if l['key'] == level_key)
    prev_level = PROGRESSION_LEVELS[idx - 1] if idx > 0 else None
    next_level = PROGRESSION_LEVELS[idx + 1] if idx < len(PROGRESSION_LEVELS) - 1 else None

    return render_template('learning_progression_level.html',
        level=level,
        completed=completed,
        prev_level=prev_level,
        next_level=next_level,
    )


@app.route('/learning/progression/<level_key>/complete', methods=['POST'])
@login_required
def complete_progression_level(level_key):
    db = get_db()
    db.execute(
        'INSERT INTO module_completions (coach_id, module_key) VALUES (%s, %s) ON CONFLICT DO NOTHING',
        (current_user.id, level_key)
    )
    db.commit()
    db.close()
    return redirect(url_for('learning_progression_level', level_key=level_key))


# ── ADMIN — ALL COACH PROGRESS ────────────────────────────────────────────

@app.route('/learning/admin/progress')
@login_required
def admin_learning_progress():
    if not current_user.is_admin:
        return redirect(url_for('learning_hub'))

    db = get_db()
    coaches = db.execute(
        'SELECT id, name FROM coaches WHERE is_active = 1 ORDER BY name'
    ).fetchall()

    checklist_total = db.execute(
        'SELECT COUNT(*) AS c FROM induction_checklist_items'
    ).fetchone()['c']

    coach_progress = []
    for coach in coaches:
        done_rows = db.execute(
            'SELECT module_key FROM module_completions WHERE coach_id = %s',
            (coach['id'],)
        ).fetchall()
        done_keys = {r['module_key'] for r in done_rows}

        checklist_done = db.execute(
            'SELECT COUNT(*) AS c FROM induction_checklist_progress WHERE coach_id = %s AND completed_at IS NOT NULL',
            (coach['id'],)
        ).fetchone()['c']

        coach_progress.append({
            'id':              coach['id'],
            'name':            coach['name'],
            'induction_done':  sum(1 for m in INDUCTION_MODULES if m['key'] in done_keys),
            'induction_total': len(INDUCTION_MODULES),
            'lesson_done':     sum(1 for w in LESSON_WEEKS if f"lesson_week_{w['week']}" in done_keys),
            'lesson_total':    len(LESSON_WEEKS),
            'prog_done':       sum(1 for l in PROGRESSION_LEVELS if l['key'] in done_keys),
            'prog_total':      len(PROGRESSION_LEVELS),
            'checklist_done':  checklist_done,
            'checklist_total': checklist_total,
        })

    db.close()
    return render_template('admin_learning_progress.html', coaches=coach_progress)


@app.route('/learning/admin/coach/<int:coach_id>/induction')
@login_required
def admin_coach_induction(coach_id):
    if not current_user.is_admin:
        return redirect(url_for('learning_hub'))

    db = get_db()
    coach = db.execute(
        'SELECT id, name FROM coaches WHERE id = %s',
        (coach_id,)
    ).fetchone()

    items = db.execute(
        'SELECT * FROM induction_checklist_items ORDER BY sequence_order'
    ).fetchall()

    rows = db.execute(
        'SELECT item_id, completed_at, admin_signoff_at FROM induction_checklist_progress WHERE coach_id = %s',
        (coach_id,)
    ).fetchall()
    progress = {r['item_id']: r for r in rows}

    grouped = OrderedDict()
    for item in items:
        cat = item['category']
        if cat not in grouped:
            grouped[cat] = []
        p = progress.get(item['id'])
        grouped[cat].append({
            'id':             item['id'],
            'text':           item['item_text'],
            'requires_admin': item['requires_admin_signoff'],
            'completed':      bool(p and p['completed_at']),
            'admin_signed':   bool(p and p['admin_signoff_at']),
        })

    db.close()
    return render_template('admin_coach_induction.html',
        coach=coach,
        grouped=grouped,
    )

# ── External API ────────────────────────────────────────────────────────────

@app.route('/api/this-week')
def api_this_week():
    api_key = request.args.get('key', '')
    expected_key = app.config.get('API_KEY')

    if not expected_key or api_key != expected_key:
        return jsonify({'error': 'unauthorised'}), 401

    db = get_db()

    try:
        today = datetime.now(AEST).date()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        term_schedules = load_week_session_schedules(db, week_start, week_end)

        sessions = db.execute(
            "SELECT * FROM sessions WHERE is_active = 1 ORDER BY "
            "CASE day_of_week WHEN 'Monday' THEN 1 WHEN 'Tuesday' THEN 2 "
            "WHEN 'Wednesday' THEN 3 WHEN 'Thursday' THEN 4 WHEN 'Friday' THEN 5 "
            "WHEN 'Saturday' THEN 6 WHEN 'Sunday' THEN 7 ELSE 8 END, start_time"
        ).fetchall()

        result = []

        for s in sessions:
            try:
                day_num = DAY_ORDER.index(s['day_of_week'])
            except ValueError:
                continue

            session_date = week_start + timedelta(days=day_num)
            if not session_occurs_in_week(s['id'], session_date, term_schedules):
                continue

            entries = db.execute('''
                SELECT c.name FROM roster_entries re
                JOIN coaches c ON re.coach_id = c.id
                WHERE re.session_id = ? AND re.date = ?
            ''', (s['id'], session_date.isoformat())).fetchall()

            assigned = len(entries)

            status = (
                'empty' if assigned == 0 else
                'understaffed' if assigned < s['min_coaches'] else
                'staffed'
            )

            result.append({
                'day': s['day_of_week'],
                'date': session_date.isoformat(),
                'time': f"{s['start_time']}-{s['end_time']}",
                'location': s['location'],
                'programs': s['programs'],
                'coaches': [e['name'] for e in entries],
                'assigned': assigned,
                'min_required': s['min_coaches'],
                'status': status,
            })

        return jsonify({
            'week_start': week_start.isoformat(),
            'sessions': result
        })

    finally:
        db.close()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
