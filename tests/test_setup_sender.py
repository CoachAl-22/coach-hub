import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from config import Config
from services.coach_setup_sms import SetupDeliveryError, send_setup_sms, verify_setup_sender


class SetupSenderTests(unittest.TestCase):
    def setUp(self):
        self.sid = patch.object(Config, 'TWILIO_ACCOUNT_SID', 'test-account')
        self.token = patch.object(Config, 'TWILIO_AUTH_TOKEN', 'test-only-token')
        self.sid.start()
        self.token.start()
        self.addCleanup(self.sid.stop)
        self.addCleanup(self.token.stop)

    def test_verification_is_read_only_and_redacts_account_payload(self):
        client = MagicMock()
        client.api.accounts.return_value.fetch.return_value = SimpleNamespace(
            status='active', type='Full', auth_token='must-never-be-returned',
        )
        client.incoming_phone_numbers.list.return_value = [SimpleNamespace(capabilities={'SMS': True})]
        with patch('twilio.rest.Client', return_value=client):
            result = verify_setup_sender('+15551234567')
        self.assertEqual(result, {
            'verified': True, 'backend': 'saved_secrets',
            'account_type': 'Full', 'sender_sms_capable': True,
        })
        client.api.accounts.assert_called_once_with('test-account')
        client.api.accounts.return_value.fetch.assert_called_once_with()
        client.incoming_phone_numbers.list.assert_called_once_with(
            phone_number='+15551234567', limit=1,
        )
        client.messages.create.assert_not_called()

    def test_authentication_failure_is_safe(self):
        client = MagicMock()
        error = Exception('sensitive provider response')
        error.status = 401
        client.api.accounts.return_value.fetch.side_effect = error
        with patch('twilio.rest.Client', return_value=client):
            with self.assertRaisesRegex(SetupDeliveryError, 'rejected the saved credentials') as result:
                verify_setup_sender('+15551234567')
        self.assertNotIn('sensitive', str(result.exception))
        client.messages.create.assert_not_called()

    def test_non_sms_sender_keeps_sending_disabled(self):
        client = MagicMock()
        client.api.accounts.return_value.fetch.return_value = SimpleNamespace(status='active', type='Full')
        client.incoming_phone_numbers.list.return_value = [SimpleNamespace(capabilities={'sms': False})]
        with patch('twilio.rest.Client', return_value=client):
            with self.assertRaisesRegex(SetupDeliveryError, 'not SMS-capable'):
                verify_setup_sender('+15551234567')
        client.messages.create.assert_not_called()

    def send_error(self, error, *, sid='test-account', token='test-only-token'):
        with (
            patch.object(Config, 'TWILIO_ACCOUNT_SID', sid),
            patch.object(Config, 'TWILIO_AUTH_TOKEN', token),
            patch('twilio.rest.Client') as client_class,
            patch('twilio.http.http_client.TwilioHttpClient'),
        ):
            client_class.return_value.messages.create.side_effect = error
            with self.assertRaises(SetupDeliveryError) as raised:
                send_setup_sms(
                    '+15551234567', 'private setup link https://private.invalid/token',
                    '+15557654321',
                )
        return raised.exception

    def test_known_twilio_codes_have_specific_actionable_messages(self):
        expected = {
            20003: 'rejected the saved credentials',
            21211: 'recipient number',
            21408: 'geographic permissions',
            21606: 'SMS-capable number',
            21608: 'trial account',
            21610: 'opted out',
            21612: 'does not support',
            21614: 'not a mobile number',
            21660: 'does not belong',
            20429: 'rate limiting',
        }
        for code, message_part in expected.items():
            with self.subTest(code=code):
                error = Exception('sensitive provider body')
                error.status = 400
                error.code = code
                result = self.send_error(error)
                self.assertIn(message_part, str(result))
                self.assertEqual(result.provider_status, 400)
                self.assertEqual(result.provider_code, code)
                self.assertNotIn('sensitive provider body', str(result))

    def test_unknown_numeric_code_is_safe_and_retained(self):
        error = Exception('private response text')
        error.status = 400
        error.code = 987654
        result = self.send_error(error)
        self.assertIn('provider error code 987654', str(result))
        self.assertEqual(result.provider_code, 987654)
        self.assertNotIn('private response text', str(result))

    def test_invalid_provider_metadata_is_not_echoed(self):
        error = Exception('secret exception text')
        error.status = '401 secret-status'
        error.code = '+15551234567'
        with self.assertLogs('services.coach_setup_sms', level='WARNING') as captured:
            result = self.send_error(error)
        self.assertIn('could not confirm SMS delivery', str(result))
        self.assertIsNone(result.provider_status)
        self.assertIsNone(result.provider_code)
        for private_value in ('secret-status', '+15551234567', 'secret exception text'):
            self.assertNotIn(private_value, str(result))
            self.assertNotIn(private_value, '\n'.join(captured.output))

    def test_logs_and_messages_redact_exception_details(self):
        sensitive = (
            'token=test-only-token to=+15551234567 '
            'https://private.invalid/token response body must-not-leak'
        )
        error = TimeoutError(sensitive)
        with self.assertLogs('services.coach_setup_sms', level='WARNING') as captured:
            result = self.send_error(error)
        logs = '\n'.join(captured.output)
        self.assertIn('category=unconfirmed', logs)
        for private_value in (
            'test-only-token', '+15551234567', 'private.invalid', 'must-not-leak',
        ):
            self.assertNotIn(private_value, logs)
            self.assertNotIn(private_value, str(result))
        self.assertIn('could not confirm SMS delivery', str(result))
        self.assertIn('no automatic retry', str(result))

    def test_import_error_is_reported_as_sdk_unavailable(self):
        with (
            patch.object(Config, 'TWILIO_ACCOUNT_SID', 'test-account'),
            patch.object(Config, 'TWILIO_AUTH_TOKEN', 'test-only-token'),
            patch('twilio.rest.Client', side_effect=ImportError('private import detail')),
            patch('twilio.http.http_client.TwilioHttpClient'),
        ):
            with self.assertRaises(SetupDeliveryError) as raised:
                send_setup_sms('+15551234567', 'private message', '+15557654321')
        self.assertIn('SDK is unavailable', str(raised.exception))
        self.assertNotIn('rejected the saved credentials', str(raised.exception))
        self.assertNotIn('private import detail', str(raised.exception))

    def test_partial_credentials_fail_explicitly_without_connector_fallback(self):
        with (
            patch.object(Config, 'TWILIO_ACCOUNT_SID', ''),
            patch.object(Config, 'TWILIO_AUTH_TOKEN', 'test-only-token'),
            patch('services.coach_setup_sms.subprocess.run') as connector,
        ):
            with self.assertRaisesRegex(SetupDeliveryError, 'Both TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN'):
                send_setup_sms('+15551234567', 'private message', '+15557654321')
        connector.assert_not_called()

    def test_verification_provider_code_has_actionable_message_and_never_sends(self):
        client = MagicMock()
        error = Exception('sensitive provider response')
        error.status = 400
        error.code = 21606
        client.api.accounts.return_value.fetch.side_effect = error
        with patch('twilio.rest.Client', return_value=client):
            with self.assertRaises(SetupDeliveryError) as raised:
                verify_setup_sender('+15551234567')
        self.assertIn('SMS-capable number', str(raised.exception))
        self.assertIn('Do not send until verification succeeds', str(raised.exception))
        self.assertEqual(raised.exception.provider_code, 21606)
        self.assertNotIn('sensitive provider response', str(raised.exception))
        client.incoming_phone_numbers.list.assert_not_called()
        client.messages.create.assert_not_called()