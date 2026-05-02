import json
import secrets
from datetime import datetime, timedelta, date

import pytz
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash

from config import Config
from database import get_db, init_db
from services.term_dates import get_session_dates_for_term, get_current_or_next_term
from services.google_sheets import get_sheet_availability
from services.twilio_service import send_sms
from services.scheduler import start_scheduler

app = Flask(__name__)
app.config.from_object(Config)

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

    def get_id(self):
        return str(self.id)


@login_manager.user_loader
def load_user(user_id):
    db = get_db()
    row = db.execute('SELECT * FROM coaches WHERE id = ?', (user_id,)).fetchone()
    db.close()
    return User(row) if row else None


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    return redirect(url_for('dashboard'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        password = request.form.get('password', '')
        db = get_db()
        row = db.execute(
            'SELECT * FROM coaches WHERE username = ? AND is_active = 1', (username,)
        ).fetchone()
        db.close()
        if row and check_password_hash(row['password_hash'], password):
            login_user(User(row))
            return redirect(url_for('dashboard'))
        flash('Invalid username or password.', 'error')
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.route('/dashboard')
@login_required
def dashboard():
    db = get_db()
    today = datetime.now(AEST).date()
    # Get start/end of this week (Mon-Fri)
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    sessions = db.execute(
        'SELECT * FROM sessions WHERE is_active = 1 ORDER BY '
        'CASE day_of_week WHEN "Monday" THEN 1 WHEN "Tuesday" THEN 2 WHEN "Wednesday" THEN 3 '
        'WHEN "Thursday" THEN 4 WHEN "Friday" THEN 5 ELSE 6 END, start_time'
    ).fetchall()

    # Build this week's schedule with roster info
    week_schedule = []
    for s in sessions:
        # Find the date this session falls on this week
        day_num = DAY_ORDER.index(s['day_of_week'])
        session_date = week_start + timedelta(days=day_num)
        if session_date > week_end:
            continue

        # Get roster entries for this session on this date
        entries = db.execute('''
            SELECT re.*, c.name as coach_name FROM roster_entries re
            JOIN coaches c ON re.coach_id = c.id
            WHERE re.session_id = ? AND re.date = ?
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
                           gaps=gaps)


# ---------------------------------------------------------------------------
# Roster
# ---------------------------------------------------------------------------

@app.route('/roster')
@login_required
def roster():
    db = get_db()
    current_term = get_current_or_next_term(db)
    db.close()
    if current_term:
        return redirect(url_for('roster_term', term_id=current_term['id']))
    return redirect(url_for('roster_term', term_id=1))


@app.route('/roster/<int:term_id>')
@login_required
def roster_term(term_id):
    db = get_db()
    terms = db.execute('SELECT * FROM terms ORDER BY start_date').fetchall()
    term = db.execute('SELECT * FROM terms WHERE id = ?', (term_id,)).fetchone()
    if not term:
        db.close()
        flash('Term not found.', 'error')
        return redirect(url_for('dashboard'))

    sessions = db.execute(
        'SELECT * FROM sessions WHERE is_active = 1 ORDER BY '
        'CASE day_of_week WHEN "Monday" THEN 1 WHEN "Tuesday" THEN 2 WHEN "Wednesday" THEN 3 '
        'WHEN "Thursday" THEN 4 WHEN "Friday" THEN 5 ELSE 6 END, start_time'
    ).fetchall()

    coaches = db.execute(
        'SELECT * FROM coaches WHERE is_active = 1 ORDER BY name'
    ).fetchall()

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
            if session_date < term_start or session_date > term_end:
                week_start += timedelta(days=7)
                continue

            entries = db.execute('''
                SELECT re.*, c.name as coach_name, c.id as coach_id
                FROM roster_entries re
                JOIN coaches c ON re.coach_id = c.id
                WHERE re.session_id = ? AND re.date = ? AND re.term_id = ?
            ''', (s['id'], session_date.isoformat(), term_id)).fetchall()

            assigned = len(entries)
            if assigned == 0:
                status = 'empty'
            elif assigned < s['min_coaches']:
                status = 'understaffed'
            elif assigned < s['max_coaches']:
                status = 'staffed'
            else:
                status = 'full'

            week_sessions.append({
                'session': s,
                'date': session_date,
                'entries': entries,
                'assigned': assigned,
                'status': status,
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

    db = get_db()
    try:
        db.execute('''
            INSERT OR IGNORE INTO roster_entries (term_id, session_id, date, coach_id)
            VALUES (?, ?, ?, ?)
        ''', (term_id, session_id, roster_date, coach_id))
        db.commit()
        coach = db.execute('SELECT name FROM coaches WHERE id = ?', (coach_id,)).fetchone()
        db.close()
        return jsonify({'success': True, 'coach_name': coach['name']})
    except Exception as e:
        db.close()
        return jsonify({'error': str(e)}), 500


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
        WHERE term_id = ? AND session_id = ? AND date = ? AND coach_id = ?
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
    term = db.execute('SELECT * FROM terms WHERE id = ?', (term_id,)).fetchone()
    sessions = db.execute('SELECT * FROM sessions WHERE is_active = 1').fetchall()
    coaches = db.execute(
        'SELECT * FROM coaches WHERE is_active = 1 AND is_standby = 0'
    ).fetchall()

    # Get availability responses for this term
    availability = {}
    for c in coaches:
        resp = db.execute(
            'SELECT * FROM availability_responses WHERE coach_id = ? AND term_id = ?',
            (c['id'], term_id)
        ).fetchone()
        if resp:
            availability[c['id']] = {
                'weekly': json.loads(resp['weekly_availability'] or '{}'),
                'unavailable_dates': json.loads(resp['unavailable_dates'] or '[]'),
            }

    # Clear existing auto-generated entries for this term
    db.execute('DELETE FROM roster_entries WHERE term_id = ?', (term_id,))

    term_start = date.fromisoformat(term['start_date'])
    term_end = date.fromisoformat(term['end_date'])

    # Track assignments per coach for load balancing
    coach_assignment_count = {c['id']: 0 for c in coaches}

    entries_to_insert = []
    current_date = term_start
    while current_date <= term_end:
        day_name = current_date.strftime('%A')
        date_str = current_date.isoformat()

        day_sessions = [s for s in sessions if s['day_of_week'] == day_name]

        for s in day_sessions:
            # Determine available coaches for this date
            available = []
            for c in coaches:
                avail = availability.get(c['id'], {})
                weekly = avail.get('weekly', {})
                unavailable_dates = avail.get('unavailable_dates', [])

                # Check specific date unavailability
                if date_str in unavailable_dates:
                    continue
                # Check weekly availability (if submitted, must be True for this day)
                if weekly and not weekly.get(day_name, True):
                    continue
                available.append(c)

            # For school sessions, prefer Level 2+
            is_school = s['location'] in ('Peninsula Grammar', 'Toorak College')
            if is_school:
                preferred = [c for c in available if c['level'] in ('Level 2', 'Level 3')]
                others = [c for c in available if c not in preferred]
                ordered = sorted(preferred, key=lambda c: coach_assignment_count[c['id']]) + \
                          sorted(others, key=lambda c: coach_assignment_count[c['id']])
            else:
                ordered = sorted(available, key=lambda c: coach_assignment_count[c['id']])

            assigned = 0
            for c in ordered:
                if assigned >= s['max_coaches']:
                    break
                entries_to_insert.append((term_id, s['id'], date_str, c['id']))
                coach_assignment_count[c['id']] += 1
                assigned += 1

        current_date += timedelta(days=1)

    for entry in entries_to_insert:
        try:
            db.execute(
                'INSERT OR IGNORE INTO roster_entries (term_id, session_id, date, coach_id) VALUES (?, ?, ?, ?)',
                entry
            )
        except Exception:
            pass

    db.commit()
    db.close()
    flash(f'Roster generated for {term["name"]} -- {len(entries_to_insert)} assignments created.', 'success')
    return redirect(url_for('roster_term', term_id=term_id))


@app.route('/roster/<int:term_id>/clear', methods=['POST'])
@login_required
def roster_clear(term_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorised'}), 403
    db = get_db()
    db.execute('DELETE FROM roster_entries WHERE term_id = ?', (term_id,))
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
                'SELECT * FROM availability_responses WHERE coach_id = ? AND term_id = ?',
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
    db = get_db()
    term = db.execute('SELECT * FROM terms WHERE id = ?', (term_id,)).fetchone()
    coaches = db.execute(
        'SELECT * FROM coaches WHERE is_active = 1 AND is_standby = 0 AND mobile IS NOT NULL'
    ).fetchall()

    sent = 0
    for coach in coaches:
        token = secrets.token_urlsafe(24)
        expires = datetime.utcnow() + timedelta(days=14)
        expires_str = expires.strftime('%Y-%m-%d %H:%M:%S')
        db.execute('''
            INSERT OR REPLACE INTO availability_tokens (coach_id, term_id, token, expires_at)
            VALUES (?, ?, ?, ?)
        ''', (coach['id'], term_id, token, expires_str))

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
            VALUES (?, ?, ?, ?, ?)
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
        WHERE at.token = ?
    ''', (token,)).fetchone()

    if not tok:
        db.close()
        return render_template('availability_form.html', error='Invalid link.')

    if tok['used']:
        # Load existing response to show it
        existing = db.execute(
            'SELECT * FROM availability_responses WHERE coach_id = ? AND term_id = ?',
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

    db.close()
    return render_template('availability_form.html',
                           tok=tok,
                           token=token,
                           term_dates=term_dates,
                           days_of_week=['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'])


@app.route('/availability/<token>/submit', methods=['POST'])
def availability_submit(token):
    db = get_db()
    tok = db.execute(
        'SELECT * FROM availability_tokens WHERE token = ?', (token,)
    ).fetchone()

    if not tok or tok['used']:
        db.close()
        flash('This link has already been used or is invalid.', 'error')
        return redirect(url_for('availability_form', token=token))

    weekly = {}
    for day in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']:
        weekly[day] = request.form.get(f'weekly_{day}') != 'unavailable'

    unavailable_dates = request.form.getlist('unavailable_dates')
    notes = request.form.get('notes', '')

    db.execute('''
        INSERT OR REPLACE INTO availability_responses
        (coach_id, term_id, weekly_availability, unavailable_dates, notes, submitted_at)
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    ''', (tok['coach_id'], tok['term_id'],
          json.dumps(weekly), json.dumps(unavailable_dates), notes))

    db.execute('UPDATE availability_tokens SET used = 1 WHERE token = ?', (token,))
    db.commit()
    db.close()

    return render_template('availability_form.html', submitted=True, token=token)


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

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
    return render_template('alerts.html', coaches=coaches, terms=terms, log=log)


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
            f'SELECT * FROM coaches WHERE id IN ({",".join("?" * len(coach_ids))}) AND mobile IS NOT NULL',
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
            VALUES (?, ?, ?, ?, ?)
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
            f'SELECT * FROM coaches WHERE id IN ({",".join("?" * len(coach_ids))}) AND mobile IS NOT NULL',
            coach_ids
        ).fetchall()
    else:
        coaches = db.execute(
            'SELECT * FROM coaches WHERE is_active = 1 AND mobile IS NOT NULL'
        ).fetchall()

    sent = 0
    for coach in coaches:
        result = send_sms(
            app.config['TWILIO_ACCOUNT_SID'],
            app.config['TWILIO_AUTH_TOKEN'],
            app.config['TWILIO_FROM_NUMBER'],
            coach['mobile'],
            message_text
        )
        db.execute('''
            INSERT INTO sms_log (coach_id, mobile, message, type, status)
            VALUES (?, ?, ?, ?, ?)
        ''', (coach['id'], coach['mobile'], message_text, 'custom',
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
    coaches = db.execute('SELECT * FROM coaches ORDER BY is_active DESC, name').fetchall()
    db.close()
    return render_template('coaches.html', coaches=coaches)


@app.route('/admin/coaches/add', methods=['POST'])
@login_required
def admin_coaches_add():
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorised'}), 403

    name = request.form.get('name', '').strip()
    username = request.form.get('username', '').strip().lower()
    email = request.form.get('email', '').strip() or None
    mobile = request.form.get('mobile', '').strip() or None
    role = request.form.get('role', '').strip()
    level = request.form.get('level', '').strip()
    is_standby = 1 if request.form.get('is_standby') else 0
    password = request.form.get('password', 'CoachHub2026')

    db = get_db()
    try:
        db.execute('''
            INSERT INTO coaches (name, username, email, mobile, role, level, is_standby, password_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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

    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip() or None
    mobile = request.form.get('mobile', '').strip() or None
    role = request.form.get('role', '').strip()
    level = request.form.get('level', '').strip()
    is_standby = 1 if request.form.get('is_standby') else 0
    new_password = request.form.get('new_password', '').strip()

    db = get_db()
    if new_password:
        db.execute('''
            UPDATE coaches SET name=?, email=?, mobile=?, role=?, level=?, is_standby=?,
            password_hash=? WHERE id=?
        ''', (name, email, mobile, role, level, is_standby,
              generate_password_hash(new_password), coach_id))
    else:
        db.execute('''
            UPDATE coaches SET name=?, email=?, mobile=?, role=?, level=?, is_standby=?
            WHERE id=?
        ''', (name, email, mobile, role, level, is_standby, coach_id))
    db.commit()
    db.close()
    flash('Coach updated.', 'success')
    return redirect(url_for('admin_coaches'))


@app.route('/admin/coaches/<int:coach_id>/toggle', methods=['POST'])
@login_required
def admin_coaches_toggle(coach_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorised'}), 403
    db = get_db()
    db.execute('UPDATE coaches SET is_active = NOT is_active WHERE id = ?', (coach_id,))
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
    sessions = db.execute(
        'SELECT * FROM sessions ORDER BY '
        'CASE day_of_week WHEN "Monday" THEN 1 WHEN "Tuesday" THEN 2 WHEN "Wednesday" THEN 3 '
        'WHEN "Thursday" THEN 4 WHEN "Friday" THEN 5 ELSE 6 END, start_time'
    ).fetchall()
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
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
        UPDATE sessions SET day_of_week=?, start_time=?, end_time=?, location=?,
        programs=?, min_coaches=?, max_coaches=?, notes=? WHERE id=?
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
    db.execute('UPDATE sessions SET is_active = NOT is_active WHERE id = ?', (session_id,))
    db.commit()
    db.close()
    return redirect(url_for('admin_sessions'))


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

with app.app_context():
    init_db()
    start_scheduler(app)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
