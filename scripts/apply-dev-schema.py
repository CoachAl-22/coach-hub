"""Development-only schema setup, run by post-merge, never by deployment startup."""
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
from database import get_db

if not os.environ.get('PGHOST') or not os.environ.get('PGDATABASE'):
    raise RuntimeError('Development PG configuration is required to apply the development schema.')

db = get_db()
try:
    db.execute((root / 'migrations' / 'coach_password_setup.sql').read_text())
    db.commit()
finally:
    db.close()