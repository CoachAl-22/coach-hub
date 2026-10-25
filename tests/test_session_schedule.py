import unittest
from datetime import date, datetime
from unittest.mock import patch

import main
from services.session_schedule import (
    is_within_effective_session_bounds,
    session_occurs_in_week,
)


TERM3 = {
    'id': 3, 'name': 'Term 3 2026',
    'start_date': '2026-07-13', 'end_date': '2026-09-25',
}
TERM4 = {
    'id': 4, 'name': 'Term 4 2026',
    'start_date': '2026-10-05', 'end_date': '2026-12-18',
}
PENINSULA_ID = 100
BALLAM_ID = 101
PENINSULA = {
    'id': PENINSULA_ID, 'day_of_week': 'Tuesday', 'start_time': '07:00',
    'end_time': '08:00', 'location': 'Peninsula Grammar',
    'programs': 'Athletics', 'min_coaches': 1, 'max_coaches': 2,
}
BALLAM = {
    'id': BALLAM_ID, 'day_of_week': 'Tuesday', 'start_time': '07:00',
    'end_time': '08:00', 'location': 'Ballam Park',
    'programs': 'Athletics', 'min_coaches': 1, 'max_coaches': 2,
}


class Result:
    def __init__(self, row=None, rows=None):
        self.row = row
        self.rows = rows or []

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class FakeScheduleDB:
    """In-memory route mock; it never writes roster or production data."""

    def __init__(self):
        self.terms = [TERM3, TERM4]
        self.sessions = [PENINSULA, BALLAM]
        self.overrides = {(PENINSULA_ID, TERM4['id']): {
            'start_date': None, 'end_date': '2026-10-04',
        }}
        self.queries = []
        self.inserts = []
        self.closed = False

    def execute(self, sql, args=()):
        normalized = ' '.join(sql.split())
        self.queries.append((normalized, args))

        if 'FROM terms t LEFT JOIN session_overrides so' in normalized:
            week_end = date.fromisoformat(args[0])
            week_start = date.fromisoformat(args[1])
            rows = []
            for term in self.terms:
                if (date.fromisoformat(term['start_date']) <= week_end
                        and date.fromisoformat(term['end_date']) >= week_start):
                    term_overrides = [
                        (session_id, override)
                        for (session_id, term_id), override in self.overrides.items()
                        if term_id == term['id']
                    ]
                    if term_overrides:
                        for session_id, override in term_overrides:
                            rows.append({
                                'term_id': term['id'],
                                'term_start': term['start_date'],
                                'term_end': term['end_date'],
                                'session_id': session_id,
                                'override_start': override['start_date'],
                                'override_end': override['end_date'],
                            })
                    else:
                        rows.append({
                            'term_id': term['id'],
                            'term_start': term['start_date'],
                            'term_end': term['end_date'],
                            'session_id': None,
                            'override_start': None,
                            'override_end': None,
                        })
            return Result(rows=rows)

        if normalized.startswith('SELECT 1 FROM terms WHERE start_date <='):
            today = date.fromisoformat(args[0])
            active = any(
                date.fromisoformat(term['start_date']) <= today <= date.fromisoformat(term['end_date'])
                for term in self.terms
            )
            return Result({'exists': 1} if active else None)

        if normalized.startswith('SELECT * FROM terms WHERE start_date >'):
            today = date.fromisoformat(args[0])
            upcoming = [term for term in self.terms if date.fromisoformat(term['start_date']) > today]
            upcoming.sort(key=lambda term: term['start_date'])
            return Result(upcoming[0] if upcoming else None)

        if normalized.startswith('SELECT * FROM terms ORDER BY start_date'):
            return Result(rows=self.terms)

        if normalized.startswith('SELECT * FROM sessions WHERE is_active = 1'):
            return Result(rows=self.sessions)

        if normalized.startswith('SELECT session_id, date FROM session_cancellations'):
            return Result(rows=[])

        if normalized.startswith('SELECT re.*, c.name as coach_name FROM roster_entries'):
            return Result(rows=[])

        if normalized.startswith('SELECT c.name FROM roster_entries'):
            return Result(rows=[])

        if 'JOIN sessions s ON s.id = %s' in normalized:
            session_id, term_id = args
            term = next((term for term in self.terms if term['id'] == term_id), None)
            if not term or not any(session['id'] == session_id for session in self.sessions):
                return Result()
            override = self.overrides.get((session_id, term_id), {})
            return Result({
                'term_start': term['start_date'],
                'term_end': term['end_date'],
                'override_start': override.get('start_date'),
                'override_end': override.get('end_date'),
            })

        if normalized.startswith(
            'SELECT auth_version FROM public.coach_auth_state WHERE coach_id'
        ):
            return Result()

        if normalized.startswith('SELECT * FROM coaches WHERE id'):
            return Result({
                'id': 1, 'name': 'Test Admin', 'username': 'admin',
                'is_admin': 1, 'is_standby': 0, 'is_active': 1, 'auth_version': 0,
            })

        if normalized.startswith('INSERT INTO roster_entries'):
            self.inserts.append(args)
            return Result()

        raise AssertionError(f'Unexpected database query: {normalized}')

    def commit(self):
        raise AssertionError('Schedule tests must not write database data.')

    def close(self):
        self.closed = True


class FixedDatetime(datetime):
    current = datetime(2026, 10, 6, 12)

    @classmethod
    def now(cls, tz=None):
        return cls.current.replace(tzinfo=tz)


class SessionScheduleTests(unittest.TestCase):
    def setUp(self):
        self.db = FakeScheduleDB()
        self.get_db_patcher = patch.object(main, 'get_db', return_value=self.db)
        self.get_db_patcher.start()
        self.addCleanup(self.get_db_patcher.stop)
        self.datetime_patcher = patch.object(main, 'datetime', FixedDatetime)
        self.datetime_patcher.start()
        self.addCleanup(self.datetime_patcher.stop)
        self.client = main.app.test_client()
        self.original_api_key = main.app.config.get('API_KEY')
        main.app.config['API_KEY'] = 'schedule-test-key'
        self.addCleanup(self._restore_api_key)

    def _restore_api_key(self):
        main.app.config['API_KEY'] = self.original_api_key

    def _login_as_admin(self):
        with self.client.session_transaction() as session:
            session['_user_id'] = '1'
            session['_fresh'] = True
            session['auth_version'] = 0

    def test_api_and_dashboard_apply_term4_exclusion_only(self):
        api_response = self.client.get('/api/this-week?key=schedule-test-key')
        self.assertEqual(api_response.status_code, 200)
        api_sessions = api_response.get_json()['sessions']
        api_locations = [session['location'] for session in api_sessions]
        self.assertNotIn('Peninsula Grammar', api_locations)
        self.assertIn('Ballam Park', api_locations)

        FixedDatetime.current = datetime(2026, 7, 14, 12)
        t3_db = FakeScheduleDB()
        with patch.object(main, 'get_db', return_value=t3_db):
            t3_response = self.client.get('/api/this-week?key=schedule-test-key')
        self.assertEqual(t3_response.status_code, 200)
        t3_locations = [
            session['location'] for session in t3_response.get_json()['sessions']
        ]
        self.assertIn('Peninsula Grammar', t3_locations)
        self.assertIn('Ballam Park', t3_locations)

        FixedDatetime.current = datetime(2026, 9, 28, 12)
        self.db = FakeScheduleDB()
        with patch.object(main, 'get_db', return_value=self.db), patch.object(
                main, 'get_current_or_next_term', return_value=TERM4):
            self._login_as_admin()
            captured = {}

            def capture_dashboard(template, **context):
                captured.update(context)
                return 'dashboard'

            with patch.object(main, 'render_template', side_effect=capture_dashboard):
                dashboard_response = self.client.get('/dashboard')

        self.assertEqual(dashboard_response.status_code, 200)
        locations = [
            occurrence['session']['location']
            for occurrence in captured['week_schedule']
        ]
        self.assertEqual(captured['week_start'], date(2026, 10, 5))
        self.assertNotIn('Peninsula Grammar', locations)
        self.assertIn('Ballam Park', locations)
        batch_queries = [
            sql for sql, _ in self.db.queries
            if 'FROM terms t LEFT JOIN session_overrides so' in sql
        ]
        self.assertEqual(len(batch_queries), 1)

    def test_t3_peninsula_occurrence_remains_and_ballam_is_unaffected(self):
        term3_schedule = {
            'term_start': TERM3['start_date'],
            'term_end': TERM3['end_date'],
            'overrides': {},
        }
        self.assertTrue(session_occurs_in_week(
            PENINSULA_ID, date(2026, 7, 14), [term3_schedule]
        ))
        term4_schedule = {
            'term_start': TERM4['start_date'],
            'term_end': TERM4['end_date'],
            'overrides': {
                PENINSULA_ID: {
                    'override_start': None,
                    'override_end': '2026-10-04',
                },
            },
        }
        self.assertFalse(session_occurs_in_week(
            PENINSULA_ID, date(2026, 10, 6), [term4_schedule]
        ))
        self.assertTrue(session_occurs_in_week(
            BALLAM_ID, date(2026, 10, 6), [term4_schedule]
        ))

    def test_forced_assignment_outside_override_bounds_is_refused(self):
        self._login_as_admin()
        response = self.client.post('/roster/4/assign', json={
            'session_id': PENINSULA_ID,
            'coach_id': 1,
            'date': '2026-10-06',
            'force': True,
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.db.inserts, [])

    def test_explicit_camp_start_before_term_start_is_permitted(self):
        self.assertTrue(is_within_effective_session_bounds(
            date(2026, 7, 13),
            '2026-07-14',
            '2026-09-25',
            {'override_start': '2026-07-13', 'override_end': '2026-07-20'},
        ))


if __name__ == '__main__':
    unittest.main()