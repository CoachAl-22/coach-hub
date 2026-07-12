"""
Toorak College GSV Athletics Fixture 2026
P2A coaching supplied from 1 June 2026 onwards.

Run seed_fixture() to insert new session types and all fixture dates into the database.
Fixture dates are stored as specific roster slots (not recurring).
"""

from database import get_db

# ── New session types to add to the sessions table ─────────────────────────
# These are distinct from the existing Thursday 3pm-5pm Toorak afternoon program.

GSV_SESSIONS = [
    # (day_of_week, start_time, end_time, location, programs, min_coaches, max_coaches, notes)
    ('Monday',    '07:00', '08:30', 'Toorak College', 'GSV Athletics',   2, 4, 'Morning session - T&F'),
    ('Tuesday',   '07:00', '08:30', 'Toorak College', 'GSV Athletics',   2, 4, 'Morning session - T&F'),
    ('Thursday',  '07:00', '08:30', 'Toorak College', 'GSV Athletics',   2, 4, 'Morning session - T&F'),
    ('Friday',    '13:30', '15:30', 'Toorak College', 'GSV Athletics',   2, 4, 'Afternoon session - T3 only'),
]

# ── Full fixture: all dates requiring P2A coach presence ────────────────────
# Types: 'training' = regular session, 'event' = meet/competition, 'no_school' = flag only

FIXTURE_DATES = [

    # ── TERM 2 ──────────────────────────────────────────────────────────────
    # T&F starts Week 7. P2A coaches required from here.

    # Week 7
    {'date': '2026-06-01', 'day': 'Monday',    'start': '07:00', 'end': '08:15', 'type': 'training', 'event': 'Morning Training', 'notes': 'T&F starts Term 2'},
    {'date': '2026-06-02', 'day': 'Tuesday',   'start': '07:00', 'end': '08:15', 'type': 'training', 'event': 'Morning Training', 'notes': ''},
    {'date': '2026-06-03', 'day': 'Wednesday', 'start': None,    'end': None,    'type': 'event',    'event': 'WH Division Champs', 'notes': 'Time TBC'},
    {'date': '2026-06-04', 'day': 'Thursday',  'start': '07:00', 'end': '08:15', 'type': 'training', 'event': 'Morning Training', 'notes': ''},
    {'date': '2026-06-05', 'day': 'Friday',    'start': None,    'end': None,    'type': 'no_school','event': 'No School - Report Writing', 'notes': ''},

    # Week 8
    {'date': '2026-06-08', 'day': 'Monday',    'start': None,    'end': None,    'type': 'no_school','event': "No School - King's Birthday", 'notes': ''},
    {'date': '2026-06-12', 'day': 'Friday',    'start': None,    'end': None,    'type': 'event',    'event': 'House Track and Field', 'notes': 'Time TBC'},

    # Week 9
    {'date': '2026-06-17', 'day': 'Wednesday', 'start': None,    'end': None,    'type': 'event',    'event': 'WH Regionals', 'notes': 'Time TBC'},
    {'date': '2026-06-19', 'day': 'Friday',    'start': None,    'end': None,    'type': 'no_school','event': 'Last Day Term 2 / Holidays Begin', 'notes': ''},

    # ── TERM 3 ──────────────────────────────────────────────────────────────

    # Week 1
    {'date': '2026-07-13', 'day': 'Monday',    'start': '08:45', 'end': '12:30', 'type': 'event',    'event': 'Staff Day / Camp', 'notes': 'Not a regular coaching session'},
    {'date': '2026-07-16', 'day': 'Thursday',  'start': '07:00', 'end': '08:30', 'type': 'training', 'event': 'Morning Training', 'notes': ''},
    {'date': '2026-07-17', 'day': 'Friday',    'start': '13:30', 'end': '15:30', 'type': 'training', 'event': 'Afternoon Session', 'notes': ''},

    # Week 2
    {'date': '2026-07-23', 'day': 'Thursday',  'start': '07:00', 'end': '08:30', 'type': 'training', 'event': 'Morning Training', 'notes': ''},
    {'date': '2026-07-24', 'day': 'Friday',    'start': '13:30', 'end': '15:30', 'type': 'training', 'event': 'Afternoon Session', 'notes': ''},

    # Week 3
    {'date': '2026-07-27', 'day': 'Monday',    'start': '07:00', 'end': '08:30', 'type': 'training', 'event': 'Morning Training', 'notes': ''},
    {'date': '2026-07-29', 'day': 'Wednesday', 'start': None,    'end': None,    'type': 'event',    'event': 'Junior School House Aths', 'notes': 'Time TBC'},
    {'date': '2026-07-30', 'day': 'Thursday',  'start': '07:00', 'end': '08:30', 'type': 'training', 'event': 'Morning Training', 'notes': ''},
    {'date': '2026-07-31', 'day': 'Friday',    'start': '13:40', 'end': '14:35', 'type': 'event',    'event': 'Year 5/6 Sport (P5)', 'notes': 'Toorak doc lists Aug 1 - actual Friday is Jul 31'},

    # Week 4
    {'date': '2026-08-03', 'day': 'Monday',    'start': '07:00', 'end': '08:30', 'type': 'training', 'event': 'Morning Training', 'notes': 'Prelim entries due'},
    {'date': '2026-08-06', 'day': 'Thursday',  'start': '07:00', 'end': '08:30', 'type': 'training', 'event': 'Morning Training', 'notes': ''},
    {'date': '2026-08-07', 'day': 'Friday',    'start': '13:40', 'end': '14:35', 'type': 'event',    'event': 'Year 5/6 Sport (P5)', 'notes': ''},

    # Week 5
    {'date': '2026-08-10', 'day': 'Monday',    'start': '07:00', 'end': '08:30', 'type': 'training', 'event': 'Morning Training', 'notes': ''},
    {'date': '2026-08-11', 'day': 'Tuesday',   'start': '07:00', 'end': '15:30', 'type': 'event',    'event': 'GSV Prelim Athletics (hosted at Toorak)', 'notes': 'Full day event'},
    {'date': '2026-08-13', 'day': 'Thursday',  'start': '07:00', 'end': '08:30', 'type': 'training', 'event': 'Morning Training', 'notes': ''},
    {'date': '2026-08-14', 'day': 'Friday',    'start': '13:40', 'end': '14:35', 'type': 'event',    'event': 'Year 5/6 Sport (P5)', 'notes': ''},

    # Week 6
    {'date': '2026-08-17', 'day': 'Monday',    'start': '07:00', 'end': '08:30', 'type': 'training', 'event': 'Morning Training', 'notes': 'Champs entries due'},
    {'date': '2026-08-19', 'day': 'Wednesday', 'start': '07:00', 'end': '16:00', 'type': 'event',    'event': 'GSV Primary Athletics', 'notes': 'Full day event'},
    {'date': '2026-08-20', 'day': 'Thursday',  'start': '07:00', 'end': '08:30', 'type': 'training', 'event': 'Morning Training', 'notes': ''},

    # Week 7 (GSV Champs week)
    {'date': '2026-08-24', 'day': 'Monday',    'start': '07:00', 'end': '08:15', 'type': 'training', 'event': 'Morning Training', 'notes': ''},
    {'date': '2026-08-25', 'day': 'Tuesday',   'start': None,    'end': None,    'type': 'event',    'event': 'GSV Champs - Division 3', 'notes': 'Time TBC'},
    {'date': '2026-08-26', 'day': 'Wednesday', 'start': None,    'end': None,    'type': 'event',    'event': 'GSV Champs - Division 2', 'notes': 'Time TBC'},
    {'date': '2026-08-27', 'day': 'Thursday',  'start': None,    'end': None,    'type': 'event',    'event': 'GSV Champs - Division 1', 'notes': 'Time TBC'},
]


def seed_fixture():
    """
    Insert GSV session types and fixture dates into the Coach Hub database.
    Safe to re-run -- skips duplicates.
    """
    db = get_db()
    cursor = db.cursor()

    # Add new session types (skip if already present)
    for s in GSV_SESSIONS:
        existing = cursor.execute(
            'SELECT id FROM sessions WHERE day_of_week=? AND start_time=? AND location=? AND programs=?',
            (s[0], s[1], s[3], s[4])
        ).fetchone()
        if not existing:
            cursor.execute(
                'INSERT INTO sessions (day_of_week, start_time, end_time, location, programs, min_coaches, max_coaches, notes) VALUES (?,?,?,?,?,?,?,?)',
                s
            )
            print(f"Added session: {s[0]} {s[1]} - {s[4]}")
        else:
            print(f"Session already exists: {s[0]} {s[1]} - {s[4]}")

    db.commit()

    # Print fixture summary for review
    print("\n── Toorak College GSV Fixture 2026 ──")
    print(f"{'Date':<14} {'Day':<12} {'Time':<14} {'Type':<12} {'Event'}")
    print("-" * 75)
    for entry in FIXTURE_DATES:
        time_str = f"{entry['start']}-{entry['end']}" if entry['start'] else "TBC"
        print(f"{entry['date']:<14} {entry['day']:<12} {time_str:<14} {entry['type']:<12} {entry['event']}")

    db.close()
    print("\nDone. Review output above, then assign coaches via the roster.")


if __name__ == '__main__':
    seed_fixture()
