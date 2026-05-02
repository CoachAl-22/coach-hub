import sqlite3
from werkzeug.security import generate_password_hash
from config import Config


def get_db():
    conn = sqlite3.connect(Config.DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.executescript('''
        CREATE TABLE IF NOT EXISTS coaches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            day_of_week TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            location TEXT NOT NULL,
            programs TEXT,
            min_coaches INTEGER DEFAULT 1,
            max_coaches INTEGER DEFAULT 4,
            notes TEXT,
            is_active INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS terms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            year INTEGER NOT NULL,
            term_number INTEGER NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS roster_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            term_id INTEGER NOT NULL,
            session_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            coach_id INTEGER NOT NULL,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (term_id) REFERENCES terms(id),
            FOREIGN KEY (session_id) REFERENCES sessions(id),
            FOREIGN KEY (coach_id) REFERENCES coaches(id),
            UNIQUE(term_id, session_id, date, coach_id)
        );

        CREATE TABLE IF NOT EXISTS availability_responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            coach_id INTEGER NOT NULL,
            term_id INTEGER NOT NULL,
            weekly_availability TEXT DEFAULT '{}',
            unavailable_dates TEXT DEFAULT '[]',
            notes TEXT,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (coach_id) REFERENCES coaches(id),
            FOREIGN KEY (term_id) REFERENCES terms(id),
            UNIQUE(coach_id, term_id)
        );

        CREATE TABLE IF NOT EXISTS availability_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            coach_id INTEGER NOT NULL,
            term_id INTEGER NOT NULL,
            token TEXT UNIQUE NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            used INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (coach_id) REFERENCES coaches(id),
            FOREIGN KEY (term_id) REFERENCES terms(id)
        );

        CREATE TABLE IF NOT EXISTS sms_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            coach_id INTEGER,
            mobile TEXT,
            message TEXT,
            type TEXT,
            status TEXT,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    ''')

    existing = cursor.execute('SELECT COUNT(*) FROM coaches').fetchone()[0]
    if existing == 0:
        _seed_coaches(cursor)
        _seed_sessions(cursor)
        _seed_terms(cursor)
        conn.commit()

    conn.close()


def _seed_coaches(cursor):
    coaches = [
        ('Alistair Tait', 'alistair', 'alistair@power2adapt.com', None,
         'Head Coach & Director', 'Level 3', 1, 0, generate_password_hash('P2A-Admin-2026')),
        ('Sami Merhi', 'sami', None, '+61478878827',
         'Performance Coach', 'Level 3', 0, 0, generate_password_hash('CoachHub2026')),
        ('Georgia Middleton', 'georgia', None, '+61406344060',
         'Development Coach - Junior Development & Sprints', 'Level 2', 0, 0, generate_password_hash('CoachHub2026')),
        ('Ella Wilson', 'ella', None, '+61455229300',
         'Community Coach - Foundation Program Lead', 'Level 1', 0, 0, generate_password_hash('CoachHub2026')),
        ('Sarai Hughes', 'sarai', None, '+61419977570',
         'Development Coach - Jumps', 'Level 2', 0, 0, generate_password_hash('CoachHub2026')),
        ('Geena Davy', 'geena', None, '+61436359756',
         'Development Coach - Jumps', 'Level 2', 0, 0, generate_password_hash('CoachHub2026')),
        ('Declyn Tanner', 'declyn', None, '+61424740608',
         'Development Coach - Middle Distance', 'Level 2', 0, 0, generate_password_hash('CoachHub2026')),
        ('Miah Noble', 'miah', None, '+61423634161',
         'Community Coach - Endurance & Personal Training', 'Level 1', 0, 0, generate_password_hash('CoachHub2026')),
        ('Blake Ireland', 'blake', None, None,
         'Coach', 'Level 2', 0, 1, generate_password_hash('CoachHub2026')),
    ]
    cursor.executemany('''
        INSERT INTO coaches (name, username, email, mobile, role, level, is_admin, is_standby, password_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', coaches)


def _seed_sessions(cursor):
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
    cursor.executemany('''
        INSERT INTO sessions (day_of_week, start_time, end_time, location, programs, min_coaches, max_coaches, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', sessions)


def _seed_terms(cursor):
    terms = [
        ('Term 1 2026', 2026, 1, '2026-01-28', '2026-03-27'),
        ('Term 2 2026', 2026, 2, '2026-04-14', '2026-06-26'),
        ('Term 3 2026', 2026, 3, '2026-07-14', '2026-09-18'),
        ('Term 4 2026', 2026, 4, '2026-10-06', '2026-12-18'),
    ]
    cursor.executemany('''
        INSERT INTO terms (name, year, term_number, start_date, end_date)
        VALUES (?, ?, ?, ?, ?)
    ''', terms)
