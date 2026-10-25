import logging

logger = logging.getLogger(__name__)


def send_sms(account_sid, auth_token, from_number, to_number, message):
    """
    Send an SMS via Twilio. Returns True on success, False on failure.
    If credentials are not configured, logs to console (dev mode).
    """
    if not account_sid or not auth_token:
        logger.info('[DEV MODE] SMS to %s: %s', to_number, message)
        return True

    try:
        from twilio.rest import Client
        client = Client(account_sid, auth_token)
        msg = client.messages.create(
            body=message,
            from_=from_number,
            to=to_number
        )
        logger.info('SMS sent to %s: SID %s', to_number, msg.sid)
        return True
    except Exception as e:
        logger.error('SMS failed to %s: %s', to_number, e)
        return False
