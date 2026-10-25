import hashlib
import re
import secrets
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from werkzeug.security import check_password_hash, generate_password_hash

from config import Config
import main
from services import coach_password_setup, coach_setup_sms
from services.coach_setup_sms import SetupDeliveryError


class Result:
    def __init__(self, row=None, rows=None):
        self.row = row
        self.rows = rows or []

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class FakeDB:
    """Per-test database state for exercising setup routes without PostgreSQL."""

    def __init__(self):
        self.coaches = {
            42: {
                'id': 42, 'name': 'Test Coach', 'username': 'testcoach',
                'email': 'coach@example.test', 'mobile': '+61412345678',
                'role': 'Coach', 'level': 'Level 1', 'is_admin': 0,
                'is_standby': 0, 'is_active': 1, 'auth_version': 0,
                'password_hash': generate_password_hash('initial-password-123'),
            },
            7: {
                'id': 7, 'name': 'Test Admin', 'username': 'testadmin',
                'email': 'admin@example.test', 'mobile': '+61487654321',
                'role': 'Admin', 'level': 'Level 1', 'is_admin': 1,
                'is_standby': 0, 'is_active': 1, 'auth_version': 0,
                'password_hash': generate_password_hash('admin-password-123'),
            },
        }
        self.setup_links = []
        self.sms_log = []
        self.auth_versions = {}
        self.next_setup_id = 1
        self.closed = False
        self.executed_queries = []

    def execute(self, sql, args=()):
        self.executed_queries.append(' '.join(sql.split()))
        normalized = ' '.join(sql.split())
        local_normalized = normalized.replace('public.', '')
        now = datetime.now(timezone.utc)

        if ('FROM coaches c LEFT JOIN public.coach_auth_state a' in normalized
                and 'WHERE c.username' in normalized):
            coach = next(
                (row for row in self.coaches.values()
                 if row['username'] == args[0] and row['is_active']),
                None,
            )
            if coach:
                coach = dict(coach)
                coach['auth_version'] = self.auth_versions.get(coach['id'], 0)
            return Result(coach)

        if 'SELECT * FROM coaches WHERE username' in normalized:
            coach = next(
                (row for row in self.coaches.values()
                 if row['username'] == args[0] and row['is_active']),
                None,
            )
            return Result(dict(coach) if coach else None)

        if 'SELECT * FROM coaches WHERE id' in normalized:
            coach = self.coaches.get(int(args[0]))
            return Result(dict(coach) if coach else None)

        if 'SELECT password_hash FROM coaches WHERE id' in normalized:
            coach = self.coaches.get(int(args[0]))
            return Result({'password_hash': coach['password_hash']} if coach else None)

        if 'SELECT password_hash, is_active FROM coaches WHERE id' in normalized:
            coach = self.coaches.get(int(args[0]))
            return Result({
                'password_hash': coach['password_hash'],
                'is_active': coach['is_active'],
            } if coach else None)

        if 'SELECT auth_version FROM public.coach_auth_state WHERE coach_id' in normalized:
            version = self.auth_versions.get(int(args[0]))
            return Result({'auth_version': version} if version is not None else None)

        if normalized.startswith('INSERT INTO public.coach_auth_state'):
            coach_id = int(args[0])
            version = self.auth_versions.get(coach_id, 0) + 1
            self.auth_versions[coach_id] = version
            coach = self.coaches.get(coach_id)
            if coach:
                coach['auth_version'] = version
            return Result({'auth_version': version})

        if local_normalized.startswith('SELECT 1 FROM coach_password_setups'):
            coach_id = int(args[0])
            recent = any(
                link['coach_id'] == coach_id
                and link['delivery_status'] in ('pending', 'sent')
                and link['created_at'] > now - timedelta(minutes=1)
                for link in self.setup_links
            )
            return Result({'?column?': 1} if recent else None)

        if local_normalized.startswith('INSERT INTO coach_password_setups'):
            coach_id, requested_by, token_hash = args
            setup_id = self.next_setup_id
            self.next_setup_id += 1
            self.setup_links.append({
                'id': setup_id,
                'coach_id': int(coach_id),
                'requested_by': int(requested_by),
                'token_hash': token_hash,
                'delivery_status': 'pending',
                'created_at': now,
                'sent_at': None,
                'expires_at': now + timedelta(hours=24),
                'completed_at': None,
                'revoked_at': None,
            })
            return Result({'id': setup_id})

        if local_normalized.startswith('SELECT coach_id FROM coach_password_setups'):
            link = next(
                (row for row in self.setup_links if row['token_hash'] == args[0]),
                None,
            )
            return Result({'coach_id': link['coach_id']} if link else None)

        if local_normalized.startswith('SELECT id FROM coach_password_setups WHERE token_hash'):
            link = next(
                (
                    row for row in self.setup_links
                    if row['token_hash'] == args[0]
                    and row['delivery_status'] == 'sent'
                    and row['completed_at'] is None
                    and row['revoked_at'] is None
                    and row['expires_at'] > now
                ),
                None,
            )
            return Result({'id': link['id']} if link else None)

        if local_normalized.startswith("UPDATE coach_password_setups SET delivery_status = 'failed'"):
            setup_id = int(args[0])
            for link in self.setup_links:
                if link['id'] == setup_id:
                    link['delivery_status'] = 'failed'
            return Result()

        if local_normalized.startswith('UPDATE coach_password_setups SET revoked_at = NOW()'):
            coach_id, except_id = args
            for link in self.setup_links:
                if (link['coach_id'] == int(coach_id)
                        and link['completed_at'] is None
                        and link['revoked_at'] is None
                        and link['id'] != except_id):
                    link['revoked_at'] = now
            return Result()

        if local_normalized.startswith("UPDATE coach_password_setups SET delivery_status = 'sent'"):
            setup_id = int(args[0])
            for link in self.setup_links:
                if link['id'] == setup_id:
                    link['delivery_status'] = 'sent'
                    link['sent_at'] = now
            return Result()

        if normalized.startswith('INSERT INTO sms_log'):
            self.sms_log.append({
                'coach_id': int(args[0]),
                'mobile': args[1],
                'message': args[2],
                'type': 'password_setup',
                'status': 'sent',
            })
            return Result()

        if normalized.startswith('UPDATE coaches SET password_hash'):
            coach = self.coaches.get(int(args[1]))
            if coach:
                coach['password_hash'] = args[0]
            return Result()

        if normalized.startswith('UPDATE coaches SET name='):
            coach = self.coaches.get(int(args[-1]))
            if coach:
                coach.update({
                    'name': args[0], 'email': args[1], 'mobile': args[2],
                    'role': args[3], 'level': args[4], 'is_standby': args[5],
                })
                if len(args) == 8:
                    coach['password_hash'] = args[6]
            return Result()

        if local_normalized.startswith('UPDATE coach_password_setups SET completed_at = NOW()'):
            setup_id = int(args[0])
            for link in self.setup_links:
                if link['id'] == setup_id:
                    link['completed_at'] = now
            return Result()

        return Result()

    def commit(self):
        pass

    def close(self):
        self.closed = True


class CoachPasswordSetupTests(unittest.TestCase):
    def test_australian_mobile_is_normalized_without_accepting_invalid_numbers(self):
        normalize = coach_password_setup.normalize_setup_mobile
        self.assertEqual(normalize('0400 123 456'), '+61400123456')
        self.assertEqual(normalize('+61 400-123-456'), '+61400123456')
        self.assertIsNone(normalize('not-a-phone'))

    def test_migration_uses_public_auth_state_without_coaches_auth_version_column(self):
        migration = (
            Path(__file__).resolve().parents[1]
            / 'migrations' / 'coach_password_setup.sql'
        ).read_text()
        self.assertRegex(
            migration,
            r'(?i)CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+public\.coach_auth_state\b',
        )
        self.assertRegex(
            migration,
            r'(?i)CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+public\.coach_password_setups\b',
        )
        self.assertNotRegex(
            migration,
            r'(?i)ALTER\s+TABLE\s+ch\.coaches\s+ADD\s+COLUMN'
            r'(?:\s+IF\s+NOT\s+EXISTS)?\s+auth_version\b',
        )

    def setUp(self):
        self.config_before = {
            key: main.app.config.get(key)
            for key in (
                'TESTING', 'COACH_AUTH_BASE_URL', 'COACH_AUTH_FROM_NUMBER',
                'COACH_AUTH_TWILIO_ACCOUNT_SID', 'COACH_AUTH_SMS_ENABLED',
            )
        }
        main.app.config.update(
            TESTING=True,
            COACH_AUTH_BASE_URL='https://published.example',
            COACH_AUTH_FROM_NUMBER='+61400000000',
            COACH_AUTH_TWILIO_ACCOUNT_SID='',
            COACH_AUTH_SMS_ENABLED=True,
        )
        self.addCleanup(self._restore_config)

        self.db = FakeDB()
        self.main_db_patcher = patch.object(main, 'get_db', return_value=self.db)
        self.setup_db_patcher = patch.object(coach_password_setup, 'get_db', return_value=self.db)
        self.main_db_patcher.start()
        self.setup_db_patcher.start()
        self.addCleanup(self.main_db_patcher.stop)
        self.addCleanup(self.setup_db_patcher.stop)
        self.client = main.app.test_client()

    def _restore_config(self):
        for key, value in self.config_before.items():
            if value is None:
                main.app.config.pop(key, None)
            else:
                main.app.config[key] = value

    def set_user(self, client, user_id, auth_version=0):
        with client.session_transaction() as session:
            session['_user_id'] = str(user_id)
            session['_fresh'] = True
            session['auth_version'] = auth_version

    def admin_csrf(self):
        with self.client.session_transaction() as session:
            session['coach_admin_csrf'] = 'test-admin-csrf'
        return 'test-admin-csrf'

    def issue_setup_sms(self, coach_id=42):
        self.set_user(self.client, 7)
        csrf = self.admin_csrf()
        with patch.object(coach_password_setup, 'send_setup_sms') as send_sms:
            response = self.client.post(
                f'/admin/coaches/{coach_id}/setup-sms',
                data={'csrf_token': csrf},
            )
        return response, send_sms

    def setup_token(self, send_sms):
        message = send_sms.call_args.args[1]
        match = re.search(r'#token=([A-Za-z0-9_-]{43})', message)
        self.assertIsNotNone(match)
        return match.group(1)

    def make_sent_link(self, *, expires_at=None, revoked_at=None):
        token = secrets.token_urlsafe(32)
        link = {
            'id': self.db.next_setup_id,
            'coach_id': 42,
            'requested_by': 7,
            'token_hash': hashlib.sha256(token.encode()).hexdigest(),
            'delivery_status': 'sent',
            'created_at': datetime.now(timezone.utc) - timedelta(minutes=5),
            'sent_at': datetime.now(timezone.utc) - timedelta(minutes=5),
            'expires_at': expires_at or datetime.now(timezone.utc) + timedelta(hours=24),
            'completed_at': None,
            'revoked_at': revoked_at,
        }
        self.db.next_setup_id += 1
        self.db.setup_links.append(link)
        return token, link

    def setup_form_csrf(self):
        response = self.client.get('/coach/password-setup')
        self.assertEqual(response.status_code, 200)
        with self.client.session_transaction() as session:
            return session['coach_setup_csrf']

    def complete_setup(self, token, csrf, password='a-new-password-123', confirmation=None):
        return self.client.post('/coach/password-setup', data={
            'csrf_token': csrf,
            'token': token,
            'new_password': password,
            'confirm_password': password if confirmation is None else confirmation,
        })

    def test_admin_send_keeps_password_and_persists_only_token_hash_and_metadata(self):
        original_hash = self.db.coaches[42]['password_hash']
        response, send_sms = self.issue_setup_sms()

        self.assertEqual(response.status_code, 302)
        send_sms.assert_called_once()
        token = self.setup_token(send_sms)
        self.assertEqual(self.db.coaches[42]['password_hash'], original_hash)
        self.assertTrue(check_password_hash(original_hash, 'initial-password-123'))
        self.assertNotIn(42, self.db.auth_versions)
        self.assertEqual(len(self.db.setup_links), 1)
        link = self.db.setup_links[0]
        self.assertEqual(link['requested_by'], 7)
        self.assertEqual(link['coach_id'], 42)
        self.assertEqual(link['delivery_status'], 'sent')
        self.assertEqual(link['token_hash'], hashlib.sha256(token.encode()).hexdigest())
        self.assertNotIn(token, link['token_hash'])
        self.assertEqual(len(self.db.sms_log), 1)
        self.assertNotIn(token, self.db.sms_log[0]['message'])
        self.assertNotIn('#token=', self.db.sms_log[0]['message'])
        self.assertNotIn('/coach/password-setup', self.db.sms_log[0]['message'])
        self.assertEqual(self.db.sms_log[0]['type'], 'password_setup')
        self.assertIn(token, send_sms.call_args.args[1])

    def test_admin_read_only_sms_verification_success(self):
        self.set_user(self.client, 7)
        with (
            patch.object(
                coach_password_setup, 'verify_setup_sender',
                return_value={
                    'verified': True, 'backend': 'saved_secrets',
                    'account_type': 'Trial', 'sender_sms_capable': True,
                },
            ) as verify_sender,
            patch.object(coach_password_setup, 'send_setup_sms') as send_sms,
        ):
            response = self.client.get('/admin/coaches/setup-sms/verify')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {
            'verified': True, 'backend': 'saved_secrets',
            'account_type': 'Trial', 'sender_sms_capable': True,
            'sending_enabled': True,
            'same_sender_as_reminders': False,
        })
        verify_sender.assert_called_once_with('+61400000000')
        send_sms.assert_not_called()
        self.assertEqual(self.db.setup_links, [])
        self.assertFalse(any(
            'coach_password_setups' in query for query in self.db.executed_queries
        ))

    def test_admin_read_only_sms_verification_failure_is_safe_and_does_not_send(self):
        self.set_user(self.client, 7)
        safe_error = 'Twilio rejected the saved credentials. Sending remains disabled.'
        with (
            patch.object(
                coach_password_setup, 'verify_setup_sender',
                side_effect=SetupDeliveryError(safe_error),
            ) as verify_sender,
            patch.object(coach_password_setup, 'send_setup_sms') as send_sms,
        ):
            response = self.client.get('/admin/coaches/setup-sms/verify')

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json, {
            'verified': False, 'sending_enabled': True, 'error': safe_error,
        })
        verify_sender.assert_called_once_with('+61400000000')
        send_sms.assert_not_called()
        self.assertEqual(self.db.setup_links, [])
        self.assertEqual(self.db.sms_log, [])
        self.assertFalse(any(
            'coach_password_setups' in query for query in self.db.executed_queries
        ))

    def test_sms_verification_rejects_non_admin_and_redirects_anonymous_users(self):
        with patch.object(coach_password_setup, 'verify_setup_sender') as verify_sender:
            self.set_user(self.client, 42)
            non_admin = self.client.get('/admin/coaches/setup-sms/verify')
            anonymous = main.app.test_client().get('/admin/coaches/setup-sms/verify')

        self.assertEqual(non_admin.status_code, 403)
        self.assertEqual(anonymous.status_code, 302)
        self.assertIn('/login', anonymous.headers['Location'])
        verify_sender.assert_not_called()
        self.assertEqual(self.db.setup_links, [])

    def test_coaches_page_has_read_only_sms_connection_control(self):
        self.set_user(self.client, 7)
        response = self.client.get('/admin/coaches')

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Check SMS connection', response.data)
        self.assertIn(b'aria-live="polite"', response.data)
        self.assertIn(b'fetch(', response.data)
        self.assertIn(b'SMS delivery', response.data)

    def test_admin_target_and_invalid_csrf_are_rejected_without_sms(self):
        self.set_user(self.client, 7)
        with patch.object(coach_password_setup, 'send_setup_sms') as send_sms:
            invalid_csrf = self.client.post('/admin/coaches/42/setup-sms')
            admin_target = self.client.post(
                '/admin/coaches/7/setup-sms',
                data={'csrf_token': self.admin_csrf()},
            )
        self.assertEqual(invalid_csrf.status_code, 403)
        self.assertEqual(admin_target.status_code, 403)
        send_sms.assert_not_called()
        self.assertEqual(self.db.setup_links, [])

        token, _ = self.make_sent_link()
        original_hash = self.db.coaches[42]['password_hash']
        setup_csrf = self.setup_form_csrf()
        rejected = self.complete_setup(token, 'wrong-csrf-token')
        self.assertEqual(rejected.status_code, 403)
        self.assertEqual(self.db.coaches[42]['password_hash'], original_hash)

    def test_setup_sms_is_denied_when_feature_flag_is_disabled(self):
        self.set_user(self.client, 7)
        csrf = self.admin_csrf()
        main.app.config['COACH_AUTH_SMS_ENABLED'] = False
        with patch.object(coach_password_setup, 'send_setup_sms') as send_sms:
            response = self.client.post(
                '/admin/coaches/42/setup-sms',
                data={'csrf_token': csrf},
            )

        self.assertEqual(response.status_code, 302)
        send_sms.assert_not_called()
        self.assertEqual(self.db.setup_links, [])

    def test_inactive_coach_can_set_password_without_becoming_active(self):
        token, link = self.make_sent_link()
        self.db.coaches[42]['is_active'] = 0
        csrf = self.setup_form_csrf()

        response = self.complete_setup(token, csrf)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'account is inactive', response.data)
        self.assertTrue(check_password_hash(
            self.db.coaches[42]['password_hash'], 'a-new-password-123'
        ))
        self.assertEqual(self.db.coaches[42]['is_active'], 0)
        self.assertIsNotNone(link['completed_at'])

    def test_setup_tokens_are_one_use_expire_and_can_be_revoked(self):
        token, link = self.make_sent_link()
        csrf = self.setup_form_csrf()
        completed = self.complete_setup(token, csrf)
        self.assertEqual(completed.status_code, 200)
        self.assertIsNotNone(link['completed_at'])

        reused_csrf = self.setup_form_csrf()
        reused = self.complete_setup(token, reused_csrf)
        self.assertEqual(reused.status_code, 400)

        expired_token, _ = self.make_sent_link(
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
        expired_csrf = self.setup_form_csrf()
        expired = self.complete_setup(expired_token, expired_csrf)
        self.assertEqual(expired.status_code, 400)

        revoked_token, _ = self.make_sent_link(
            revoked_at=datetime.now(timezone.utc),
        )
        revoked_csrf = self.setup_form_csrf()
        revoked = self.complete_setup(revoked_token, revoked_csrf)
        self.assertEqual(revoked.status_code, 400)

    def test_resend_supersedes_old_token_but_failed_delivery_keeps_existing_link(self):
        first_response, first_send = self.issue_setup_sms()
        self.assertEqual(first_response.status_code, 302)
        first_token = self.setup_token(first_send)
        first_link = self.db.setup_links[0]
        first_link['created_at'] -= timedelta(minutes=2)

        second_response, second_send = self.issue_setup_sms()
        self.assertEqual(second_response.status_code, 302)
        second_token = self.setup_token(second_send)
        second_link = self.db.setup_links[1]
        self.assertNotEqual(first_token, second_token)
        self.assertIsNotNone(first_link['revoked_at'])
        self.assertIsNone(second_link['revoked_at'])

        second_link['created_at'] -= timedelta(minutes=2)
        self.set_user(self.client, 7)
        csrf = self.admin_csrf()
        with patch.object(
            coach_password_setup, 'send_setup_sms',
            side_effect=SetupDeliveryError('delivery unavailable'),
        ):
            failed_response = self.client.post(
                '/admin/coaches/42/setup-sms',
                data={'csrf_token': csrf},
            )

        self.assertEqual(failed_response.status_code, 302)
        self.assertIsNone(second_link['revoked_at'])
        self.assertEqual(self.db.setup_links[-1]['delivery_status'], 'failed')
        self.assertEqual(len(self.db.sms_log), 2)

    def test_password_minimum_and_confirmation_are_enforced(self):
        token, link = self.make_sent_link()
        original_hash = self.db.coaches[42]['password_hash']
        csrf = self.setup_form_csrf()

        too_short = self.complete_setup(token, csrf, password='short-pass')
        self.assertEqual(too_short.status_code, 400)
        mismatch = self.complete_setup(
            token, csrf, password='a-long-enough-password',
            confirmation='a-different-password',
        )
        self.assertEqual(mismatch.status_code, 400)
        self.assertEqual(self.db.coaches[42]['password_hash'], original_hash)
        self.assertIsNone(link['completed_at'])

        valid = self.complete_setup(token, csrf, password='exactly-12!!')
        self.assertEqual(valid.status_code, 200)
        self.assertTrue(check_password_hash(
            self.db.coaches[42]['password_hash'], 'exactly-12!!'
        ))
        self.assertEqual(self.db.auth_versions[42], 1)

    def test_setup_rejects_reusing_current_password(self):
        token, link = self.make_sent_link()
        original_hash = self.db.coaches[42]['password_hash']
        csrf = self.setup_form_csrf()

        response = self.complete_setup(
            token, csrf, password='initial-password-123',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.db.coaches[42]['password_hash'], original_hash)
        self.assertIsNone(link['completed_at'])

    def test_admin_mobile_change_revokes_active_setup_links(self):
        _, link = self.make_sent_link()
        self.set_user(self.client, 7)
        csrf = self.admin_csrf()

        response = self.client.post('/admin/coaches/42/edit', data={
            'csrf_token': csrf,
            'name': 'Test Coach',
            'email': 'coach@example.test',
            'mobile': '+61499999999',
            'role': 'Coach',
            'level': 'Level 1',
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.db.coaches[42]['mobile'], '+61499999999')
        self.assertIsNotNone(link['revoked_at'])

    def test_reset_invalidates_other_existing_sessions(self):
        token, _ = self.make_sent_link()
        stale_client = main.app.test_client()
        self.set_user(self.client, 42)
        self.set_user(stale_client, 42)
        csrf = self.setup_form_csrf()

        response = self.complete_setup(token, csrf)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.db.coaches[42]['auth_version'], 1)
        self.assertEqual(self.db.auth_versions[42], 1)
        self.assertEqual(stale_client.get('/account/password').status_code, 302)
        self.assertEqual(self.client.get('/account/password').status_code, 302)

    def test_saved_twilio_credentials_path_is_mocked_for_success_and_failure(self):
        message = 'mock setup message'
        with (
            patch.object(Config, 'TWILIO_ACCOUNT_SID', 'AC_saved_mock'),
            patch.object(Config, 'TWILIO_AUTH_TOKEN', 'saved_mock_auth'),
            patch('twilio.rest.Client') as client_class,
            patch('twilio.http.http_client.TwilioHttpClient') as http_client_class,
            patch.object(coach_setup_sms.subprocess, 'run') as connector,
        ):
            client_class.return_value.messages.create.return_value = SimpleNamespace(
                sid='SM_mock_accepted', status='queued',
            )
            result = coach_setup_sms.send_setup_sms(
                '+61412345678', message, '+61400000000', 'AC_request_config',
            )
            self.assertEqual(result, 'SM_mock_accepted')
            client_class.assert_called_once_with(
                'AC_saved_mock', 'saved_mock_auth',
                http_client=http_client_class.return_value,
            )
            client_class.return_value.messages.create.assert_called_once_with(
                body=message, from_='+61400000000', to='+61412345678',
            )
            connector.assert_not_called()

        with (
            patch.object(Config, 'TWILIO_ACCOUNT_SID', 'AC_saved_mock'),
            patch.object(Config, 'TWILIO_AUTH_TOKEN', 'saved_mock_auth'),
            patch('twilio.rest.Client') as client_class,
            patch('twilio.http.http_client.TwilioHttpClient'),
            patch.object(coach_setup_sms.subprocess, 'run') as connector,
        ):
            client_class.return_value.messages.create.return_value = SimpleNamespace(
                sid=None, status='failed',
            )
            with self.assertRaises(SetupDeliveryError):
                coach_setup_sms.send_setup_sms(
                    '+61412345678', message, '+61400000000', 'AC_request_config',
                )
            connector.assert_not_called()


if __name__ == '__main__':
    unittest.main()