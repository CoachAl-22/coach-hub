import json
import secrets
from datetime import datetime, timedelta, date

import pytz
from apscheduler.schedulers.background import BackgroundScheduler

AEST = pytz.timezone('Australia/Melbourne')


def start_scheduler(app):
    scheduler = BackgroundScheduler(timezone=AEST)

    # Friday 5pm: timesheet reminder
    scheduler.add_job(
        func=lambda: _send_timesheet_reminders(app),
        trigger='cron',
        day_of_week='fri',
        hour=17,
        minute=0,
        id='timesheet_reminder'
    )

    # Daily check: send availability requests 14 days before a term starts
    scheduler.add_job(
        func=lambda: _check_availability_requests(app),
        trigger='cron',
        hour=8,
        minute=0,
        id='availability_check'
    )

    try:
        scheduler.start()
        print('Scheduler started.')
    except Exception as e:
        print(f'Scheduler failed to start: {e}')


def _send_timesheet_reminders(app):
    from database import get_db
    from services.twilio_service import send_sms

    with app.app_context():
        db = get_db()
        coaches = db.execute(
            'SELECT * FROM coaches WHERE is_active = 1 AND mobile IS NOT NULL'
        ).fetchall()

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
                expires_str = expires.strftime('%Y-%m-%d %H:%M:%S')
                db.execute('''
                    INSERT INTO availability_tokens (coach_id, term_id, token, expires_at)
                    VALUES (?, ?, ?, ?)
                ''', (coach['id'], term['id'], token, expires_str))

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
                    VALUES (?, ?, ?, ?, ?)
                ''', (coach['id'], coach['mobile'], message, 'availability_request',
                      'sent' if result else 'failed'))

        db.commit()
        db.close()
