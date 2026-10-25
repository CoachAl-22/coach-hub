"""Opt-in PostgreSQL integration checks for coach password setup and stale sessions.

Run only against the development database with:
    RUN_AUTH_PG_TESTS=1 python -m unittest tests.test_coach_setup_pg

Every test creates its own temporary schema and drops it during cleanup. SMS
delivery is mocked throughout; no existing coach records or provider are used.
"""

import hashlib
import os
import re
import threading
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from unittest.mock import patch

import psycopg2
import psycopg2.extras
import psycopg2.sql
from werkzeug.security import check_password_hash, generate_password_hash

import database
import main
from services import coach_password_setup
from services.coach_setup_sms import SetupDeliveryError


@unittest.skipUnless(
    os.environ.get('RUN_AUTH_PG_TESTS') == '1',
    'Set RUN_AUTH_PG_TESTS=1 to run isolated development PostgreSQL checks.',
)
class CoachSetupPostgreSQLTests(unittest.TestCase):
    def setUp(self):
        self.schema = 'coach_setup_pg_' + uuid.uuid4().hex
        self.schema_created = False
        self.patchers = []
        self.config_before = {
            key: main.app.config.get(key)
            for key in (
                'TESTING', 'COACH_AUTH_BASE_URL', 'COACH_AUTH_FROM_NUMBER',
                'COACH_AUTH_TWILIO_ACCOUNT_SID', 'COACH_AUTH_SMS_ENABLED',
            )
        }
        try:
            self._assert_development_database()
            self._create_schema()
            main.app.config.update(
                TESTING=True,
                COACH_AUTH_BASE_URL='https://published.example',
                COACH_AUTH_FROM_NUMBER='+61400000000',
                COACH_AUTH_TWILIO_ACCOUNT_SID='',
                COACH_AUTH_SMS_ENABLED=True,
            )
            self.lock_select_enabled = False
            self.lock_query_reached = threading.Event()
            self.allow_lock_query = threading.Event()
            self.login_snapshot_queries = []
            self.main_db_patcher = patch.object(main, 'get_db', side_effect=self.get_scoped_db)
            self.setup_db_patcher = patch.object(
                coach_password_setup, 'get_db', side_effect=self.get_scoped_db,
            )
            self.main_db_patcher.start()
            self.setup_db_patcher.start()
            self.patchers.extend((self.main_db_patcher, self.setup_db_patcher))
            self.client = main.app.test_client()
            self._insert_test_coaches()
        except BaseException:
            self._cleanup()
            raise

    def tearDown(self):
        self._cleanup()

    def _assert_development_database(self):
        if not os.environ.get('REPLIT_DEV_DOMAIN', '').endswith('.replit.dev'):
            raise RuntimeError('Refusing PostgreSQL tests outside a Replit development preview.')
        if os.environ.get('REPLIT_DEPLOYMENT'):
            raise RuntimeError('Refusing PostgreSQL tests in a deployment.')
        if not all(os.environ.get(key) for key in ('PGHOST', 'PGDATABASE', 'PGUSER')):
            raise RuntimeError('Refusing PostgreSQL tests without explicit development PG* settings.')

        conn = psycopg2.connect(database.DATABASE_URL)
        try:
            with conn.cursor() as cursor:
                cursor.execute('SELECT current_database()')
                if cursor.fetchone()[0] != os.environ['PGDATABASE']:
                    raise RuntimeError('Refusing PostgreSQL tests: connected database differs from PGDATABASE.')
        finally:
            conn.close()

    def _create_schema(self):
        conn = psycopg2.connect(database.DATABASE_URL)
        conn.autocommit = True
        try:
            with conn.cursor() as cursor:
                schema_ident = psycopg2.sql.Identifier(self.schema)
                cursor.execute(
                    psycopg2.sql.SQL('CREATE SCHEMA {}').format(schema_ident)
                )
                self.schema_created = True
                cursor.execute(psycopg2.sql.SQL('''
                    CREATE TABLE {}.coaches (
                        id INTEGER PRIMARY KEY,
                        name TEXT NOT NULL,
                        username TEXT NOT NULL UNIQUE,
                        email TEXT,
                        mobile TEXT,
                        role TEXT,
                        level TEXT,
                        is_admin INTEGER NOT NULL DEFAULT 0,
                        is_standby INTEGER NOT NULL DEFAULT 0,
                        is_active INTEGER NOT NULL DEFAULT 1,
                        password_hash TEXT
                    )
                ''').format(schema_ident))
                cursor.execute(psycopg2.sql.SQL('''
                    CREATE TABLE {}.coach_auth_state (
                        coach_id INTEGER PRIMARY KEY REFERENCES {}.coaches(id),
                        auth_version INTEGER NOT NULL DEFAULT 0
                    )
                ''').format(schema_ident, schema_ident))
                cursor.execute(psycopg2.sql.SQL('''
                    CREATE TABLE {}.login_attempts (
                        attempt_key TEXT PRIMARY KEY,
                        failures INTEGER NOT NULL DEFAULT 0,
                        window_started TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                ''').format(schema_ident))
                cursor.execute(psycopg2.sql.SQL('''
                    CREATE TABLE {}.coach_password_setups (
                        id BIGSERIAL PRIMARY KEY,
                        coach_id INTEGER NOT NULL REFERENCES {}.coaches(id),
                        requested_by INTEGER NOT NULL REFERENCES {}.coaches(id),
                        token_hash TEXT NOT NULL UNIQUE,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        expires_at TIMESTAMPTZ NOT NULL,
                        delivery_status TEXT NOT NULL DEFAULT 'pending'
                            CHECK (delivery_status IN ('pending', 'sent', 'failed')),
                        sent_at TIMESTAMPTZ,
                        completed_at TIMESTAMPTZ,
                        revoked_at TIMESTAMPTZ
                    )
                ''').format(schema_ident, schema_ident, schema_ident))
                cursor.execute(psycopg2.sql.SQL('''
                    CREATE INDEX coach_password_setups_coach_idx
                    ON {}.coach_password_setups (coach_id, created_at DESC)
                ''').format(schema_ident))
                cursor.execute(psycopg2.sql.SQL('''
                    CREATE TABLE {}.sms_log (
                        id SERIAL PRIMARY KEY,
                        coach_id INTEGER,
                        mobile TEXT,
                        message TEXT,
                        type TEXT,
                        status TEXT,
                        sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''').format(schema_ident))
        finally:
            conn.close()

    def _cleanup(self):
        try:
            for patcher in reversed(self.patchers):
                try:
                    patcher.stop()
                except RuntimeError:
                    pass
            self.patchers = []
        finally:
            try:
                if self.schema_created:
                    conn = psycopg2.connect(database.DATABASE_URL)
                    conn.autocommit = True
                    try:
                        with conn.cursor() as cursor:
                            cursor.execute(
                                psycopg2.sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(
                                    psycopg2.sql.Identifier(self.schema)
                                )
                            )
                    finally:
                        conn.close()
                    self.schema_created = False
            finally:
                for key, value in self.config_before.items():
                    if value is None:
                        main.app.config.pop(key, None)
                    else:
                        main.app.config[key] = value

    def get_scoped_db(self):
        return self.ScopedConnection(self)

    class ScopedConnection:
        def __init__(self, test_case):
            self.test_case = test_case
            self.connection = psycopg2.connect(
                database.DATABASE_URL,
                cursor_factory=psycopg2.extras.RealDictCursor,
                options=f'-c search_path={test_case.schema},pg_catalog',
            )

        def execute(self, sql, params=None):
            normalized = ' '.join(sql.split())
            if normalized.startswith(
                'SELECT c.*, COALESCE(a.auth_version, 0) AS auth_version'
            ):
                self.test_case.login_snapshot_queries.append(normalized)
            if (
                self.test_case.lock_select_enabled
                and threading.current_thread().name == 'self-password-change'
                and normalized.startswith(
                    'SELECT password_hash, is_active FROM coaches'
                )
                and normalized.endswith('FOR UPDATE')
            ):
                # The request's user loader has already cached state-table version 0.
                self.test_case.lock_query_reached.set()
                if not self.test_case.allow_lock_query.wait(timeout=30):
                    raise RuntimeError('Timed out waiting to resume locked password query.')
            cursor = self.connection.cursor()
            sql = sql.replace(
                'public.coach_auth_state',
                f'{self.test_case.schema}.coach_auth_state',
            ).replace(
                'public.coach_password_setups',
                f'{self.test_case.schema}.coach_password_setups',
            )
            cursor.execute(sql.replace('?', '%s'), params or ())
            return cursor

        def commit(self):
            self.connection.commit()

        def close(self):
            self.connection.close()

    def _insert_test_coaches(self):
        conn = self.get_scoped_db()
        try:
            conn.execute('''
                INSERT INTO coaches
                    (id, name, username, email, mobile, role, level, is_admin,
                     is_standby, is_active, password_hash)
                VALUES
                    (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s),
                    (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s),
                    (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s),
                    (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (
                1, 'Isolated Test Admin', 'pg-test-admin', 'admin@example.test',
                '+61411111111', 'Admin', 'Level 1', 1, 0, 1,
                generate_password_hash('pg-admin-password'),
                2, 'Isolated Active Coach', 'pg-test-active', 'active@example.test',
                '+61422222222', 'Coach', 'Level 1', 0, 0, 1,
                generate_password_hash('pg-old-active-password'),
                3, 'Isolated Inactive Coach', 'pg-test-inactive', 'inactive@example.test',
                '+61433333333', 'Coach', 'Level 1', 0, 0, 0,
                generate_password_hash('pg-old-inactive-password'),
                4, 'Isolated Concurrent Coach', 'pg-test-concurrent',
                'concurrent@example.test', '+61444444444', 'Coach', 'Level 1',
                0, 0, 1, generate_password_hash('pg-old-concurrent-password'),
            ))
            conn.commit()
        finally:
            conn.close()

    def _query_one(self, sql, params=()):
        conn = self.get_scoped_db()
        try:
            return conn.execute(sql, params).fetchone()
        finally:
            conn.close()

    def test_login_uses_one_consistent_password_and_auth_version_snapshot(self):
        original_check = check_password_hash
        reset_hash = generate_password_hash('pg-login-concurrent-reset-password')

        def reset_after_login_snapshot(password_hash, password):
            verified = original_check(password_hash, password)
            reset = self.get_scoped_db()
            try:
                reset.execute(
                    'UPDATE coaches SET password_hash = %s WHERE id = %s',
                    (reset_hash, 2),
                )
                main.bump_auth_version(reset, 2)
                reset.commit()
            finally:
                reset.close()
            return verified

        with patch.object(
            main, 'check_password_hash',
            side_effect=reset_after_login_snapshot,
        ):
            response = self.client.post('/login', data={
                'username': 'pg-test-active',
                'password': 'pg-old-active-password',
            })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, '/dashboard')
        self.assertEqual(len(self.login_snapshot_queries), 1)
        self.assertIn('LEFT JOIN public.coach_auth_state', self.login_snapshot_queries[0])
        with self.client.session_transaction() as session:
            self.assertEqual(session['auth_version'], 0)

        rejected = self.client.get('/account/password')
        self.assertEqual(rejected.status_code, 302)
        self.assertEqual(urlsplit(rejected.location).path, '/login')
        with self.client.session_transaction() as session:
            self.assertEqual(session['auth_version'], 0)

        current = self._query_one(
            'SELECT password_hash FROM coaches WHERE id = %s', (2,),
        )
        current_version = self._query_one(
            'SELECT auth_version FROM coach_auth_state WHERE coach_id = %s', (2,),
        )
        self.assertTrue(check_password_hash(
            current['password_hash'], 'pg-login-concurrent-reset-password',
        ))
        self.assertEqual(current_version['auth_version'], 1)

    def _set_admin_session(self, client):
        with client.session_transaction() as session:
            session['_user_id'] = '1'
            session['_fresh'] = True
            session['auth_version'] = 0
            session['coach_admin_csrf'] = 'temporary-schema-admin-csrf'

    def _send_setup_link(self, coach_id, *, failure=None):
        self._set_admin_session(self.client)
        provider_patch = patch.object(
            coach_password_setup, 'send_setup_sms',
            side_effect=failure,
        )
        with provider_patch as sender:
            response = self.client.post(
                f'/admin/coaches/{coach_id}/setup-sms',
                data={'csrf_token': 'temporary-schema-admin-csrf'},
            )
        return response, sender

    def _extract_token(self, sender):
        message = sender.call_args.args[1]
        match = re.search(r'#token=([A-Za-z0-9_-]{43})', message)
        self.assertIsNotNone(match, 'mock SMS should contain a setup token')
        return match.group(1)

    def _setup_csrf(self, client):
        response = client.get('/coach/password-setup')
        self.assertEqual(response.status_code, 200)
        with client.session_transaction() as session:
            return session['coach_setup_csrf']

    def test_send_resend_inactive_reset_and_concurrent_one_use(self):
        # Send is mocked for every route call; all assertions read real PostgreSQL rows.
        initial_hash = self._query_one(
            'SELECT password_hash FROM coaches WHERE id = %s', (2,),
        )['password_hash']
        sent, sender = self._send_setup_link(2)
        self.assertEqual(sent.status_code, 302)
        sender.assert_called_once()
        old_token = self._extract_token(sender)
        old_hash = hashlib.sha256(old_token.encode()).hexdigest()
        old_setup = self._query_one(
            'SELECT * FROM coach_password_setups WHERE token_hash = %s', (old_hash,),
        )
        self.assertEqual(old_setup['requested_by'], 1)
        self.assertEqual(old_setup['coach_id'], 2)
        self.assertEqual(old_setup['delivery_status'], 'sent')
        self.assertGreater(old_setup['expires_at'], datetime.now(timezone.utc))
        self.assertTrue(check_password_hash(initial_hash, 'pg-old-active-password'))
        self.assertEqual(
            self._query_one('SELECT password_hash FROM coaches WHERE id = %s', (2,))['password_hash'],
            initial_hash,
        )
        log_message = self._query_one(
            'SELECT message FROM sms_log WHERE coach_id = %s', (2,),
        )['message']
        self.assertNotIn(old_token, log_message)
        self.assertNotIn('#token=', log_message)

        conn = self.get_scoped_db()
        try:
            conn.execute(
                "UPDATE coach_password_setups SET created_at = NOW() - INTERVAL '2 minutes' WHERE id = %s",
                (old_setup['id'],),
            )
            conn.commit()
        finally:
            conn.close()
        resent, resend_sender = self._send_setup_link(2)
        self.assertEqual(resent.status_code, 302)
        new_token = self._extract_token(resend_sender)
        new_hash = hashlib.sha256(new_token.encode()).hexdigest()
        new_setup = self._query_one(
            'SELECT * FROM coach_password_setups WHERE token_hash = %s', (new_hash,),
        )
        self.assertNotEqual(old_token, new_token)
        self.assertIsNotNone(self._query_one(
            'SELECT revoked_at FROM coach_password_setups WHERE id = %s',
            (old_setup['id'],),
        )['revoked_at'])
        self.assertIsNone(new_setup['revoked_at'])

        conn = self.get_scoped_db()
        try:
            conn.execute(
                "UPDATE coach_password_setups SET created_at = NOW() - INTERVAL '2 minutes' WHERE id = %s",
                (new_setup['id'],),
            )
            conn.commit()
        finally:
            conn.close()
        failed, _ = self._send_setup_link(
            2, failure=SetupDeliveryError('mocked provider failure'),
        )
        self.assertEqual(failed.status_code, 302)
        self.assertIsNone(self._query_one(
            'SELECT revoked_at FROM coach_password_setups WHERE id = %s',
            (new_setup['id'],),
        )['revoked_at'])
        self.assertEqual(self._query_one(
            "SELECT COUNT(*) AS count FROM coach_password_setups WHERE coach_id = %s AND delivery_status = 'failed'",
            (2,),
        )['count'], 1)

        inactive_send, inactive_sender = self._send_setup_link(3)
        self.assertEqual(inactive_send.status_code, 302)
        inactive_token = self._extract_token(inactive_sender)
        inactive_client = main.app.test_client()
        inactive_csrf = self._setup_csrf(inactive_client)
        inactive_reset = inactive_client.post('/coach/password-setup', data={
            'csrf_token': inactive_csrf,
            'token': inactive_token,
            'new_password': 'pg-new-inactive-password',
            'confirm_password': 'pg-new-inactive-password',
        })
        self.assertEqual(inactive_reset.status_code, 200)
        inactive_after = self._query_one(
            'SELECT is_active, password_hash FROM coaches WHERE id = %s',
            (3,),
        )
        inactive_version = self._query_one(
            'SELECT auth_version FROM coach_auth_state WHERE coach_id = %s',
            (3,),
        )
        self.assertEqual(inactive_after['is_active'], 0)
        self.assertEqual(inactive_version['auth_version'], 1)
        self.assertTrue(check_password_hash(
            inactive_after['password_hash'], 'pg-new-inactive-password',
        ))

        concurrent_send, concurrent_sender = self._send_setup_link(4)
        self.assertEqual(concurrent_send.status_code, 302)
        concurrent_token = self._extract_token(concurrent_sender)
        barrier = threading.Barrier(2)
        outcomes = []
        failures = []
        passwords = ('pg-concurrent-password-one', 'pg-concurrent-password-two')

        def complete_same_token(password):
            try:
                client = main.app.test_client()
                csrf = self._setup_csrf(client)
                barrier.wait(timeout=20)
                response = client.post('/coach/password-setup', data={
                    'csrf_token': csrf,
                    'token': concurrent_token,
                    'new_password': password,
                    'confirm_password': password,
                })
                outcomes.append(response.status_code)
            except BaseException:
                failures.append(True)

        threads = [
            threading.Thread(target=complete_same_token, args=(password,))
            for password in passwords
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertFalse(failures)
        self.assertEqual(sorted(outcomes), [200, 400])
        concurrent_after = self._query_one(
            'SELECT password_hash FROM coaches WHERE id = %s',
            (4,),
        )
        concurrent_version = self._query_one(
            'SELECT auth_version FROM coach_auth_state WHERE coach_id = %s',
            (4,),
        )
        self.assertEqual(concurrent_version['auth_version'], 1)
        self.assertEqual(sum(
            check_password_hash(concurrent_after['password_hash'], password)
            for password in passwords
        ), 1)
        self.assertEqual(self._query_one(
            'SELECT COUNT(*) AS count FROM coach_password_setups WHERE token_hash = %s AND completed_at IS NOT NULL',
            (hashlib.sha256(concurrent_token.encode()).hexdigest(),),
        )['count'], 1)

    def test_stale_self_change_cannot_overwrite_admin_reset(self):
        self.lock_select_enabled = True
        errors = []
        result = {}

        def self_change_request():
            try:
                client = main.app.test_client()
                with client.session_transaction() as session:
                    session['_user_id'] = '2'
                    session['_fresh'] = True
                    session['auth_version'] = 0
                    session['password_csrf'] = 'temporary-schema-self-csrf'
                response = client.post('/account/password', data={
                    'csrf_token': 'temporary-schema-self-csrf',
                    'current_password': 'pg-old-active-password',
                    'new_password': 'pg-self-requested-password',
                    'confirm_password': 'pg-self-requested-password',
                })
                result['status'] = response.status_code
                result['location'] = response.location
            except BaseException:
                errors.append(True)

        worker = threading.Thread(
            target=self_change_request,
            name='self-password-change',
        )
        worker.start()
        try:
            self.assertTrue(
                self.lock_query_reached.wait(timeout=20),
                'self-change should reach the locked SELECT after loading session version 0',
            )

            # Exercise the real admin edit route, committing state version 1 while
            # the self-change request waits before its SELECT ... FOR UPDATE.
            admin = main.app.test_client()
            self._set_admin_session(admin)
            admin_response = admin.post('/admin/coaches/2/edit', data={
                'csrf_token': 'temporary-schema-admin-csrf',
                'name': 'Isolated Active Coach',
                'email': 'active@example.test',
                'mobile': '+61422222222',
                'role': 'Coach',
                'level': 'Level 1',
                'new_password': 'pg-admin-reset-password',
            })
            self.assertEqual(admin_response.status_code, 302)
            self.allow_lock_query.set()

            worker.join(timeout=30)
            self.assertFalse(worker.is_alive())
            self.assertFalse(errors)
            self.assertEqual(result.get('status'), 302)
            self.assertEqual(result.get('location'), '/login')
            final = self._query_one(
                'SELECT password_hash FROM coaches WHERE id = %s',
                (2,),
            )
            final_version = self._query_one(
                'SELECT auth_version FROM coach_auth_state WHERE coach_id = %s',
                (2,),
            )
            self.assertEqual(final_version['auth_version'], 1)
            self.assertTrue(check_password_hash(
                final['password_hash'], 'pg-admin-reset-password',
            ))
            self.assertFalse(check_password_hash(
                final['password_hash'], 'pg-self-requested-password',
            ))
        finally:
            self.allow_lock_query.set()
            worker.join(timeout=30)


if __name__ == '__main__':
    unittest.main()