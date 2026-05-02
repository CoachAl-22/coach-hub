def send_sms(account_sid, auth_token, from_number, to_number, message):
    """
    Send an SMS via Twilio. Returns True on success, False on failure.
    If credentials are not configured, prints to console (dev mode).
    """
    if not account_sid or not auth_token:
        print(f'[DEV MODE] SMS to {to_number}: {message}')
        return True

    try:
        from twilio.rest import Client
        client = Client(account_sid, auth_token)
        msg = client.messages.create(
            body=message,
            from_=from_number,
            to=to_number
        )
        print(f'SMS sent to {to_number}: SID {msg.sid}')
        return True
    except Exception as e:
        print(f'SMS failed to {to_number}: {e}')
        return False
