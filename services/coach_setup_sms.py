import json
import logging
import re
import subprocess
from pathlib import Path

from config import Config


logger = logging.getLogger(__name__)


class SetupDeliveryError(Exception):
    def __init__(self, message, *, provider_status=None, provider_code=None):
        super().__init__(message)
        # Safe, validated provider metadata for read-only admin diagnostics.
        self.provider_status = provider_status
        self.provider_code = provider_code


_PROVIDER_ERRORS = {
    20003: ('credentials', 'Twilio rejected the saved credentials. Check the account SID and auth token.'),
    21211: ('recipient', 'Twilio rejected the recipient number. Check that the mobile number is valid and correctly formatted.'),
    21408: ('destination_permission', 'Twilio is not permitted to send to this destination. Enable it in Twilio geographic permissions.'),
    21606: ('sender', 'Twilio rejected the sender. Check that it is a valid SMS-capable number on this account.'),
    21608: ('trial_recipient', 'This Twilio trial account can send only to verified recipient numbers. Verify the recipient in Twilio or upgrade the account.'),
    21610: ('recipient_opt_out', 'The recipient has opted out of SMS. Do not resend unless they opt back in.'),
    21612: ('unsupported_route', 'Twilio does not support this sender-to-recipient SMS route. Check the sender and destination configuration.'),
    21614: ('non_mobile_recipient', 'The recipient number is not a mobile number capable of receiving SMS. Check the number.'),
    21660: ('sender_account_mismatch', 'The sender does not belong to the configured Twilio account. Check the sender and account configuration.'),
    20429: ('rate_limit', 'Twilio is rate limiting requests. Wait and check delivery status before manually retrying.'),
}


def _numeric_attribute(error, name, *, minimum, maximum):
    """Return only bounded integer metadata, never arbitrary provider values."""
    try:
        value = getattr(error, name, None)
    except Exception:
        return None
    if type(value) is int:
        number = value
    elif isinstance(value, str) and re.fullmatch(r'[0-9]{1,9}', value):
        number = int(value)
    else:
        return None
    return number if minimum <= number <= maximum else None


def _log_safe_error(category, status=None, code=None):
    # Do not log exception details, credentials, recipient numbers or SMS links.
    logger.warning(
        'setup_sms_error category=%s status=%s code=%s',
        category, status if status is not None else '-', code if code is not None else '-',
    )


def _classified_provider_error(error, operation):
    status = _numeric_attribute(error, 'status', minimum=100, maximum=599)
    code = _numeric_attribute(error, 'code', minimum=0, maximum=999999999)
    if code in _PROVIDER_ERRORS:
        category, message = _PROVIDER_ERRORS[code]
    elif status in (401, 403):
        category, message = (
            'credentials',
            'Twilio rejected the saved credentials. Check the account SID and auth token.',
        )
    elif status == 429:
        category, message = (
            'rate_limit',
            'Twilio is rate limiting requests. Wait and check delivery status before manually retrying.',
        )
    elif code is not None:
        category = 'provider_error'
        message = f'Twilio returned provider error code {code}. Check Twilio configuration and delivery status.'
    else:
        category = 'unconfirmed'
        if operation == 'verify':
            message = 'Twilio verification could not be confirmed. Check connectivity and Twilio status.'
        else:
            message = 'Twilio could not confirm SMS delivery. Check delivery status before manually retrying; no automatic retry was attempted.'

    _log_safe_error(category, status, code)
    if operation == 'verify':
        message += ' Do not send until verification succeeds.'
    elif category != 'unconfirmed':
        message += ' The setup link was not activated.'
    return SetupDeliveryError(message, provider_status=status, provider_code=code)


def _sdk_unavailable_error(operation):
    _log_safe_error('sdk_unavailable')
    if operation == 'verify':
        return SetupDeliveryError(
            'The Twilio SDK is unavailable, so saved-secrets verification cannot run. Do not send until this is resolved.'
        )
    return SetupDeliveryError(
        'The Twilio SDK is unavailable, so the SMS was not sent. Configure the SDK before retrying.'
    )


def verify_setup_sender(from_number):
    """Read-only authentication/sender check. Never creates a message."""
    if not Config.TWILIO_ACCOUNT_SID or not Config.TWILIO_AUTH_TOKEN:
        raise SetupDeliveryError('Both saved Twilio credentials are required for this check.')
    try:
        from twilio.rest import Client
        from twilio.http.http_client import TwilioHttpClient
        client = Client(
            Config.TWILIO_ACCOUNT_SID, Config.TWILIO_AUTH_TOKEN,
            http_client=TwilioHttpClient(timeout=15),
        )
        account = client.api.accounts(Config.TWILIO_ACCOUNT_SID).fetch()
        if account.status != 'active':
            raise SetupDeliveryError('The Twilio account is not active. Do not send until this is resolved.')
        senders = client.incoming_phone_numbers.list(phone_number=from_number, limit=1)
        if not senders:
            raise SetupDeliveryError('The configured sender was not found on this Twilio account.')
        capabilities = senders[0].capabilities or {}
        if not (capabilities.get('sms') or capabilities.get('SMS')):
            raise SetupDeliveryError('The configured sender is not SMS-capable.')
        # Account responses can contain credentials: return only safe metadata.
        return {
            'verified': True, 'backend': 'saved_secrets',
            'account_type': account.type, 'sender_sms_capable': True,
        }
    except SetupDeliveryError:
        raise
    except ImportError:
        raise _sdk_unavailable_error('verify') from None
    except Exception as error:
        raise _classified_provider_error(error, 'verify') from None


def send_setup_sms(to_number, message, from_number, account_sid=None):
    # Prefer this project's existing saved credentials, without simulated sends.
    if Config.TWILIO_ACCOUNT_SID or Config.TWILIO_AUTH_TOKEN:
        if not Config.TWILIO_ACCOUNT_SID or not Config.TWILIO_AUTH_TOKEN:
            raise SetupDeliveryError('Both TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN must be configured.')
        try:
            from twilio.rest import Client
            from twilio.http.http_client import TwilioHttpClient
            client = Client(
                Config.TWILIO_ACCOUNT_SID, Config.TWILIO_AUTH_TOKEN,
                http_client=TwilioHttpClient(timeout=15),
            )
            accepted = client.messages.create(body=message, from_=from_number, to=to_number)
            if not accepted.sid or accepted.status in ('failed', 'undelivered'):
                raise SetupDeliveryError('Twilio did not accept the SMS. No setup link was activated.')
            return accepted.sid
        except SetupDeliveryError:
            raise
        except ImportError:
            raise _sdk_unavailable_error('send') from None
        except Exception as error:
            raise _classified_provider_error(error, 'send') from None
    bridge = Path(__file__).with_name('twilio_connector.mjs')
    try:
        result = subprocess.run(
            ['node', str(bridge)],
            input=json.dumps({
                'mode': 'send', 'to': to_number, 'message': message,
                'from': from_number, 'accountSid': account_sid,
            }),
            text=True, capture_output=True, timeout=25, check=False,
        )
        response = json.loads(result.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        raise SetupDeliveryError(
            'The Twilio connector is unavailable. No setup link was activated.'
        ) from None
    if result.returncode != 0 or not response.get('ok'):
        raise SetupDeliveryError(response.get('error') or 'SMS delivery could not be confirmed.')
    return response['sid']