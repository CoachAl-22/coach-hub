import unittest
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from unittest.mock import patch

from werkzeug.security import check_password_hash, generate_password_hash

import main


class Result:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakeDB:
    def __init__(self):
        self.coach = {
            'id': 42, 'name': 'Test Coach', 'username': 'testcoach',
            'is_admin': 0, 'is_standby': 0, 'is_active': 1,
            'auth_version': 0,
            'password_hash': generate_password_hash('initial-password-123'),
        }
        self.attempts = {}
        self.setup_links = []
        self.auth_versions = {}
        self.closed = False
        self.queries = []
        self.before_locked_select = None

    def execute(self, sql, args=()):
        normalized_sql = ' '.join(sql.split())
        self.queries.append(normalized_sql)
        if ('FROM coaches c LEFT JOIN public.coach_auth_state a' in normalized_sql
                and 'WHERE c.username' in normalized_sql):
            row = (
                self.coach if args[0] == self.coach['username']
                and self.coach['is_active'] else None
            )
            if row:
                row = dict(row)
                row['auth_version'] = self.auth_versions.get(row['id'], 0)
            return Result(row)
        if 'SELECT * FROM coaches WHERE username' in sql:
            return Result(self.coach if args[0] == self.coach['username'] and self.coach['is_active'] else None)
        if 'SELECT * FROM coaches WHERE id' in sql:
            return Result(self.coach if str(args[0]) == str(self.coach['id']) else None)
        if 'SELECT password_hash, is_active FROM coaches WHERE id' in normalized_sql:
            if self.before_locked_select:
                self.before_locked_select(self)
            return Result({
                'password_hash': self.coach['password_hash'],
                'is_active': self.coach['is_active'],
            })
        if 'SELECT auth_version FROM public.coach_auth_state WHERE coach_id' in normalized_sql:
            version = self.auth_versions.get(int(args[0]))
            return Result({'auth_version': version} if version is not None else None)
        if normalized_sql.startswith('INSERT INTO public.coach_auth_state'):
            coach_id = int(args[0])
            version = self.auth_versions.get(coach_id, 0) + 1
            self.auth_versions[coach_id] = version
            if coach_id == self.coach['id']:
                self.coach['auth_version'] = version
            return Result({'auth_version': version})
        if 'SELECT password_hash FROM coaches WHERE id' in sql:
            return Result({'password_hash': self.coach['password_hash']})
        if sql.startswith('DELETE FROM login_attempts'):
            if args:
                self.attempts.pop(args[0], None)
        if 'INSERT INTO login_attempts' in sql:
            entry = self.attempts.get(args[0])
            now = datetime.now(timezone.utc)
            if entry and now - entry['window_started'] < timedelta(minutes=15):
                entry['failures'] += 1
            else:
                self.attempts[args[0]] = {'failures': 1, 'window_started': now}
            return Result(self.attempts[args[0]])
        if sql.startswith('UPDATE coaches SET password_hash'):
            self.coach['password_hash'] = args[0]
        if normalized_sql.startswith('UPDATE public.coach_password_setups SET revoked_at = NOW()'):
            coach_id, except_id = args
            for link in self.setup_links:
                if (link['coach_id'] == coach_id and link['completed_at'] is None
                        and link['revoked_at'] is None and link['id'] != except_id):
                    link['revoked_at'] = datetime.now(timezone.utc)
        return Result(None)

    def commit(self):
        pass

    def close(self):
        self.closed = True


class AuthTests(unittest.TestCase):
    def setUp(self):
        main.app.config['TESTING'] = True
        self.db = FakeDB()
        self.patcher = patch.object(main, 'get_db', return_value=self.db)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.client = main.app.test_client()

    def test_failed_logins_are_limited_and_expire(self):
        for _ in range(5):
            response = self.client.post('/login', data={
                'username': 'testcoach', 'password': 'wrong',
            })
            self.assertEqual(response.status_code, 200)
        locked = self.client.post('/login', data={
            'username': 'testcoach', 'password': 'initial-password-123',
        })
        self.assertEqual(locked.status_code, 429)
        key = next(iter(self.db.attempts))
        self.db.attempts[key]['window_started'] -= timedelta(minutes=16)
        allowed = self.client.post('/login', data={
            'username': 'testcoach', 'password': 'initial-password-123',
        })
        self.assertEqual(allowed.status_code, 302)
        self.assertEqual(self.db.attempts, {})

    def test_login_keeps_the_version_snapshot_used_with_the_password_hash(self):
        original_check = check_password_hash
        reset_hash = generate_password_hash('concurrent-login-reset-password')

        def reset_after_snapshot(password_hash, password):
            verified = original_check(password_hash, password)
            self.db.coach['password_hash'] = reset_hash
            main.bump_auth_version(self.db, self.db.coach['id'])
            return verified

        with patch.object(main, 'check_password_hash', side_effect=reset_after_snapshot):
            response = self.client.post('/login', data={
                'username': 'testcoach',
                'password': 'initial-password-123',
            })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, '/dashboard')
        with self.client.session_transaction() as session:
            self.assertEqual(session['auth_version'], 0)
        login_queries = self.db.queries[:]
        self.assertEqual(sum(
            query.startswith(
                'SELECT c.*, COALESCE(a.auth_version, 0) AS auth_version '
                'FROM coaches c LEFT JOIN public.coach_auth_state a'
            )
            for query in login_queries
        ), 1)
        self.assertFalse(any(
            query.startswith('SELECT auth_version FROM public.coach_auth_state')
            for query in login_queries
        ))

        rejected = self.client.get('/account/password')
        self.assertEqual(rejected.status_code, 302)
        self.assertEqual(urlsplit(rejected.location).path, '/login')
        with self.client.session_transaction() as session:
            self.assertEqual(session['auth_version'], 0)
        self.assertEqual(self.db.auth_versions[42], 1)

    def test_coach_changes_own_password(self):
        with self.client.session_transaction() as session:
            session['_user_id'] = '42'
            session['_fresh'] = True
        page = self.client.get('/account/password')
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'Current password', page.data)
        with self.client.session_transaction() as session:
            token = session['password_csrf']
        invalid = self.client.post('/account/password', data={
            'csrf_token': token, 'current_password': 'incorrect',
            'new_password': 'replacement-password-123',
            'confirm_password': 'replacement-password-123',
        })
        self.assertEqual(invalid.status_code, 302)
        self.assertTrue(check_password_hash(
            self.db.coach['password_hash'], 'initial-password-123'
        ))
        self.assertNotIn(42, self.db.auth_versions)
        changed = self.client.post('/account/password', data={
            'csrf_token': token, 'current_password': 'initial-password-123',
            'new_password': 'replacement-password-123',
            'confirm_password': 'replacement-password-123',
        })
        self.assertEqual(changed.status_code, 302)
        self.assertTrue(check_password_hash(
            self.db.coach['password_hash'], 'replacement-password-123'
        ))
        self.assertEqual(self.db.auth_versions[42], 1)
        self.assertEqual(self.db.coach['auth_version'], 1)
        with self.client.session_transaction() as session:
            self.assertNotIn('password_csrf', session)

    def test_self_password_change_rejects_stale_auth_version_after_lock(self):
        with self.client.session_transaction() as session:
            session['_user_id'] = '42'
            session['_fresh'] = True
            session['auth_version'] = 0
        page = self.client.get('/account/password')
        self.assertEqual(page.status_code, 200)
        with self.client.session_transaction() as session:
            token = session['password_csrf']

        reset_hash = generate_password_hash('concurrent-admin-password')

        def concurrent_reset(db):
            db.coach['password_hash'] = reset_hash
            main.bump_auth_version(db, db.coach['id'])

        self.db.before_locked_select = concurrent_reset
        response = self.client.post('/account/password', data={
            'csrf_token': token,
            'current_password': 'initial-password-123',
            'new_password': 'self-change-password',
            'confirm_password': 'self-change-password',
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, '/login')
        self.assertTrue(check_password_hash(
            self.db.coach['password_hash'], 'concurrent-admin-password'
        ))
        self.assertEqual(self.db.coach['auth_version'], 1)
        self.assertEqual(self.db.auth_versions[42], 1)
        self.assertTrue(any(
            query.startswith('SELECT password_hash, is_active FROM coaches')
            and query.endswith('FOR UPDATE')
            for query in self.db.queries
        ))
        with self.client.session_transaction() as session:
            self.assertNotIn('_user_id', session)

    def test_deactivated_coach_cannot_reuse_session(self):
        with self.client.session_transaction() as session:
            session['_user_id'] = '42'
        self.db.coach['is_active'] = 0
        self.assertEqual(self.client.get('/account/password').status_code, 302)

    def test_unknown_usernames_share_one_limited_bucket(self):
        for index in range(6):
            response = self.client.post('/login', data={
                'username': f'not-a-coach-{index}', 'password': 'wrong',
            })
        self.assertEqual(response.status_code, 429)
        self.assertEqual(len(self.db.attempts), 1)

    def test_forwarded_client_isolation_ignores_spoofed_earlier_hops(self):
        for ip in ('198.51.100.10', '198.51.100.11'):
            response = self.client.post('/login', data={
                'username': 'testcoach', 'password': 'incorrect',
            }, headers={'X-Forwarded-For': f'203.0.113.99, {ip}'})
            self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.db.attempts), 2)
        # The last hop, not the spoofable earlier one, decides the bucket.
        for _ in range(4):
            self.client.post('/login', data={
                'username': 'testcoach', 'password': 'incorrect',
            }, headers={'X-Forwarded-For': '192.0.2.88, 198.51.100.10'})
        response = self.client.post('/login', data={
            'username': 'testcoach', 'password': 'incorrect',
        }, headers={'X-Forwarded-For': '192.0.2.99, 198.51.100.10'})
        self.assertEqual(response.status_code, 429)
        other_client = self.client.post('/login', data={
            'username': 'testcoach', 'password': 'initial-password-123',
        }, headers={'X-Forwarded-For': '192.0.2.99, 198.51.100.11'})
        self.assertEqual(other_client.status_code, 302)

    def test_admin_password_actions_require_form_token(self):
        self.db.coach['is_admin'] = 1
        with self.client.session_transaction() as session:
            session['_user_id'] = '42'
            session['_fresh'] = True
        data = {
            'name': 'Test Coach', 'role': 'Coach', 'level': 'Level 1',
            'new_password': 'new-password-123',
        }
        self.assertEqual(self.client.post('/admin/coaches/42/edit', data=data).status_code, 403)
        self.assertEqual(self.client.post('/admin/coaches/42/toggle').status_code, 403)
        self.assertEqual(self.client.post('/admin/coaches/add', data=data).status_code, 403)
        self.assertTrue(check_password_hash(
            self.db.coach['password_hash'], 'initial-password-123'
        ))


if __name__ == '__main__':
    unittest.main()