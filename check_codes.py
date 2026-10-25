"""
check_codes.py — Inspect speed-assessment.online database for assessment/login codes
Run: python check_codes.py
"""
import os
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    print("❌  DATABASE_URL not found.")
    raise SystemExit(1)

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor(cursor_factory=RealDictCursor)

print("\n" + "═" * 60)
print("  speed-assessment.online — Database Code Inspection")
print("═" * 60)

# Show all tables in public schema
cur.execute("""
    SELECT table_name FROM information_schema.tables
    WHERE table_schema = 'public' ORDER BY table_name
""")
tables = [r['table_name'] for r in cur.fetchall()]
print(f"\n📋  Tables found ({len(tables)}): {', '.join(tables)}\n")

# Show clients with their identifiers
print("─" * 60)
print("  CLIENTS (potential athlete links)")
print("─" * 60)
cur.execute("""
    SELECT id, first_name, last_name, setmore_customer_id,
           email, phone
    FROM public.clients ORDER BY first_name
""")
clients = cur.fetchall()
for c in clients:
    code = c['setmore_customer_id'] or '—'
    print(f"  [{c['id']:>2}] {c['first_name']} {c['last_name']:<20} code: {code[:40]}")

# Show current athletes and their linked codes
print(f"\n{'─' * 60}")
print("  ATHLETES → LINKED CLIENT")
print("─" * 60)
cur.execute("""
    SELECT a.id, a.name, a.assessment_code,
           c.first_name, c.last_name
    FROM public.athletes a
    LEFT JOIN public.clients c ON a.assessment_code = c.setmore_customer_id
    ORDER BY a.name
""")
athletes = cur.fetchall()
if athletes:
    for a in athletes:
        linked = f"{a['first_name']} {a['last_name']}" if a['first_name'] else '❌ No match'
        code = (a['assessment_code'] or '')[:40]
        print(f"  [{a['id']:>2}] {a['name']:<20} → {linked}")
        print(f"       code: {code or '—'}")
else:
    print("  No athletes in database yet.")

# Show unlinked clients (potential athletes to add)
print(f"\n{'─' * 60}")
print("  UNLINKED CLIENTS (not yet added as athletes)")
print("─" * 60)
cur.execute("""
    SELECT c.id, c.first_name, c.last_name, c.setmore_customer_id
    FROM public.clients c
    WHERE NOT EXISTS (
        SELECT 1 FROM public.athletes a
        WHERE a.assessment_code = c.setmore_customer_id
    )
    ORDER BY c.first_name
""")
unlinked = cur.fetchall()
if unlinked:
    for c in unlinked:
        code = (c['setmore_customer_id'] or '')[:40]
        print(f"  [{c['id']:>2}] {c['first_name']} {c['last_name']:<20} code: {code}")
else:
    print("  All clients are linked to athletes.")

print("\n" + "═" * 60 + "\n")
conn.close()
