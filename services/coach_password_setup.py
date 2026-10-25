import hashlib
import re
import secrets
from datetime import datetime, timezone
from urllib.parse import urlparse

import pytz
from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from database import get_db
from services.coach_auth_state import bump_auth_version
from services.coach_setup_sms import SetupDeliveryError, send_setup_sms, verify_setup_sender

coach_setup = Blueprint('coach_setup', __name__)

def normalize_setup_mobile(value):
    number = re.sub(r'[\s()-]', '', value or '')
    if re.fullmatch(r'04\d{8}', number):
        number = '+61' + number[1:]
    return number if re.fullmatch(r'\+[1-9]\d{7,14}', number) else None


def revoke_setup_links(db, coach_id, except_id=None):
    db.execute('''
        UPDATE public.coach_password_setups SET revoked_at = NOW()
        WHERE coach_id = %s AND completed_at IS NULL AND revoked_at IS NULL
          AND id <> COALESCE(%s, -1)
    ''', (coach_id, except_id))


def setup_statuses(db):
    rows = db.execute('''
        SELECT DISTINCT ON (coach_id) coach_id, delivery_status, sent_at,
               completed_at, expires_at, revoked_at,
               MAX(sent_at) OVER (PARTITION BY coach_id) AS last_sent_at,
               MAX(completed_at) OVER (PARTITION BY coach_id) AS last_completed_at
        FROM public.coach_password_setups ORDER BY coach_id, created_at DESC, id DESC
    ''').fetchall()
    statuses = {}
    now = datetime.now(timezone.utc)
    tz = pytz.timezone('Australia/Melbourne')
    def label(value):
        return value.astimezone(tz).strftime('%d %b %Y, %I:%M %p') if value else ''
    for row in rows:
        status = 'Not sent'
        if row['completed_at']:
            status = 'Completed'
        elif row['delivery_status'] == 'failed':
            status = 'Send failed'
        elif row['delivery_status'] == 'sent':
            status = 'Expired' if row['expires_at'] <= now or row['revoked_at'] else 'Sent'
        statuses[row['coach_id']] = {
            'setup_status': status,
            'setup_sent_label': label(row['last_sent_at']),
            'setup_completed_label': label(row['last_completed_at']),
            'setup_expires_label': label(row['expires_at']) if status == 'Sent' else '',
        }
    return statuses


def valid_csrf(name):
    expected = session.get(name, '')
    return bool(expected) and secrets.compare_digest(expected, request.form.get('csrf_token', ''))


@coach_setup.after_request
def protect_setup_responses(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Robots-Tag'] = 'noindex, nofollow'
    return response


@coach_setup.route('/admin/coaches/setup-sms/verify', methods=['GET'])
@login_required
def verify_setup_sms():
    if not current_user.is_admin:
        return jsonify(error='Admin access required.'), 403

    base = current_app.config.get('COACH_AUTH_BASE_URL', '').rstrip('/')
    parsed = urlparse(base)
    sending_enabled = bool(
        current_app.config.get('COACH_AUTH_SMS_ENABLED')
        and parsed.scheme == 'https' and parsed.netloc
        and not parsed.query and not parsed.fragment
    )
    try:
        metadata = verify_setup_sender(current_app.config['COACH_AUTH_FROM_NUMBER'])
    except SetupDeliveryError as error:
        return jsonify(
            verified=False, sending_enabled=sending_enabled, error=str(error),
        ), 503
    except Exception:
        return jsonify(
            verified=False, sending_enabled=sending_enabled,
            error='SMS connection verification could not be completed. Do not send until verification succeeds.',
        ), 503

    return jsonify({
        **metadata, 'verified': True, 'sending_enabled': sending_enabled,
        'same_sender_as_reminders': (
            current_app.config['COACH_AUTH_FROM_NUMBER']
            == current_app.config['TWILIO_FROM_NUMBER']
        ),
    })


@coach_setup.route('/admin/coaches/<int:coach_id>/setup-sms', methods=['POST'])
@login_required
def send_setup(coach_id):
    if not current_user.is_admin or not valid_csrf('coach_admin_csrf'):
        return 'Unauthorised request', 403
    base = current_app.config.get('COACH_AUTH_BASE_URL', '').rstrip('/')
    parsed = urlparse(base)
    if (not current_app.config.get('COACH_AUTH_SMS_ENABLED') or parsed.scheme != 'https'
            or not parsed.netloc or parsed.query or parsed.fragment):
        flash('Setup SMS is disabled until the published URL and Twilio sender are verified.', 'error')
        return redirect(url_for('admin_coaches'))

    db = get_db()
    try:
        coach = db.execute('SELECT * FROM coaches WHERE id = %s FOR UPDATE', (coach_id,)).fetchone()
        if not coach or coach['is_admin']:
            return 'Admin accounts are not part of coach setup', 403
        mobile = normalize_setup_mobile(coach['mobile'])
        if not mobile:
            flash('Add a valid Australian or international mobile number before sending setup SMS.', 'error')
            return redirect(url_for('admin_coaches'))
        recent = db.execute('''
            SELECT 1 FROM public.coach_password_setups WHERE coach_id = %s
            AND delivery_status IN ('pending', 'sent') AND created_at > NOW() - INTERVAL '1 minute'
        ''', (coach_id,)).fetchone()
        if recent:
            flash('A setup link was just sent. Wait one minute before resending.', 'error')
            return redirect(url_for('admin_coaches'))

        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        setup = db.execute('''
            INSERT INTO public.coach_password_setups (coach_id, requested_by, token_hash, expires_at)
            VALUES (%s, %s, %s, NOW() + INTERVAL '24 hours') RETURNING id
        ''', (coach_id, current_user.id, token_hash)).fetchone()
        link = f"{base}/coach/password-setup#token={token}"
        message = (
            f"Power2ADAPT Coach Hub: Your username is {coach['username']}. "
            f"Choose your own password: {link} "
            "This one-use link expires in 24 hours. If unexpected, contact Coach Al."
        )
        try:
            send_setup_sms(
                mobile, message, current_app.config['COACH_AUTH_FROM_NUMBER'],
                current_app.config.get('COACH_AUTH_TWILIO_ACCOUNT_SID') or None,
            )
        except SetupDeliveryError as error:
            db.execute("UPDATE public.coach_password_setups SET delivery_status = 'failed' WHERE id = %s", (setup['id'],))
            db.commit()
            flash(str(error), 'error')
            return redirect(url_for('admin_coaches'))

        revoke_setup_links(db, coach_id, setup['id'])
        db.execute('''
            UPDATE public.coach_password_setups SET delivery_status = 'sent', sent_at = NOW()
            WHERE id = %s
        ''', (setup['id'],))
        # Never store the private link or chosen password in the general SMS log.
        db.execute('''
            INSERT INTO sms_log (coach_id, mobile, message, type, status)
            VALUES (%s, %s, %s, 'password_setup', 'sent')
        ''', (coach_id, mobile, 'Individual password setup SMS accepted by Twilio; private link omitted.'))
        db.commit()
        flash(f"Setup SMS accepted by Twilio for {coach['name']}. Their current password is unchanged until setup is completed.", 'success')
        return redirect(url_for('admin_coaches'))
    finally:
        db.close()


@coach_setup.route('/coach/password-setup', methods=['GET'])
def setup_form():
    session.setdefault('coach_setup_csrf', secrets.token_urlsafe(32))
    return render_template('coach_password_setup.html')


@coach_setup.route('/coach/password-setup', methods=['POST'])
def complete_setup():
    if not valid_csrf('coach_setup_csrf'):
        return render_template('coach_password_setup.html', error='Please reopen the link from your SMS and try again.'), 403
    token = request.form.get('token', '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
        return render_template('coach_password_setup.html', error='This link is invalid. Ask Coach Al for a new setup SMS.'), 400
    password = request.form.get('new_password', '')
    confirmation = request.form.get('confirm_password', '')
    if not 12 <= len(password) <= 128 or password != confirmation:
        return render_template(
            'coach_password_setup.html', token=token,
            error='Use 12–128 characters and enter the same new password in both fields.',
        ), 400

    token_hash = hashlib.sha256(token.encode()).hexdigest()
    db = get_db()
    try:
        found = db.execute('SELECT coach_id FROM public.coach_password_setups WHERE token_hash = %s', (token_hash,)).fetchone()
        coach = db.execute('SELECT * FROM coaches WHERE id = %s FOR UPDATE', (found['coach_id'],)).fetchone() if found else None
        setup = db.execute('''
            SELECT id FROM public.coach_password_setups WHERE token_hash = %s
            AND delivery_status = 'sent' AND completed_at IS NULL AND revoked_at IS NULL
            AND expires_at > NOW() FOR UPDATE
        ''', (token_hash,)).fetchone() if coach and not coach['is_admin'] else None
        if not setup:
            return render_template('coach_password_setup.html', error='This link has expired, was replaced, or has already been used. Ask Coach Al for a new setup SMS.'), 400
        if coach['password_hash'] and check_password_hash(coach['password_hash'], password):
            return render_template(
                'coach_password_setup.html', token=token,
                error='Choose a password different from your current one.',
            ), 400

        db.execute('''
            UPDATE coaches SET password_hash = %s WHERE id = %s
        ''', (generate_password_hash(password), coach['id']))
        bump_auth_version(db, coach['id'])
        db.execute('UPDATE public.coach_password_setups SET completed_at = NOW() WHERE id = %s', (setup['id'],))
        revoke_setup_links(db, coach['id'], setup['id'])
        db.commit()
        session.pop('coach_setup_csrf', None)
        if current_user.is_authenticated and int(current_user.id) == coach['id']:
            logout_user()
        return render_template('coach_password_setup.html', completed=True, coach=coach)
    finally:
        db.close()