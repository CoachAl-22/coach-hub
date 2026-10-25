import os
import json
import secrets as _secrets
from datetime import date, timedelta
import psycopg2
import psycopg2.extras
from werkzeug.security import generate_password_hash

# Prefer individual PG* vars (always correct for this environment) over DATABASE_URL,
# which may be overwritten with a production Neon URL that isn't reachable in dev.
_pghost = os.environ.get('PGHOST')
_pgport = os.environ.get('PGPORT', '5432')
_pgdb   = os.environ.get('PGDATABASE')
_pguser = os.environ.get('PGUSER')
_pgpass = os.environ.get('PGPASSWORD', '')
if _pghost and _pgdb:
    DATABASE_URL = f"postgresql://{_pguser}:{_pgpass}@{_pghost}:{_pgport}/{_pgdb}"
else:
    DATABASE_URL = os.environ.get('DATABASE_URL')


class _Cursor:
    def __init__(self, pg_cursor):
        self._c = pg_cursor

    @property
    def rowcount(self):
        return self._c.rowcount

    def fetchone(self):
        return self._c.fetchone()

    def fetchall(self):
        return self._c.fetchall()

    def __iter__(self):
        return iter(self._c)


class _Connection:
    def __init__(self, url):
        # Set search_path at connection level so every query uses the ch schema
        self._conn = psycopg2.connect(
            url,
            cursor_factory=psycopg2.extras.RealDictCursor,
            options='-c search_path=ch,public'
        )

    def execute(self, sql, params=None):
        sql = sql.replace('?', '%s')
        cur = self._conn.cursor()
        cur.execute(sql, params or ())
        return _Cursor(cur)

    def executemany(self, sql, seq):
        sql = sql.replace('?', '%s')
        cur = self._conn.cursor()
        psycopg2.extras.execute_batch(cur, sql, seq)

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


def get_db():
    return _Connection(DATABASE_URL)


def init_db():
    conn = get_db()

    # Ensure our schema exists before creating tables
    conn.execute('CREATE SCHEMA IF NOT EXISTS ch')
    conn.commit()

    statements = [
        '''CREATE TABLE IF NOT EXISTS coaches (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            username TEXT UNIQUE NOT NULL,
            email TEXT,
            mobile TEXT,
            role TEXT,
            level TEXT,
            is_admin INTEGER DEFAULT 0,
            is_standby INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            password_hash TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''',
        '''CREATE TABLE IF NOT EXISTS login_attempts (
            attempt_key TEXT PRIMARY KEY,
            failures INTEGER NOT NULL DEFAULT 0,
            window_started TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )''',
        '''CREATE INDEX IF NOT EXISTS login_attempts_window_idx
           ON login_attempts (window_started)''',
        '''CREATE TABLE IF NOT EXISTS sessions (
            id SERIAL PRIMARY KEY,
            day_of_week TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            location TEXT NOT NULL,
            programs TEXT,
            min_coaches INTEGER DEFAULT 1,
            max_coaches INTEGER DEFAULT 4,
            notes TEXT,
            is_active INTEGER DEFAULT 1
        )''',
        '''CREATE TABLE IF NOT EXISTS terms (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            year INTEGER NOT NULL,
            term_number INTEGER NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL
        )''',
        '''CREATE TABLE IF NOT EXISTS session_overrides (
            session_id INTEGER,
            term_id INTEGER,
            start_date TEXT,
            end_date TEXT NOT NULL,
            PRIMARY KEY (session_id, term_id)
        )''',
        '''CREATE TABLE IF NOT EXISTS session_cancellations (
            session_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            reason TEXT,
            PRIMARY KEY (session_id, date)
        )''',
        '''CREATE TABLE IF NOT EXISTS fixtures (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            date TEXT NOT NULL,
            location TEXT,
            school TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''',
        '''CREATE TABLE IF NOT EXISTS fixture_coaches (
            fixture_id INTEGER,
            coach_id INTEGER,
            PRIMARY KEY (fixture_id, coach_id)
        )''',
        '''CREATE TABLE IF NOT EXISTS roster_entries (
            id SERIAL PRIMARY KEY,
            term_id INTEGER NOT NULL,
            session_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            coach_id INTEGER NOT NULL,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(term_id, session_id, date, coach_id)
        )''',
        '''CREATE TABLE IF NOT EXISTS availability_responses (
            id SERIAL PRIMARY KEY,
            coach_id INTEGER NOT NULL,
            term_id INTEGER NOT NULL,
            weekly_availability TEXT DEFAULT '{}',
            unavailable_dates TEXT DEFAULT '[]',
            notes TEXT,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(coach_id, term_id)
        )''',
        '''CREATE TABLE IF NOT EXISTS availability_tokens (
            id SERIAL PRIMARY KEY,
            coach_id INTEGER NOT NULL,
            term_id INTEGER NOT NULL,
            token TEXT UNIQUE NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            used INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''',
        '''CREATE TABLE IF NOT EXISTS sms_log (
            id SERIAL PRIMARY KEY,
            coach_id INTEGER,
            mobile TEXT,
            message TEXT,
            type TEXT,
            status TEXT,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''',

        # ── Learning Hub ───────────────────────────────────────────────────
        '''CREATE TABLE IF NOT EXISTS module_completions (
            id SERIAL PRIMARY KEY,
            coach_id INTEGER NOT NULL,
            module_key TEXT NOT NULL,
            completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (coach_id, module_key)
        )''',

        '''CREATE TABLE IF NOT EXISTS induction_checklist_items (
            id SERIAL PRIMARY KEY,
            category TEXT NOT NULL,
            item_text TEXT NOT NULL,
            requires_admin_signoff BOOLEAN DEFAULT FALSE,
            sequence_order INTEGER NOT NULL
        )''',

        '''CREATE TABLE IF NOT EXISTS induction_checklist_progress (
            coach_id INTEGER NOT NULL,
            item_id INTEGER NOT NULL,
            completed_at TIMESTAMP,
            admin_signoff_at TIMESTAMP,
            PRIMARY KEY (coach_id, item_id)
        )''',
    ]

    for sql in statements:
        conn.execute(sql)
    conn.execute("DELETE FROM login_attempts WHERE window_started < NOW() - INTERVAL '1 day'")

    result = conn.execute('SELECT COUNT(*) AS cnt FROM coaches').fetchone()
    if result['cnt'] == 0:
        _seed_coaches(conn)
        _seed_sessions(conn)
        _seed_terms(conn)
        conn.commit()
        _seed_overrides(conn)
        _seed_fixtures(conn)

    checklist_count = conn.execute('SELECT COUNT(*) AS cnt FROM induction_checklist_items').fetchone()['cnt']
    if checklist_count == 0:
        _seed_checklist(conn)
        conn.commit()

    # Always ensure Alistair has his mobile set
    conn.execute(
        "UPDATE coaches SET mobile = '+61434679395' WHERE username = 'alistair' AND (mobile IS NULL OR mobile = '')"
    )

    conn.commit()

    # Ensure public schema performance tables exist
    _init_public_schema(conn)

    # Ensure Toorak College morning + P5 sessions exist for Term 2 & 3
    _ensure_toorak_morning_sessions(conn)

    # Ensure Term 3 Peninsula Grammar sessions, fixtures, and Declyn roster
    _ensure_term3_pg_data(conn)

    # Ensure Term 4 starts on Monday with the correct Peninsula and Ballam sessions
    _ensure_term4_monday_sessions(conn)

    # Keep coach statuses and Term 4 availability aligned with the current roster
    _ensure_coach_statuses_and_term4_availability(conn)

    conn.close()


def _init_public_schema(conn):
    """Create missing public-schema tables (idempotent — IF NOT EXISTS)."""
    stmts = [
        '''CREATE TABLE IF NOT EXISTS public.athletes (
            id              SERIAL PRIMARY KEY,
            name            TEXT NOT NULL,
            initials        TEXT,
            event_group     TEXT,
            squad           TEXT,
            assessment_code TEXT UNIQUE,
            dob             DATE,
            is_active       BOOLEAN DEFAULT true,
            created_at      TIMESTAMPTZ DEFAULT NOW()
        )''',
        '''CREATE TABLE IF NOT EXISTS public.training_sessions (
            id                   SERIAL PRIMARY KEY,
            name                 TEXT NOT NULL,
            description          TEXT,
            session_type         TEXT,
            event_group          TEXT,
            training_phase       TEXT,
            intensity_level      TEXT,
            tags                 TEXT[] DEFAULT '{}',
            source_year          INT,
            is_archived          BOOLEAN DEFAULT false,
            coach_notes          TEXT,
            target_sets          INT,
            target_reps          INT,
            target_recovery_secs INT,
            target_intensity_pct INT,
            target_notes         TEXT,
            created_at           TIMESTAMPTZ DEFAULT NOW(),
            updated_at           TIMESTAMPTZ DEFAULT NOW()
        )''',
        '''CREATE TABLE IF NOT EXISTS public.athlete_training_plans (
            id                  SERIAL PRIMARY KEY,
            athlete_id          INT REFERENCES public.athletes(id) ON DELETE CASCADE,
            training_session_id INT REFERENCES public.training_sessions(id) ON DELETE CASCADE,
            notes               TEXT,
            day_of_week         INT,
            UNIQUE (athlete_id, training_session_id)
        )''',
        '''CREATE TABLE IF NOT EXISTS public.macrocycle_blocks (
            id               SERIAL PRIMARY KEY,
            season           TEXT NOT NULL,
            block_number     INT  NOT NULL,
            block_name       TEXT,
            start_date       DATE,
            end_date         DATE,
            mesocycle_phase  TEXT,
            strength_label   TEXT,
            speed_label      TEXT,
            intensity_level  TEXT,
            volume_level     TEXT,
            sc_phase_code    TEXT,
            UNIQUE (season, block_number)
        )''',
        '''CREATE TABLE IF NOT EXISTS public.performance_tests (
            id               SERIAL PRIMARY KEY,
            athlete_id       INT REFERENCES public.athletes(id) ON DELETE CASCADE,
            test_date        DATE NOT NULL,
            macrocycle_block INT,
            test_protocol    TEXT,
            conditions       TEXT,
            notes            TEXT,
            created_at       TIMESTAMPTZ DEFAULT NOW()
        )''',
        '''CREATE TABLE IF NOT EXISTS public.test_results (
            id             SERIAL PRIMARY KEY,
            test_id        INT REFERENCES public.performance_tests(id) ON DELETE CASCADE,
            metric         TEXT NOT NULL,
            value          NUMERIC(8,3),
            unit           TEXT,
            attempt_number INT DEFAULT 1,
            wind_reading   NUMERIC(4,2),
            is_pb          BOOLEAN DEFAULT false,
            notes          TEXT,
            created_at     TIMESTAMPTZ DEFAULT NOW()
        )''',
        '''CREATE TABLE IF NOT EXISTS public.performance_benchmarks (
            id          SERIAL PRIMARY KEY,
            sport       TEXT,
            event_group TEXT,
            metric      TEXT NOT NULL,
            age_group   TEXT,
            gender      TEXT,
            level       TEXT,
            value       NUMERIC(8,3),
            unit        TEXT,
            source      TEXT
        )''',
        '''CREATE TABLE IF NOT EXISTS public.sc_phases (
            id                    SERIAL PRIMARY KEY,
            name                  TEXT NOT NULL,
            short_code            TEXT NOT NULL,
            bompa_label           TEXT,
            macrocycle_phase      TEXT,
            macrocycle_blocks     TEXT,
            typical_weeks         TEXT,
            sessions_per_week_min INT DEFAULT 2,
            sessions_per_week_max INT DEFAULT 2,
            sets_min INT, sets_max INT,
            reps_min INT, reps_max INT,
            load_pct_min INT, load_pct_max INT,
            rest_seconds_min INT, rest_seconds_max INT,
            tempo_guidance TEXT,
            rpe_target_min INT, rpe_target_max INT,
            primary_goal TEXT,
            sprint_specific_focus TEXT,
            display_order INT
        )''',
        '''CREATE TABLE IF NOT EXISTS public.sc_workout_templates (
            id             SERIAL PRIMARY KEY,
            name           TEXT NOT NULL,
            sc_phase_id    INT REFERENCES public.sc_phases(id),
            session_label  TEXT,
            session_focus  TEXT,
            warmup_notes   TEXT,
            cooldown_notes TEXT,
            coach_notes    TEXT,
            week_placement TEXT,
            tags           TEXT[] DEFAULT '{}',
            display_order  INT
        )''',
        '''CREATE TABLE IF NOT EXISTS public.sc_workout_logs (
            id                   SERIAL PRIMARY KEY,
            athlete_id           INT REFERENCES public.athletes(id) ON DELETE CASCADE,
            template_id          INT REFERENCES public.sc_workout_templates(id),
            sc_phase_id          INT REFERENCES public.sc_phases(id),
            workout_date         DATE NOT NULL,
            macrocycle_block     TEXT,
            overall_rpe          INT CHECK (overall_rpe BETWEEN 1 AND 10),
            session_duration_min INT,
            coach_notes          TEXT,
            athlete_feedback     TEXT,
            created_at           TIMESTAMPTZ DEFAULT NOW()
        )''',
    ]
    for sql in stmts:
        conn.execute(sql)
    conn.commit()

    cnt = conn.execute('SELECT COUNT(*) AS cnt FROM public.training_sessions').fetchone()['cnt']
    if cnt == 0:
        _seed_training_sessions(conn)
        conn.execute(
            "SELECT setval(pg_get_serial_sequence('public.training_sessions','id'), "
            "COALESCE((SELECT MAX(id) FROM public.training_sessions), 0) + 1, false)"
        )
        conn.commit()


def _ensure_toorak_morning_sessions(conn):
    """Idempotently add Toorak College morning + P5 sessions for Term 2 & 3."""
    new_sessions = [
        ('Monday',   '07:00', '08:30', 'Toorak College', 'School Program', 2, 3, '7am setup required'),
        ('Tuesday',  '07:00', '08:15', 'Toorak College', 'School Program', 2, 3, '7am setup required'),
        ('Thursday', '07:00', '08:30', 'Toorak College', 'School Program', 2, 3, '7am setup required'),
        ('Friday',   '13:30', '15:30', 'Toorak College', 'School Program (P5)', 2, 3, ''),
    ]

    for day, start, end, location, programs, min_c, max_c, notes in new_sessions:
        existing = conn.execute(
            'SELECT id FROM sessions WHERE day_of_week=%s AND start_time=%s AND location=%s',
            (day, start, location)
        ).fetchone()

        if existing:
            session_id = existing['id']
        else:
            row = conn.execute(
                '''INSERT INTO sessions (day_of_week, start_time, end_time, location, programs, min_coaches, max_coaches, notes)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id''',
                (day, start, end, location, programs, min_c, max_c, notes)
            ).fetchone()
            session_id = row['id']

        # Term 2 (id=2): Mon/Tue/Thu start from Jun 1 (WK 7), end Jun 19; Fri excluded entirely
        # Term 4 (id=4): all excluded (user only asked for T2 & T3)
        if day in ('Monday', 'Tuesday', 'Thursday'):
            conn.execute(
                '''INSERT INTO session_overrides (session_id, term_id, start_date, end_date)
                   VALUES (%s, 2, '2026-06-01', '2026-06-19')
                   ON CONFLICT (session_id, term_id) DO NOTHING''',
                (session_id,)
            )
            conn.execute(
                '''INSERT INTO session_overrides (session_id, term_id, start_date, end_date)
                   VALUES (%s, 4, NULL, '2026-10-05')
                   ON CONFLICT (session_id, term_id) DO NOTHING''',
                (session_id,)
            )
        else:
            # Friday: exclude from Term 2
            conn.execute(
                '''INSERT INTO session_overrides (session_id, term_id, start_date, end_date)
                   VALUES (%s, 2, NULL, '2026-04-19')
                   ON CONFLICT (session_id, term_id) DO NOTHING''',
                (session_id,)
            )
            # Friday: exclude from Term 4
            conn.execute(
                '''INSERT INTO session_overrides (session_id, term_id, start_date, end_date)
                   VALUES (%s, 4, NULL, '2026-10-05')
                   ON CONFLICT (session_id, term_id) DO NOTHING''',
                (session_id,)
            )

    conn.commit()


def _ensure_term3_pg_data(conn):
    """Idempotently create Term 3 Peninsula Grammar sessions, fixtures, and Declyn's roster."""
    from datetime import date, timedelta

    # ── Coach IDs (look up by name so dev/prod IDs don't matter) ────────────
    declyn = conn.execute("SELECT id FROM coaches WHERE name ILIKE %s", ('Declyn%',)).fetchone()
    sami   = conn.execute("SELECT id FROM coaches WHERE name ILIKE %s", ('Sami%',)).fetchone()
    term3  = conn.execute("SELECT id, start_date, end_date FROM terms WHERE name=%s", ('Term 3 2026',)).fetchone()
    if not declyn or not term3:
        return
    declyn_id = declyn['id']
    sami_id   = sami['id'] if sami else None
    term_id   = term3['id']
    term_start = date.fromisoformat(str(term3['start_date']))
    term_end   = date.fromisoformat(str(term3['end_date']))

    # ── 1. Sessions ──────────────────────────────────────────────────────────
    pg_sessions = [
        ('Monday',    '15:45', '17:00', 'Peninsula Grammar', 'Athletics Training', 1, 2),
        ('Wednesday', '15:45', '17:00', 'Peninsula Grammar', 'Athletics Training', 1, 2),
    ]
    session_ids = {}
    for day, start, end, loc, prog, mn, mx in pg_sessions:
        all_rows = conn.execute(
            'SELECT id FROM sessions WHERE day_of_week=%s AND start_time=%s AND location=%s ORDER BY id',
            (day, start, loc)
        ).fetchall()
        if all_rows:
            sid = all_rows[0]['id']
            # Deactivate any duplicate sessions (higher IDs for same slot)
            for dup in all_rows[1:]:
                conn.execute('UPDATE sessions SET is_active=0 WHERE id=%s', (dup['id'],))
        else:
            sid = conn.execute(
                '''INSERT INTO sessions (day_of_week, start_time, end_time, location, programs, min_coaches, max_coaches, is_active)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,1) RETURNING id''',
                (day, start, end, loc, prog, mn, mx)
            ).fetchone()['id']
        session_ids[day] = sid

        # Exclude from Terms 1, 2, 4 — restrict to Term 3 only
        for excl_term, excl_end in [(1, '2026-01-27'), (2, '2026-04-19'), (4, '2026-10-05')]:
            conn.execute(
                '''INSERT INTO session_overrides (session_id, term_id, start_date, end_date)
                   VALUES (%s,%s,NULL,%s) ON CONFLICT (session_id, term_id) DO NOTHING''',
                (sid, excl_term, excl_end)
            )

    # ── 2. Roster entries — seeding removed; roster is managed via the UI ────

    # ── 2a. Blake Ireland — Thu 15:00 Toorak (session 8) every Term 3 Thursday
    blake = conn.execute("SELECT id FROM coaches WHERE username='blake'").fetchone()
    thu_toorak = conn.execute(
        "SELECT id FROM sessions WHERE day_of_week='Thursday' AND start_time='15:00' AND location ILIKE %s AND is_active=1",
        ('%toorak%',)
    ).fetchone()
    if blake and thu_toorak:
        d = term_start
        while d <= term_end:
            if d.weekday() == 3:  # Thursday
                conn.execute(
                    '''INSERT INTO roster_entries (term_id, session_id, date, coach_id)
                       VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING''',
                    (term_id, thu_toorak['id'], d.isoformat(), blake['id'])
                )
            d += timedelta(days=1)

    # ── 2b. One-off: Athletics Team Camp — Mon 13 Jul, 09:00–13:00 ───────────
    camp = conn.execute(
        "SELECT id FROM sessions WHERE programs='Athletics Team Camp' AND start_time='09:00'",
    ).fetchone()
    if camp:
        camp_id = camp['id']
    else:
        camp_id = conn.execute(
            '''INSERT INTO sessions (day_of_week, start_time, end_time, location, programs, min_coaches, max_coaches, is_active)
               VALUES ('Monday','09:00','13:00','Peninsula Grammar','Athletics Team Camp',1,2,1) RETURNING id'''
        ).fetchone()['id']
    # Exclude from Terms 1, 2, 4 entirely
    for excl_term, excl_end in [(1, '2026-01-27'), (2, '2026-04-19'), (4, '2026-10-05')]:
        conn.execute(
            '''INSERT INTO session_overrides (session_id, term_id, start_date, end_date)
               VALUES (%s,%s,NULL,%s) ON CONFLICT (session_id, term_id) DO NOTHING''',
            (camp_id, excl_term, excl_end)
        )
    # Term 3: show on Jul 13 only (one date before term officially starts)
    conn.execute(
        '''INSERT INTO session_overrides (session_id, term_id, start_date, end_date)
           VALUES (%s,%s,'2026-07-13','2026-07-13') ON CONFLICT (session_id, term_id) DO NOTHING''',
        (camp_id, term_id)
    )
    # Roster entry for Declyn on Jul 13
    conn.execute(
        '''INSERT INTO roster_entries (term_id, session_id, date, coach_id)
           VALUES (%s,%s,'2026-07-13',%s) ON CONFLICT DO NOTHING''',
        (term_id, camp_id, declyn_id)
    )

    # ── 3. Fixtures ──────────────────────────────────────────────────────────
    fixtures = [
        ('PGS Internal Time Trial Meet', '2026-07-31', 'Peninsula Grammar',                   'Peninsula Grammar', '3:00pm–5:30pm'),
        ('AGSV Time Trial Meet',         '2026-08-15', 'Tom Kelly Athletics Track, Doncaster', 'Peninsula Grammar', '7:00am–1:30pm (*bus)'),
        ('AGSV Time Trial Meet',         '2026-08-22', 'Peninsula',                            'Peninsula Grammar', '7:30am–12:30pm'),
        ('AGSV Time Trial Meet',         '2026-08-29', 'Dolomore Athletics Track, Mentone',    'Peninsula Grammar', '7:30am–1:00pm (*bus)'),
        ('AGSV Championships (TBC)',     '2026-09-04', 'Tom Kelly Athletics Track, Doncaster', 'Peninsula Grammar', '3:00pm–9:00pm (*bus, TO BE CONFIRMED)'),
        ('AGSV Championships',           '2026-09-09', 'Lakeside Stadium',                     'Peninsula Grammar', 'All day, times TBC'),
    ]
    for title, fdate, loc, school, notes in fixtures:
        existing = conn.execute(
            'SELECT id FROM fixtures WHERE title=%s AND date=%s', (title, fdate)
        ).fetchone()
        if existing:
            fid = existing['id']
        else:
            fid = conn.execute(
                'INSERT INTO fixtures (title, date, location, school, notes) VALUES (%s,%s,%s,%s,%s) RETURNING id',
                (title, fdate, loc, school, notes)
            ).fetchone()['id']
        conn.execute(
            'INSERT INTO fixture_coaches (fixture_id, coach_id) VALUES (%s,%s) ON CONFLICT DO NOTHING',
            (fid, declyn_id)
        )
        if sami_id and fdate == '2026-09-09':
            conn.execute(
                'INSERT INTO fixture_coaches (fixture_id, coach_id) VALUES (%s,%s) ON CONFLICT DO NOTHING',
                (fid, sami_id)
            )

    conn.commit()


def _ensure_term4_monday_sessions(conn):
    """Apply Term 4 schedule changes without changing earlier terms."""
    conn.execute(
        "UPDATE terms SET start_date=%s WHERE name=%s",
        ('2026-10-05', 'Term 4 2026')
    )
    term4 = conn.execute(
        "SELECT id FROM terms WHERE name=%s",
        ('Term 4 2026',)
    ).fetchone()
    if not term4:
        return

    term4_id = term4['id']

    # Keep existing Term 4 exclusions effective when the term starts one day earlier.
    conn.execute(
        '''UPDATE session_overrides
           SET end_date=%s
           WHERE term_id=%s AND start_date IS NULL AND end_date=%s''',
        ('2026-10-04', term4_id, '2026-10-05')
    )

    # The older Monday Peninsula class remains available to earlier terms only.
    old_peninsula = conn.execute(
        '''SELECT id FROM sessions
           WHERE day_of_week='Monday' AND start_time='15:00'
             AND location ILIKE %s AND is_active=1''',
        ('%Peninsula Grammar%',)
    ).fetchone()
    if old_peninsula:
        conn.execute(
            '''INSERT INTO session_overrides (session_id, term_id, start_date, end_date)
               VALUES (%s, %s, NULL, %s)
               ON CONFLICT (session_id, term_id)
               DO UPDATE SET start_date=NULL, end_date=EXCLUDED.end_date''',
            (old_peninsula['id'], term4_id, '2026-10-04')
        )

    # Keep the older school program excluded; the separately requested Term 4
    # Run Club below has its own time and date window.
    tuesday_school = conn.execute(
        '''SELECT id FROM sessions
           WHERE day_of_week='Tuesday' AND start_time='07:00'
             AND location ILIKE %s
             AND (programs IS DISTINCT FROM 'Run Club' OR end_time <> '08:30')''',
        ('%Peninsula Grammar%',)
    ).fetchall()
    for school_session in tuesday_school:
        conn.execute(
            '''INSERT INTO session_overrides (session_id, term_id, start_date, end_date)
               VALUES (%s, %s, NULL, %s)
               ON CONFLICT (session_id, term_id)
               DO UPDATE SET start_date=NULL, end_date=EXCLUDED.end_date''',
            (school_session['id'], term4_id, '2026-10-04')
        )
        conn.execute(
            'DELETE FROM roster_entries WHERE term_id=%s AND session_id=%s',
            (term4_id, school_session['id'])
        )

    _ensure_term4_run_club(conn, term4_id)

    emerging = conn.execute(
        '''SELECT id FROM sessions
           WHERE day_of_week='Monday' AND start_time='15:30' AND end_time='16:45'
             AND location ILIKE %s AND programs=%s''',
        ('%Peninsula Grammar%', 'Emerging Athlete')
    ).fetchone()
    if emerging:
        emerging_id = emerging['id']
        conn.execute("UPDATE sessions SET is_active=1 WHERE id=%s", (emerging_id,))
    else:
        emerging_id = conn.execute(
            '''INSERT INTO sessions
               (day_of_week, start_time, end_time, location, programs,
                min_coaches, max_coaches, notes, is_active)
               VALUES ('Monday', '15:30', '16:45', 'Peninsula Grammar',
                       'Emerging Athlete', 2, 4, '', 1)
               RETURNING id'''
        ).fetchone()['id']

    # This class is specific to Term 4 2026.
    for excluded_term in (1, 2, 3):
        excluded = conn.execute(
            "SELECT start_date FROM terms WHERE id=%s",
            (excluded_term,)
        ).fetchone()
        if excluded:
            day_before = (
                date.fromisoformat(str(excluded['start_date'])) - timedelta(days=1)
            ).isoformat()
            conn.execute(
                '''INSERT INTO session_overrides
                   (session_id, term_id, start_date, end_date)
                   VALUES (%s, %s, NULL, %s)
                   ON CONFLICT (session_id, term_id)
                   DO UPDATE SET start_date=NULL, end_date=EXCLUDED.end_date''',
                (emerging_id, excluded_term, day_before)
            )

    conn.commit()


def _ensure_term4_run_club(conn, term4_id):
    """Add the requested Run Club without changing historical school sessions."""
    club = conn.execute(
        '''SELECT id FROM sessions
           WHERE day_of_week='Tuesday' AND start_time='07:00' AND end_time='08:30'
             AND location='Peninsula Grammar' AND programs='Run Club'
           ORDER BY id LIMIT 1'''
    ).fetchone()
    if club:
        club_id = club['id']
        conn.execute(
            'UPDATE sessions SET is_active=1, min_coaches=1 WHERE id=%s',
            (club_id,)
        )
    else:
        club_id = conn.execute(
            '''INSERT INTO sessions
               (day_of_week, start_time, end_time, location, programs,
                min_coaches, max_coaches, notes, is_active)
               VALUES ('Tuesday', '07:00', '08:30', 'Peninsula Grammar',
                       'Run Club', 1, 3, '', 1)
               RETURNING id'''
        ).fetchone()['id']

    conn.execute(
        '''INSERT INTO session_overrides (session_id, term_id, start_date, end_date)
           VALUES (%s, %s, %s, %s)
           ON CONFLICT (session_id, term_id)
           DO UPDATE SET start_date=EXCLUDED.start_date, end_date=EXCLUDED.end_date''',
        (club_id, term4_id, '2026-10-27', '2026-12-08')
    )
    # This is a Term 4-only addition, including if more terms are added later.
    other_terms = conn.execute(
        'SELECT id, start_date FROM terms WHERE id <> %s', (term4_id,)
    ).fetchall()
    for term in other_terms:
        day_before = (date.fromisoformat(str(term['start_date'])) - timedelta(days=1)).isoformat()
        conn.execute(
            '''INSERT INTO session_overrides (session_id, term_id, start_date, end_date)
               VALUES (%s, %s, NULL, %s)
               ON CONFLICT (session_id, term_id)
               DO UPDATE SET start_date=NULL, end_date=EXCLUDED.end_date''',
            (club_id, term['id'], day_before)
        )


def _ensure_coach_statuses_and_term4_availability(conn):
    """Keep coach status and Term 4 availability changes durable."""
    conn.execute(
        "UPDATE coaches SET is_active=0 WHERE username IN (%s, %s)",
        ('sami', 'sarai')
    )
    conn.execute(
        "UPDATE coaches SET is_active=1, is_standby=1 WHERE username=%s",
        ('blake',)
    )

    isabella = conn.execute(
        "SELECT id FROM coaches WHERE username=%s OR name=%s",
        ('isabella', 'Isabella Avendano')
    ).fetchone()
    if isabella:
        isabella_id = isabella['id']
        conn.execute(
            '''UPDATE coaches
               SET name=%s, username=%s, mobile=%s, role=%s, level=%s,
                   is_active=1, is_standby=0
               WHERE id=%s''',
            ('Isabella Avendano', 'isabella', '+61412116212',
             'Coach', 'Level 1', isabella_id)
        )
    else:
        coach_password = os.environ.get('DEFAULT_COACH_PASSWORD')
        if not coach_password:
            coach_password = _secrets.token_urlsafe(16)
        isabella_id = conn.execute(
            '''INSERT INTO coaches
               (name, username, email, mobile, role, level, is_admin,
                is_standby, is_active, password_hash)
               VALUES (%s, %s, NULL, %s, %s, %s, 0, 0, 1, %s)
               RETURNING id''',
            ('Isabella Avendano', 'isabella', '+61412116212',
             'Coach', 'Level 1', generate_password_hash(coach_password))
        ).fetchone()['id']

    term4 = conn.execute(
        "SELECT id FROM terms WHERE name=%s",
        ('Term 4 2026',)
    ).fetchone()
    blake = conn.execute(
        "SELECT id FROM coaches WHERE username=%s",
        ('blake',)
    ).fetchone()
    declyn = conn.execute(
        "SELECT id FROM coaches WHERE username=%s",
        ('declyn',)
    ).fetchone()
    if term4 and blake:
        conn.execute(
            "DELETE FROM roster_entries WHERE term_id=%s AND coach_id=%s",
            (term4['id'], blake['id'])
        )
        conn.execute(
            '''INSERT INTO availability_responses
               (coach_id, term_id, weekly_availability, unavailable_dates,
                notes, submitted_at)
               VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
               ON CONFLICT (coach_id, term_id) DO UPDATE SET
                   weekly_availability=EXCLUDED.weekly_availability,
                   unavailable_dates=EXCLUDED.unavailable_dates,
                   notes=EXCLUDED.notes,
                   submitted_at=CURRENT_TIMESTAMP''',
            (blake['id'], term4['id'],
             json.dumps({day: 'unavailable' for day in
                         ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']}),
             json.dumps([]),
             'Unavailable for all Term 4 shifts; standby coach only.')
        )

    if term4:
        conn.execute(
            '''INSERT INTO availability_responses
               (coach_id, term_id, weekly_availability, unavailable_dates,
                notes, submitted_at)
               VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
               ON CONFLICT (coach_id, term_id) DO UPDATE SET
                   weekly_availability=EXCLUDED.weekly_availability,
                   unavailable_dates=EXCLUDED.unavailable_dates,
                   notes=EXCLUDED.notes,
                   submitted_at=CURRENT_TIMESTAMP''',
            (isabella_id, term4['id'],
             json.dumps({
                 'Monday': 'unavailable',
                 'Tuesday': 'all',
                 'Wednesday': 'unavailable',
                 'Thursday': 'all',
                 'Friday': 'unavailable',
             }),
             json.dumps([]),
             'Available Tuesdays and Thursdays for Term 4.')
        )

    if term4 and declyn:
        conn.execute(
            '''INSERT INTO availability_responses
               (coach_id, term_id, weekly_availability, unavailable_dates,
                notes, submitted_at)
               VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
               ON CONFLICT (coach_id, term_id) DO UPDATE SET
                   weekly_availability=EXCLUDED.weekly_availability,
                   unavailable_dates=EXCLUDED.unavailable_dates,
                   notes=EXCLUDED.notes,
                   submitted_at=CURRENT_TIMESTAMP''',
            (declyn['id'], term4['id'],
             json.dumps({
                 'Monday': 'all',
                 'Tuesday': 'standby',
                 'Wednesday': 'all',
                 'Thursday': 'standby',
                 'Friday': 'standby',
             }),
             json.dumps([]),
             'Available Mondays and Wednesdays; standby Tuesday, Thursday, and Friday for Term 4.')
        )

    conn.commit()


def _seed_training_sessions(conn):
    sessions = [
        (1,'100m & 200m start practice','1 x30m, 1 x40m & 1x 50m Block starts\nRest = 3mins, 4 mins & 5mins\n2x50m bend - 5mins break\n1 x100m (50m bend + 50m straight) 6mins break\n1 x120m sprint','Technical','Multi','Competition','High'),
        (2,'100m Race preparation work','100m work\n3 x 30m sprints - 3mins rest between\n2 x 60m sprints - 6 mins rest between\n2 x 100m - 10-12mins or Full recovery','Speed','100m','Competition','Max'),
        (3,'100m Tempo / Speed Endurance','5min jog, active warmup\n5min running drills\n4 x 60m run throughs\n2 Sets of 3-4x100m WB +1min to be fresh -\nHold form and run tall, no quicker than 80%\n6 mins break between sets','Speed_Endurance','100m','Base','Moderate'),
        (4,'100m form runs','Extended In & Out Warm Up\nStretches, Activation and SMR\n4 x 50m run throughs\n3 x 10 x Wickets at 5-6 "shoe" spacing - 5min break (20m fast run in)\n2 x 3 x 100m relaxed form runs - WB + 1 min\n8 mins betweens sets','Technical','100m','Base','Moderate'),
        (5,'100m or 400m preparation work','100m / 200m work\n3 x 30m sprints - 2mins rest between\n2 x 60m sprints - 5 mins rest between\n2 x 100m - 10 mins or Full recovery\n1 x 150m\n200m = FAST 1 x 100 - 150 - 200m (10 mins between reps)\n400m work - Split 400s\n2 x 60m bend ( Race start setup )\n1 x 300m 400m start to top bend - 10-12mins recovery\n1 x 200m (200m start to 400 Finish mark) 8mins recovery\n1 x 100m to Finish line','Speed','Multi','Competition','High'),
        (6,'150-80s','Active warmup and running drills\n4x60m run throughs\n*Short Hill Sprints*\n3 x10 sec hill - WB = 60-90secs recovery\n2 x13-15sec hill - WB = 2/2:30mins\n4 x 150m, WB 80m, run 80m\nWalk 250m recovery','Speed_Endurance','Multi','Competition','High'),
        (7,'150m speed endurance building session','Dynamic warmup + running drills\n4 x 60m run throughs\n5 x 40m Sprints, 2mins recovery\n3 x 3 x 150m - Walk / Jog / Walk Recovery\n4mins between sets\nBodyweight circuit x 2','Speed_Endurance','Multi','Base','High'),
        (8,'2 x 2km Tempo','2 x 2km steady @4 to 4:30min pace - 5mins between reps','Aerobic','General','Base','Moderate'),
        (9,'200m Endurance Session 1','5 mins jog\n5 x Running drill circuit\n4 x 60m run throughs on track or grass\n3-4 x 30 - 40m bend starts\n2 x 3 x 200m@90% - walk 200m recovery (5-6mins between reps)\n8 mins between sets\nGym session','Speed_Endurance','200m','Base','High'),
        (10,'200m endurance Session 2','5 mins jog\n5 x Running drill circuit\n4 x 60m run throughs on grass\n3-4 x 30 - 40m bend starts\n2 x 3 x 200m - walk 200m recovery\n8mins after 3\n*variation - 2 x 120, 150, 250m - 5mins rest\n8mins after each set','Speed_Endurance','200m','Base','High'),
        (11,'200m prep work','2 x 40m bend starts - 4mins\n2 x 70m bend starts - 6 mins\n2 x 150m - FAST\n10mins Break, then 12mins after 2\n1 x 250m in 30 secs or under\n4 x 60m ease down runs and stretching','Speed','200m','Competition','High'),
        (12,'200m preparation - Split 200','4 x 20m sprints\n3 x 30m sprints\n2 x 50m bend,\n3 x 120m, 1min break, sprint back 80m\n6 mins Break','Speed','200m','Competition','High'),
        (13,'200m preparation work','3 x 30m sprints\n2 x 50m sprints\n2 x 40m bend, 2 x 60m bend\n2 x 100m - 50m bend, 50m straight\n2 x 150m, 1 x 200m, 1 x 250m 6-8mins between reps','Speed','200m','Competition','High'),
        (14,'200m preparation work 2','3 x 30m sprints\n2 x 50m sprints\n2 x 60m bend, 2 x 80m (40m & bend into straight)\n2 x 120m @90% 6mins between reps\nAthletes running at 95% = 8mins Recovery\n10mins Break\n2 x 200m @90%\n10mins between reps','Speed','200m','Competition','High'),
        (15,'250 - 150 (400m session)','4 x60m RT\n2 x 250 / 150m in 35-40sec 3-4mins between 250m\n10 min break between sets\n4 x 70m Strides\nAb Circuit','Speed_Endurance','400m','Competition','Max'),
        (16,'3-5 km at a steady pace','can also be done as 2 x 2km, with 5min rest and stretch in between','Aerobic','General','Transition','Low'),
        (17,'3km run','Easy run at a pace that you can have a chat','Aerobic','General','Transition','Low'),
        (18,'400+ 150 tempo session','After Warmup and Short Sprints\n400m 5mins rest\n4x150m 2mins rest\n400m 5mins rest\nEase down run throughs and stretching','Speed_Endurance','400m','Competition','High'),
        (19,'400m Endurance building session','Dynamic warmup and running drills\n4 x 60m run throughs\n4 x 300m @80% - 6mins recovery\n8mins between sets\nOR - 4 x 500m with 6mins rest\n5 x 80m runs @ 80%- Recovery = WB in 1min\nCore workout circuit','Speed_Endurance','400m','Base','High'),
        (20,'400m Gut buster','In and Out warmup\nActive stretching exercises and Core activation\n(leg swings, squats, plank, plank with leg left)\n3 - 4 x 80m RTs\n2 x 300 - 80 - 70m @90%\nRun 300, rest 1min, Run 80m to finish, WB to 70m, run to finish, then walk a slow lap in 6-8mins\nThen repeat\n4 x 50m Easy Stride Run throughs to help the legs recover','Speed_Endurance','400m','Competition','Max'),
        (21,'400m prep - 350 / 250','Active Warmup and running drills\n4 x 60m run throughs\n3 x 40m sprints - Straight\n2 x 70m sprints - Bend\n1 x 350m , 1 x 250m - 15mins break','Speed_Endurance','400m','Competition','Max'),
        (22,'400m prep session - Speed Endurance','4 x60m run throughs\n3 x 50m sprints - 5 mins rest between each\n2 x 2 x 200m @90% 8mins rest between reps\n15mins break after 1st set\n(Target time = 25 secs or under)','Speed_Endurance','400m','Competition','High'),
        (23,'400m race tempo 200s','4 x60m run throughs\n3 x40m sprints - Straight - 3mins rest between each\n3 x 200m at 400m race pace\n10 - 12 mins break between each','Speed_Endurance','400m','Competition','High'),
        (24,'400m speed endurance','3x30m block starts\n2x50m block starts\n300m @90%\nWalk 150m in 3mins recovery\n150m @90%\nWalk back 70m / 2mins rest\n70m hold form\nWalk 1 lap in 6mins\nRepeat','Speed_Endurance','400m','Base','High'),
        (25,'400m speed endurance work 1','2 Lap jog\nSquats, leg swings, Skipping drills\nRunning drills x 2 each\n3-4 x 80m RTs\n4 x 20m fast starts\n3 x 50m sprints - 2mins rest between each\n2 x 250m @80% effort - walk 80m - sprint 70m to finish.\nRest is walk 1 lap in 5-6mins\n5-10 mins Stretching','Speed_Endurance','400m','Base','High'),
        (26,'800 - 1500m workout 1','600m @ 1500m pace 3mins Rest\n4x200m @800m pace 90 secs rest, then 3mins break\n600m @1500m pace','Speed_Endurance','800_1500m','Base','High'),
        (27,'800m prep & Race sim','Active / Skipping warmup\nRunning drills\n4 x 50m Run throughs\nSprint work x 3 reps\n300m @90% - 5mins rest\n200m @90% - From 300m start - 4mins rest\n200m from 200m start - 5mins rest\n120m or 150m\n1 lap easy jog or 4 x 60 ease down runs\nStretching','Speed_Endurance','800_1500m','Competition','High'),
        (28,'Acceleration Development 1 (INTRO)','3 - 4 SETS x Accel Ladder 20 / 30 / 40m = 300 - 400m\nRECOVERY = 2, 3 & 4 mins\n3 x Jumping and Bounding Drills over 30 - 40m = 200m\nTechnical Form Running = 4 x 100m @90% = 400m\nMedball Circuit x 3','Speed','General','Pre_season','Moderate'),
        (29,'Acceleration and Speed Endurance','3x20m sprints :1min break\n2x30m Sprints : 2 mins break\n2x40m Sprints : 3mins break\n2 x 4 x 80m / 45 secs recovery\n4 mins between sets','Speed_Endurance','General','Base','High'),
        (30,'Agility and Speed Endurance 1','5min jog, active warmup\n5 min Balance and Activation\n5min running drills\n3-4 x 60m run throughs\n4 x 4 cone tennis ball drill ( set cones up 4m apart in a square)\n1-2mins between reps\n4 x Agility / Zig Zag runs over 20-30m\nShort Sprints - 3 x 40m\n3 x 120m build up runs (40m 50%, 40m 75%, 40m 100% effort)\n4mins recovery\n1 x 250m Run','Speed_Endurance','General','Base','High'),
        (31,'Agility and Speed Endurance 2','5min jog, active warmup\n5 min Balance and Activation\n5min running drills\n3-4 x 60m run throughs\n3x30m, 2x50m, 2x80m WB +1min to be fresh\n3-4 150m build up runs - 50m@50%, 50m@75%, 50m@100% - 3mins recovery\nAb & Back exercises','Speed_Endurance','General','Base','High'),
        (32,'Athletic Performance Testing','Using Electronic Timing Gates and Jump Mat\n20m Sprint x 2\n60m sprint x 2\n150m Sprint\n300m (for 400m athletes)\nVertical Jump x 3\nStanding Long Jump','Testing','General','Base','Max'),
        (33,'Block Starts + Max V','Heavy Sled x 20m\nBlock Starts x 30m / 40m out to 50m\nFlying 30 x 2\nMed Ball Throws and Sandpit Jumps','Speed','Multi','Competition','High'),
        (34,'Block Starts and Max V Work','Block Starts x 4 x 40m\n3 x 75m - In & Outs (15m Accel, 15m Maintain - 3 Accels)\n6 mins between reps\n3 x120m - hard bend relaxed straight\n5 mins recovery','Speed','Multi','Competition','High'),
        (35,'Footy Boys session 1','Acceleration, Speed and Form running\nIn & Outs 20, on, 20m off, 20m on x 4\n60m, 80m, 120m x 2\n3 - 4 x 250m, walk 150m recovery\nLateral Hurdle jumps','Speed','Team_Sport','Base','Moderate'),
        (36,'Hills + Track','5 x 10sec hill, 1min WB recovery\n5mins break\n4x30m sprints, 1 min recovery\n4mins\n3 x 60m on/off 15m on, 10m off\n5x60m Jog/WB/Jog/WB/Jog','Speed_Endurance','General','Base','High'),
        (37,'Hills + Track (150s)','5 x 15sec hill, 1min WB recovery\n5mins break\n10m "roll in" into 4x30m sprints, 1 min recovery\n4mins\n2 x 2 x 150m - 2 mins rest between sets\n4 mins Break between sets','Speed_Endurance','General','Base','High'),
        (38,'Hills and Track Workout','5 min jog\nRunning Drills and Active Warmup\n4x60m Run throughs\n4 x 30m sprints - WB\n400/800m Runners = 4 x 90 sec gravel trail - 3mins rec\n100/200m runners = 5 x 20 sec efforts\nAll = 5 x 10 sec hill - WB + 30 secs\nTrack\n3 x 120 or 150m Reps - WB\nPowerband and Mini band strength exercises','Speed_Endurance','General','Base','High'),
        (39,'Long Speed Endurance - Ladder Down','2 lap easy jog\nRunning drills\n4 x 60m Run throughs\n500m, 400m, 300m, 200m, 100m\nRecoveries are 4min,3min,2min,1min, so judge your pace!\n1 lap easy jog or 4 x 60 ease down runs\nStretching','Speed_Endurance','400m','Base','High'),
        (40,'Long Speed Endurance - Ladders','2 lap easy jog\nRunning drills\n4 x 60m Run throughs\n500, 300m, 100, 300m, 500m\nRecoveries are 5min,3min, 1min, 3min, so judge your pace!\n1 lap easy jog or 4 x 60 ease down runs\nStretching','Speed_Endurance','400m','Base','High'),
        (41,'Max V and Speed session','3 x 30m Accels from 3 point start\n2 x 12 wickets with 20m run in and 5 stride gap\n6 mins recovery\n1 x 60 - 80 - 120\nRest = 6mins between reps','Speed','General','Competition','High'),
        (42,'Plyo Intro + Speed Endurance','Dynamic warmup + drills\n5 x standing long jumps\n4 x 20m bounding\n5 x 20m accelerations over low hurdles\n(1min rec between reps)\n5 x 100m @80%\n4mins recovery between reps\n4 x 20-30m resisted harness or sled pulls\nBodyweight circuit','Plyo_Power','General','Base','High'),
        (43,'Short Fartlek','5-6min jog warmup and Active stretches\n(squats, leg swings, inchworm & spidermans)\n3x60m run throughs\n4x30sec run, 30 sec jog - 3mins rest\n3x1min run, 1min jog\n2x2min run, 2mins rest','Aerobic','General','Transition','Moderate'),
        (44,'Sled PUSH and Max V','4 x 50m Run throughs\nHeavy Sled PUSHES x 20m x 3 reps - Superset with 3 x 30m Sprints\nFlying 30m over "wickets" x 3 - 6 mins break\nMed Ball Throws -\nUnderhand throw 2 x10\nAb Slams 2 x 10\nRotation Side throws 2 x 10 each side','Speed','General','Base','High'),
        (45,'Sled Push and Max V','4 x 50m Run throughs\nSled Push x 20m x 3 reps - Superset with 3 x 30m Sprints\nFlying 30m over "wickets" x 3 - 6 mins break\n2 x 70-80 run - 8 mins rest\nMed Ball Throws -\nUnderhand throw 2 x10\nAb Slams 2 x 10\nRotation Side throws 2 x 10 each side','Speed','General','Base','High'),
        (46,'Sled Push, Max V and Wickets','Heavy Sled x 20m\nBlock Starts x 30m / 40m out to 50m\nFlying 30 x 2 (Wicket runs?)\nMed Ball Throws and Sandpit Jumps','Speed','General','Base','High'),
        (47,'Sled Towing and Max V','4 x 50m Run throughs\n3 Point or Block Starts\nSled towing x 20m x 3 reps - Superset with 3 x 30m Sprints\nFlying 30m over "wickets" x 2 - 6 mins break\nMed Ball Throws -\nUnderhand throw 2 x10\nAb Slams 2 x 10\nRotation Side throws 2 x 10 each side','Speed','General','Base','High'),
        (48,'Speed Endurance 2 - Ladder Up & Down','2 lap easy jog\nRunning drills\n4 x 60m Run throughs\n5 x 30m sprints - Wb + 1 min recovery\n150 - 200 - 250 - 250 - 200 -150m\nRecovery = 4, 5, 6, 8, 6, 4mins between reps\n4 x 70m ease down run throughs and stretching','Speed_Endurance','Multi','Base','High'),
        (49,'Speed Endurance Building Session 1','5min jog, Active warmup\n5 min Balance and Activation\n5min running drills\n3-4 x 80m run throughs\n2 sets of 4 x 100m @ 80% WB recovery\nBodyweight Exercises & Core','Speed_Endurance','General','Base','Moderate'),
        (50,'Speed Endurance Combo session 2','Focussed Speed Drills\nMedball Push Pass starts - 4 x 20m\n2x5x80m @10-12secs, 60 sec break\n3mins between sets\n2 x 200m, walk 100m, run 100m - 4 mins break','Speed_Endurance','General','Base','High'),
        (51,'Speed Endurance Ladder','1 Lap jog, running drills and stretches\n4 x 50m Run throughs\n3 x 20m Sprint starts - FAST\n2 Sets of:\n50m @90% - WB + 1 min rest\n70m @90% - WB + 90 secs rest\n90m @90% - WB + 2mins rest\n120m @90% - 5 mins break\nRepeat in Reverse order\n5mins break then\n1 x 250m @80%\n4 x 30 sec Hill - WB - 3min rest after 4\n4-5 x 1min hill run, jog 30 secs, walk 1 min\n4-5 mins rest\nAb & Back exercise circuit','Speed_Endurance','Multi','Competition','High'),
        (52,'Speed Endurance Session 1','5min jog, Active warmup\n5 min Balance and Activation\n5min running drills\n3-4 x 60m run throughs\n1 x 60m, 80m, 100m @ 80% WB recovery +1min\n2 Sets of Speedmakers - 5xSprint 50m, Jog 50m, Walk 50m\n3 x 5 Double Leg Jumps for distance (measure it)\n3 x 6 Jumps onto a bench or stairs ( for height)','Speed_Endurance','General','Base','Moderate'),
        (53,'Speed Endurance Session 2','5min jog, Active warmup\n5 min Balance and Activation\n5min running drills\n3-4 x 60m run throughs\n2 x 4 x 80m @75%- rest 30 secs and run back\n2 Sets High bench stepup - 8-10 each leg\n2 Set of 5 hops for distance each leg','Speed_Endurance','General','Base','High'),
        (54,'Speed Endurance Session 3','5min jog, Active warmup\n5 min Balance and Activation\n5min running drills\n3-4 x 60m run throughs\n3 x 30m flying starts - 5m rolling start\n2 x 50m flying starts - 5 m rolling start\n2 Set of 4 x 80m sprints @70% effort\nJog back, walk back, jog back, walk back Rec\n5min break, then do 2nd Set','Speed_Endurance','General','Base','High'),
        (55,'Speed Endurance Session 4','5min jog, Active warmup\n5 min Balance and Activation\n5min running drills\n3-4 x 60m run throughs\n4 x 30m block starts - WB + 1min\n4 x 120m sprints @70% effort\nJog back, walk back, jog back, walk back Rec\n5min break\n3 x 200m - WB, Jog back, WB recovery','Speed_Endurance','General','Base','High'),
        (56,'Speed Endurance Session 5','In & Out Warm up - Run 100m, jog/skip 50m, walk 50m (Until you have run 3 laps)\nActive Stretches\nRunning drills\n3 x 30m stand starts - WB\n2 x 60m sprints WB + 1-2mins\n6x200m@80%\nRec 3-4 mins rest\nLeg Circuit','Speed_Endurance','General','Base','High'),
        (57,'Speed Session + hills','5min jog, Active warmup\n5 min Balance and Activation\n5min running drills\n3-4 x 60m run throughs\n3 x 30m sprints\n2x 60m sprints\n4 x 15sec sec hill - WB in 1min\n(incline to be steep enough to encourage a strong knee and arm drive up the hill)\n4 x 100m @ 80% WB recovery +1min if needed','Speed','General','Base','High'),
        (58,'Speed Session 1','5min jog, Active warmup\n5 min Balance and Activation\n5min running drills\n3-4 x 60m run throughs\n3 x 30m Accelerations\n2 x 60m sprints\n1 x 100 - 120 - 150m 6-8mins between reps\nStretching','Speed','General','Base','High'),
        (59,'Speed and Agility for Team Sport','Dynamic warmup + drills\n3 x Compass Drill\n5 x standing long jumps + 20m sprint\n4 x 20m bounding\n5 x 20m accelerations over low hurdles\n(1min rec between reps)\n5 x 100m @80%\nWalk back recovery between reps','Speed','Team_Sport','Base','Moderate'),
        (60,'Speed and Power Testing','Standing Long jump - 2 attempts\n150m sprint - 1 attempt\n20mins break\n300m run - 1 attempt','Testing','General','Base','Max'),
        (61,'Speed and Speed Endurance','5min jog, active warmup\n5 min Balance and Activation\n5min running drills\n4 x 60m run throughs\n4x20m fast sprints, block or 3 point start\n3x60m blocks or standing start\n2 Sets of 4x100m WB +1min to be fresh -\nHold form and run tall, no quicker than 80%\nAb & Back exercises','Speed_Endurance','General','Base','High'),
        (62,'Speed session for 200m','5min jog, Active warmup\n5 min Balance and Activation\n5min running drills\n4 x 50m run throughs\n3 x 30m Accelerations\n2 x 60m sprints\n3 x 100m fast 5mins between reps\n1 x 200m @90% 8mins\n1 x 250m @90%\nStretching','Speed','200m','Competition','High'),
        (63,'Speed week - Race Sim for 400m','1 lap jog and skipping warmup\n4 sets of each running drill\n4 x 60m run throughs\n3 x 20-30m block starts or 3 point start\n3 x 40m sprints from 400m start\n1 x 350m @ 400m Race pace - 10mins rest\n1 x 250m @ 400m Race pace - 10mins rest\n1 x100m @200m race pace\nWalk 5mins and stretch','Speed_Endurance','400m','Competition','Max'),
        (64,'Speedweek Sprint Session','In & Out Warmup + Dynamic Stretching\nSpeed Drills and Activation\n3x80m Run throughs\n2 x 40m Block Starts, 2 x 60m Bend starts\n3 x 150m @ 80%\n1 x 300m','Speed','Multi','Competition','High'),
        (65,'Sprint and Plyo Session','In & Out Warmup + Dynamic Stretching\nSpeed Drills and Activation\n4x60m Run throughs\nBounding starts - 20m bound, 20m sprint - Grass\n3 x50m Block Starts, 4 x100m @ 90% 5mins recovery between reps\n3 x 150m - Walk Back recovery\nDouble leg jumps and Hops for Distance - 2 sets of 20m','Plyo_Power','Multi','Competition','High'),
        (66,'Start Practice and Speed Session 1','5min jog, Active warmup\n5 min Balance and Activation\n5min running drills\n3-4 x 80m run throughs\nStart practice for 100m - 4 x 30m\nStart practice for 200m 3 x 50m bend\nForm Runs - 80,100,120,150m\nBodyweight Exercises & Core','Technical','Multi','Competition','High'),
        (67,'Starts and 200m work','4x60m RT\n4 x30 starts\n3x50m\n1 x 150, 200, 250m - 5, 8-10 mins between reps','Speed','200m','Competition','High'),
        (68,'Stawell Grass prep','Setup blocks on Grass for start practice\nmark out 120m\n40m Blocks x 2 : 3 - 4mins break\n60m blocks x 2 : 5 mins break\n2 x 100m (diagonals) 6mins break','Technical','Multi','Competition','Moderate'),
        (69,'Technical Session - Block set-ups and Start Execution','Standing start with Back Block push-off 3 x 20m\nBlock start 3 x 30m - 3 mins rest\nBlock Starts 2 x 40m - 4 mins rest\n2 x Flying 30m - 20m run in (50m Total)\n6 mins between reps\nMedball Throws. - 2 sets\nChest pass x 8\nUnderhand FWD Throw x 8\nOverhead FWD Throw x 8','Technical','Multi','Competition','High'),
        (70,'Tempo Sandwich','1km warmup run\nActive stretches and Running Drills\n5min tempo - 2 min rest\n4 x 30 sec hard/30sec easy - 3mins rest after the 4 hard efforts\n(30 secs easy is an "active" recovery)\n5min tempo','Aerobic','General','Transition','Moderate'),
        (71,'Transition Week 1 - Session 1','In and Out warm up with skipping drills\nMobility and activation exercises\nExtensive running drills - focus on Form and execution\n4 x 60m Run throughs\n3 x 10m Roll in 40m Accelerations\n5 x 80m relaxed runs - WB recovery\nSandpit bear crawls & inchworms\nAb - Flutter kicks and Planks','Speed','General','Transition','Low'),
        (72,'Transition Week 1 - Session 2','In and Out warm up with skipping drills\nMobility and activation exercises\nExtensive running drills - focus on Form and execution\n4 x 60m Run throughs\n2 x 20m Straight leg bound into 30m Accelerations\n2 x 20m Speed Bound into 30m Acceleration\n2 x 4 x 100m relaxed runs - WB recovery\n4mins between Sets\nCool down static stretches - 10mins','Speed','General','Transition','Low'),
        (73,'Transition Week 2 - Session 1','Continuous Warm-up\nExtensive running drills - focus on Form and execution\n4 x 60m Run throughs\n4 x 20m Accel - 20m "Roll", 20m Accel, then coast down\n2 x 4 x 80m relaxed runs ( Up and Backs ) 30 secs recovery\n5mins between sets\nCore x 2 Sets x 10 reps of each: Double leg lifts, Plank with shoulder taps, V-Sit, Side plank\nCool down static stretches - 10mins','Speed_Endurance','General','Transition','Moderate'),
        (74,'Transition Week 2 - Session 2','In and Out warm up with skipping drills\nMobility and activation exercises\nExtensive running drills - focus on Form and execution\n4 x 60m Run throughs\n2 x 20m Straight leg bound into 30m Accelerations\n2 x 20m B Skip into 20m Acceleration\n3 x 120m relaxed runs - WB recovery\n4mins Break\n2 x Run 200m, walk 200m @70-80%\nCool down static stretches - 10mins','Speed','General','Transition','Moderate'),
        (75,'Transition Week 3 - Session 1','Continuous Warm-up\nExtensive running drills - focus on Form and execution\n4 x 60m Run throughs\n5 x 20m Accelerations - WB + 1min\n5 x 70m - WB recovery\n5mins Break\n2 x 250m - walk 200m recovery, run 150m - 4 mins rest & repeat\nCore x 2 Sets x 10 reps of each: Double leg lifts, Plank with shoulder taps, V-Sit, Side plank','Speed_Endurance','General','Transition','Moderate'),
        (76,'Transition Week 3 - Session 2','In and Out warm up with skipping drills\nMobility and activation exercises\nExtensive running drills - focus on Form and execution\n4 x 60m Run throughs\n2 x 3 x 150m relaxed runs - WB recovery\n4mins Break\nCool down static stretches - 10mins','Speed_Endurance','General','Transition','Moderate'),
        (77,'Transition Week 4 - Session 1','Continuous Warm-up\nExtensive running drills - focus on Form and execution\n4 x 60m Run throughs\n5 x 20m Accelerations - WB + 1min\n4 x 100m (or 13-15 sec) Grass or Track runs - 90 secs - 2min WB recovery\n5mins Break\n2 x 200m - walk 200m recovery in 4-5mins','Speed_Endurance','General','Transition','Moderate'),
        (78,'Transition Week 4 - Session 2','In and Out warm up with skipping drills\nMobility and activation exercises\nExtensive running drills - focus on Form and execution\n4 x 60m Run throughs\nTraffic Light Drill for warmup\n4-5 x 10-15min 2 point starts with feedback\n2 x 4 x 80 / 40m @80% (run 80m, 30sec rest, run back 40m / 1min rest)\n5 mins Break\nCore Circuit x 2 - flutter kicks, Hollow rocks and Plank with alternating leg lifts\nCool down static stretches - 10mins','Technical','General','Transition','Moderate'),
        (79,'Wickets and Max V Session 1','Muscle activation and Active Warmup Drills\n4 x 50m Run throughs\n18w at 6 step spacing - 4 sets\nSpeed Bounding over 30m x 3 - 4\n3 x Flying 30m (20m run in)\n3 x 60 - 80m bend runs','Speed','General','Base','High'),
    ]
    conn.executemany(
        '''INSERT INTO public.training_sessions
           (id, name, description, session_type, event_group, training_phase, intensity_level)
           VALUES (%s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (id) DO NOTHING''',
        sessions
    )


def _seed_coaches(conn):
    # A fresh database must have an administrator credential supplied securely.
    admin_pw = os.environ.get('APP_ADMIN_PASSWORD')
    if not admin_pw:
        raise RuntimeError('APP_ADMIN_PASSWORD must be configured before seeding coach accounts')

    # When no initial coach password is configured, only the admin can set one
    # for each coach; never expose a generated shared password in server logs.
    coach_pw = os.environ.get('DEFAULT_COACH_PASSWORD')

    admin_hash = generate_password_hash(admin_pw)
    coach_hash = generate_password_hash(coach_pw) if coach_pw else None

    coaches = [
        ('Alistair Tait', 'alistair', 'alistair@power2adapt.com', None,
         'Head Coach & Director', 'Level 3', 1, 0, admin_hash),
        ('Sami Merhi', 'sami', None, '+61478878827',
         'Performance Coach', 'Level 3', 0, 0, coach_hash),
        ('Georgia Middleton', 'georgia', None, '+61406344060',
         'Development Coach - Junior Development & Sprints', 'Level 2', 0, 0, coach_hash),
        ('Ella Wilson', 'ella', None, '+61455229300',
         'Community Coach - Foundation Program Lead', 'Level 1', 0, 0, coach_hash),
        ('Sarai Hughes', 'sarai', None, '+61419977570',
         'Development Coach - Jumps', 'Level 2', 0, 0, coach_hash),
        ('Geena Davy', 'geena', None, '+61436359756',
         'Development Coach - Jumps', 'Level 2', 0, 0, coach_hash),
        ('Declyn Tanner', 'declyn', None, '+61424740608',
         'Development Coach - Middle Distance', 'Level 2', 0, 0, coach_hash),
        ('Miah Noble', 'miah', None, '+61423634161',
         'Community Coach - Endurance & Personal Training', 'Level 1', 0, 0, coach_hash),
        ('Blake Ireland', 'blake', None, None,
         'Coach', 'Level 2', 0, 1, coach_hash),
    ]
    conn.executemany('''
        INSERT INTO coaches (name, username, email, mobile, role, level, is_admin, is_standby, password_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', coaches)


def _seed_sessions(conn):
    sessions = [
        ('Monday',    '15:00', '17:00', 'Peninsula Grammar',          'Foundation, Emerging',          4, 6, '3pm setup required'),
        ('Monday',    '17:30', '19:00', 'Ballam Park',                'Junior Academy, Senior Squad',  2, 4, ''),
        ('Tuesday',   '07:00', '08:15', 'Peninsula Grammar',          'School Program',                2, 3, '7am setup required'),
        ('Tuesday',   '16:30', '17:30', 'Ballam Park',                'Emerging, Junior Academy',      2, 3, ''),
        ('Tuesday',   '17:30', '19:00', 'Ballam Park',                'Junior Academy, Senior Squad',  2, 4, ''),
        ('Wednesday', '16:30', '18:00', 'Mornington Athletics Track', 'Foundation, Emerging',          2, 4, '4:30pm setup required'),
        ('Wednesday', '17:30', '19:00', 'Mornington Athletics Track', 'Team Sport Speed',              1, 2, ''),
        ('Thursday',  '15:00', '17:00', 'Toorak College',             'Foundation, Emerging',          4, 6, '3pm setup required'),
        ('Friday',    '16:30', '17:30', 'Mornington Athletics Track', 'Team Sport Speed',              1, 2, ''),
        ('Friday',    '17:30', '19:00', 'Mornington Athletics Track', 'Team Sport Speed',              1, 2, ''),
    ]
    conn.executemany('''
        INSERT INTO sessions (day_of_week, start_time, end_time, location, programs, min_coaches, max_coaches, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', sessions)


def _seed_terms(conn):
    terms = [
        ('Term 1 2026', 2026, 1, '2026-01-28', '2026-03-27'),
        ('Term 2 2026', 2026, 2, '2026-04-20', '2026-06-26'),
        ('Term 3 2026', 2026, 3, '2026-07-14', '2026-09-18'),
        ('Term 4 2026', 2026, 4, '2026-10-05', '2026-12-18'),
    ]
    conn.executemany('''
        INSERT INTO terms (name, year, term_number, start_date, end_date)
        VALUES (?, ?, ?, ?, ?)
    ''', terms)


def _seed_overrides(conn):
    # Session IDs: 1=Mon PG 3pm, 3=Tue PG 7am, 8=Thu Toorak
    # These end June 19 for Term 2 (id=2); other sessions run to June 26
    overrides = [
        (1, 2, None, '2026-06-19'),
        (3, 2, None, '2026-06-19'),
        (8, 2, None, '2026-06-19'),
    ]
    for ov in overrides:
        conn.execute('''
            INSERT INTO session_overrides (session_id, term_id, start_date, end_date)
            VALUES (%s, %s, %s, %s) ON CONFLICT (session_id, term_id) DO NOTHING
        ''', ov)


def _seed_fixtures(conn):
    fixtures = [
        ('AGSV Round 1',              '2026-04-22', 'Marcellin College',   'Peninsula Grammar', 'Wednesday fixture'),
        ('Year 7-12 House Cross Country','2026-04-27', 'Peninsula Grammar', 'Peninsula Grammar', 'Monday 1:00pm – 3:30pm'),
        ('All Schools Road Relays',   '2026-05-02', 'Princes Park',        'Peninsula Grammar', 'Saturday fixture'),
        ('Year 4-6 House Cross Country','2026-05-04', 'Peninsula Grammar',  'Peninsula Grammar', 'Monday 11:00am – 1:00pm'),
        ('AGSV Round 2',           '2026-05-16', 'PEGS, Keilor Park',    'Peninsula Grammar', 'Saturday fixture'),
        ('All Schools Road Relays','2026-05-23', 'Jells Park',           'Peninsula Grammar', 'Saturday fixture'),
        ('AGSV Round 3',           '2026-05-30', 'Cruden Park',          'Peninsula Grammar', 'Saturday fixture — Peninsula Grammar host'),
        ('AGSV Round 4',           '2026-06-13', 'Yarra Bend',           'Peninsula Grammar', 'Saturday fixture'),
        ('All Schools Individual', '2026-06-20', 'Bundoora Park',        'Peninsula Grammar', 'Saturday fixture'),
        ('AGSV Round 5',           '2026-07-18', 'Braeside Park',        'Peninsula Grammar', 'Saturday fixture'),
        ('AGSV Round 6',           '2026-07-25', 'Banyule Flats',        'Peninsula Grammar', 'Saturday fixture'),
    ]
    for f in fixtures:
        conn.execute('''
            INSERT INTO fixtures (title, date, location, school, notes) VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        ''', f)
        fid_row = conn.execute('SELECT id FROM fixtures WHERE title=%s AND date=%s', (f[0], f[1])).fetchone()
        if fid_row:
            sami = conn.execute("SELECT id FROM coaches WHERE username='sami'").fetchone()
            if sami:
                conn.execute('''
                    INSERT INTO fixture_coaches (fixture_id, coach_id) VALUES (%s, %s)
                    ON CONFLICT DO NOTHING
                ''', (fid_row['id'], sami['id']))


def _seed_checklist(conn):
    items = [
        # (category, item_text, requires_admin_signoff, sequence_order)

        # Before Your First Session
        ('Before Your First Session', 'Read all 5 induction modules in the Learning Hub', False, 1),
        ('Before Your First Session', 'Download the Team App and join the Power2ADAPT group', False, 2),
        ('Before Your First Session', 'Save Alistair\'s number: 0434 679 395', False, 3),
        ('Before Your First Session', 'Review the Foundation Program lesson plans (Prep–Grade 2)', False, 4),
        ('Before Your First Session', 'Review the Emerging Program lesson plans (Grade 3–Grade 6)', False, 5),
        ('Before Your First Session', 'Complete your Working With Children Check (WWCC)', False, 6),
        ('Before Your First Session', 'WWCC verified by Alistair', True, 7),

        # First Session
        ('First Session', 'Shadowed a full session with an experienced coach', False, 8),
        ('First Session', 'Session shadow signed off by Alistair', True, 9),
        ('First Session', 'Introduced to athletes and parents', False, 10),
        ('First Session', 'Familiar with session layout and equipment setup', False, 11),

        # Policies & Expectations
        ('Policies & Expectations', 'Read and understood the Code of Conduct', False, 12),
        ('Policies & Expectations', 'Understand the emergency action plan (EAP) for each venue', False, 13),
        ('Policies & Expectations', 'Know the injury reporting process', False, 14),
        ('Policies & Expectations', 'Aware of photo/social media policy for athletes', False, 15),

        # Administration
        ('Administration', 'Provided your bank details for payroll', False, 16),
        ('Administration', 'Set up on Xero Me for timesheets', False, 17),
        ('Administration', 'Timesheet setup confirmed by Alistair', True, 18),
        ('Administration', 'Added to the coaching WhatsApp group', False, 19),
    ]
    conn.executemany(
        'INSERT INTO induction_checklist_items (category, item_text, requires_admin_signoff, sequence_order) VALUES (%s, %s, %s, %s)',
        items
    )
