import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'change-me-in-production')
    GOOGLE_CREDENTIALS_JSON = os.environ.get('GOOGLE_CREDENTIALS_JSON')
    GOOGLE_SHEET_ID = os.environ.get('GOOGLE_SHEET_ID', '1doaWgaT5kKoPWq1I9yQqcZbowAOqeKe0ymDezmnTMmA')
    TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
    TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
    TWILIO_FROM_NUMBER = os.environ.get('TWILIO_FROM_NUMBER', '+19786253879')
    APP_URL = os.environ.get('APP_URL', 'http://localhost:5000')
    TIMEZONE = 'Australia/Melbourne'
    DATABASE = 'coach_hub.db'
