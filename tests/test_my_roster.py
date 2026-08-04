import os
import tempfile
import unittest
from datetime import date, timedelta

# Apple's bundled Python 3.9 does not expose hashlib.scrypt. The application can
# still be tested locally with Werkzeug's supported PBKDF2 password method.
import werkzeug.security

_generate_password_hash = werkzeug.security.generate_password_hash
werkzeug.security.generate_password_hash = (
    lambda password: _generate_password_hash(password, method='pbkdf2:sha256')
)

import main
from database import get_db, init_db


class MyRosterTestCase(unittest.TestCase):
    def setUp(self):
        handle, self.database_path = tempfile.mkstemp(suffix='.db')
        os.close(handle)
        main.Config.DATABASE = self.database_path
        main.app.config.update(TESTING=True)
        init_db()

        today = date.today()
        monday = today - timedelta(days=today.weekday())
        with get_db() as db:
            db.execute(
                'UPDATE terms SET start_date = ?, end_date = ? WHERE id = 1',
                ((monday - timedelta(days=14)).isoformat(),
                 (monday + timedelta(days=20)).isoformat())
            )
            db.execute(
                'INSERT INTO roster_entries (term_id, session_id, date, coach_id) '
                'VALUES (1, 1, ?, 2)',
                ((monday + timedelta(days=7)).isoformat(),)
            )
            db.execute(
                'INSERT INTO roster_entries (term_id, session_id, date, coach_id) '
                'VALUES (1, 1, ?, 3)',
                ((monday + timedelta(days=7)).isoformat(),)
            )
            db.commit()

        self.client = main.app.test_client()

    def tearDown(self):
        os.unlink(self.database_path)

    def login_as(self, coach_id):
        with self.client.session_transaction() as session:
            session['_user_id'] = str(coach_id)
            session['_fresh'] = True

    def test_coach_sees_only_their_allocated_sessions(self):
        self.login_as(2)

        response = self.client.get('/my-roster')

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'My Roster', response.data)
        self.assertIn(b'Peninsula Grammar', response.data)
        self.assertNotIn(b'Georgia', response.data)

    def test_coach_is_redirected_away_from_full_roster_routes(self):
        self.login_as(2)

        response = self.client.get('/roster/1')

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers['Location'].endswith('/my-roster'))

    def test_admin_keeps_full_roster_and_cannot_open_my_roster(self):
        self.login_as(1)

        roster_response = self.client.get('/roster/1')
        my_roster_response = self.client.get('/my-roster')

        self.assertEqual(roster_response.status_code, 200)
        self.assertEqual(my_roster_response.status_code, 302)
        self.assertTrue(my_roster_response.headers['Location'].endswith('/roster'))


if __name__ == '__main__':
    unittest.main()
