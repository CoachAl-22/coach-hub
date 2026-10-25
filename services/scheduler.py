import json
import secrets
import fcntl
import os
from datetime import datetime, timedelta, date

import pytz
from apscheduler.schedulers.background import BackgroundScheduler

AEST = pytz.timezone('Australia/Melbourne')
_LOCK_FILE = '/tmp/coachub_scheduler.lock'
TIMESHEET_ANCHOR_DATE = date(2026, 8, 21)
_scheduler_lock_fd = None
_scheduler = None


def start_scheduler(app):
    # Use an exclusive file lock so only one Gunicorn worker runs the scheduler.
    # The first worker to acquire the lock starts it; others skip silently.
    global _scheduler_lock_fd, _scheduler
    try:
        _scheduler_lock_fd = open(_LOCK_FILE, 'w')
        fcntl.flock(_scheduler_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print('Scheduler already running in another worker — skipping.')
        return

    _scheduler = BackgroundScheduler(timezone=AEST)

    # Fortnightly Friday 6pm: timesheet reminder
    # Fires every Friday at 6pm AEST; the function checks the DB to skip
    # non-pay Fridays (ensures restarts don't reset the 2-week countdown).
    _scheduler.add_job(
        func=lambda: _send_timesheet_reminders(app),
        trigger='cron',
        day_of_week='fri',
        hour=18,
        minute=0,
        id='timesheet_reminder'
    )

    # Friday 6pm: SKOOL Weekly Win / Coach Hi-Five reminder
    _scheduler.add_job(
        func=lambda: _send_skool_reminders(app),
        trigger='cron',
        day_of_week='fri',
        hour=18,
        minute=0,
        id='skool_reminder'
    )

    # Daily check: send availability requests 14 days before a term starts
    _scheduler.add_job(
        func=lambda: _check_availability_requests(app),
        trigger='cron',
        hour=8,
        minute=0,
        id='availability_check'
    )

    try:
        _scheduler.start()
        print('Scheduler started.')
    except Exception as e:
        print(f'Scheduler failed to start: {e}')


def _send_timesheet_reminders(app, force=False):
    from database import get_db
    from services.twilio_service import send_sms

    now = datetime.now(AEST).strftime('%Y-%m-%d %H:%M %Z')
    print(f'[Scheduler] Timesheet reminder job started at {now}')

    today = datetime.now(AEST).date()
    days_from_anchor = (today - TIMESHEET_ANCHOR_DATE).days
    if not force and (days_from_anchor < 0 or days_from_anchor % 14 != 0):
        print(
            f'[Scheduler] Timesheet reminder skipped — '
            f'{today.isoformat()} is not a scheduled fortnightly Friday'
        )
        return
    if force:
        print('[Scheduler] Manual timesheet reminder catch-up requested — proceeding')

    with app.app_context():
        db = get_db()
        coaches = db.execute(
            'SELECT * FROM coaches WHERE is_active = 1 AND mobile IS NOT NULL'
        ).fetchall()

        sent, failed = 0, 0
        for coach in coaches:
            message = (
                f"Hi {coach['name'].split()[0]}, friendly reminder to submit your timesheet "
                f"via Xero Me today. Thanks, Alistair"
            )
            result = send_sms(
                app.config['TWILIO_ACCOUNT_SID'],
                app.config['TWILIO_AUTH_TOKEN'],
                app.config['TWILIO_FROM_NUMBER'],
                coach['mobile'],
                message
            )
            status = 'sent' if result else 'failed'
            if result:
                sent += 1
            else:
                failed += 1
                print(f'[Scheduler] Timesheet SMS FAILED for {coach["name"]} ({coach["mobile"]})')
            db.execute('''
                INSERT INTO sms_log (coach_id, mobile, message, type, status)
                VALUES (%s, %s, %s, %s, %s)
            ''', (coach['id'], coach['mobile'], message, 'timesheet_reminder', status))

        db.commit()
        db.close()
        print(f'[Scheduler] Timesheet reminder complete — {sent} sent, {failed} failed')


def _send_skool_reminders(app):
    from database import get_db
    from services.twilio_service import send_sms

    with app.app_context():
        db = get_db()
        coaches = db.execute(
            'SELECT * FROM coaches WHERE is_active = 1 AND mobile IS NOT NULL'
        ).fetchall()

        for coach in coaches:
            message = (
                f"Hey {coach['name'].split()[0]} 👋 Weekly wins are up in Skool!\n\n"
                'Drop one athlete moment from your sessions this week. One line is plenty. '
                'Something like "one of my Emerging Athletes finally nailed his arm drive in the 30m sprints."\n\n'
                "Got a photo of the drill or setup? Even better (no faces unless the family's said yes).\n\n"
                "Takes 2 mins 👉 skool.com/power2adapt-speed-school-8929\n\n"
                "Cheers, Al"
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
            ''', (coach['id'], coach['mobile'], message, 'skool_reminder',
                  'sent' if result else 'failed'))

        db.commit()
        db.close()


def _check_availability_requests(app):
    from database import get_db
    from services.twilio_service import send_sms

    with app.app_context():
        db = get_db()
        today = date.today()
        target_date = (today + timedelta(days=14)).isoformat()

        # Find terms starting in exactly 14 days
        terms = db.execute(
            'SELECT * FROM terms WHERE start_date = ?', (target_date,)
        ).fetchall()

        for term in terms:
            coaches = db.execute(
                'SELECT * FROM coaches WHERE is_active = 1 AND is_standby = 0 AND mobile IS NOT NULL'
            ).fetchall()

            for coach in coaches:
                # Check if already sent for this term
                existing = db.execute(
                    'SELECT id FROM availability_tokens WHERE coach_id = ? AND term_id = ?',
                    (coach['id'], term['id'])
                ).fetchone()
                if existing:
                    continue

                token = secrets.token_urlsafe(24)
                expires = datetime.utcnow() + timedelta(days=14)
                db.execute('''
                    INSERT INTO availability_tokens (coach_id, term_id, token, expires_at)
                    VALUES (%s, %s, %s, %s)
                ''', (coach['id'], term['id'], token, expires.strftime('%Y-%m-%dT%H:%M:%S')))

                form_url = f"{app.config['APP_URL']}/availability/{token}"
                message = (
                    f"Hi {coach['name'].split()[0]}, Power2ADAPT {term['name']} starts soon! "
                    f"Please fill in your availability: {form_url} Thanks, Alistair"
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

        db.commit()
        db.close()
