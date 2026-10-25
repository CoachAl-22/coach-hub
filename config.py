import os
import logging

_FALLBACK_SECRET = 'change-me-in-production'

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or os.environ.get('SESSION_SECRET', _FALLBACK_SECRET)
    GOOGLE_CREDENTIALS_JSON = os.environ.get('GOOGLE_CREDENTIALS_JSON')
    GOOGLE_SHEET_ID = os.environ.get('GOOGLE_SHEET_ID', '1doaWgaT5kKoPWq1I9yQqcZbowAOqeKe0ymDezmnTMmA')
    TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
    TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
    TWILIO_FROM_NUMBER = os.environ.get('TWILIO_FROM_NUMBER', '+19786253879')
    APP_URL = os.environ.get('APP_URL', 'http://localhost:5000')
    TIMEZONE = 'Australia/Melbourne'
    DATABASE = 'coach_hub.db'
    API_KEY = os.environ.get('API_KEY')
    # Set only for the published environment so preview cannot send unusable links.
    COACH_AUTH_BASE_URL = os.environ.get('COACH_AUTH_BASE_URL', '')
    COACH_AUTH_FROM_NUMBER = os.environ.get('COACH_AUTH_FROM_NUMBER', '+19786253879')
    COACH_AUTH_TWILIO_ACCOUNT_SID = os.environ.get('COACH_AUTH_TWILIO_ACCOUNT_SID', '')
    COACH_AUTH_SMS_ENABLED = os.environ.get('COACH_AUTH_SMS_ENABLED', '0') == '1'

    @classmethod
    def validate(cls):
        """Emit a loud warning if insecure defaults are in use outside of debug/dev."""
        debug = os.environ.get('FLASK_DEBUG', '0').strip().lower() in ('1', 'true', 'yes')
        if not debug and cls.SECRET_KEY == _FALLBACK_SECRET:
            logging.critical(
                'SECURITY: SECRET_KEY is using the insecure fallback value. '
                'Set the SECRET_KEY (or SESSION_SECRET) environment variable '
                'before running in production.'
            )
