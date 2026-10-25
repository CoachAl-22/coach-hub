"""
add_athlete.py — Add unlinked clients as athletes in the P2A performance database
Run: python add_athlete.py
"""
import os
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    print("❌  DATABASE_URL not found.")
    raise SystemExit(1)

conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = True
cur = conn.cursor(cursor_factory=RealDictCursor)

# ── Athletes to add ────────────────────────────────────────────────────
# Edit event_group / squad / dob as needed before running.
# assessment_code links to clients.setmore_customer_id
ATHLETES = [
    dict(name='Craig Shepherd',  initials='CS', event_group=None,       squad=None,          assessment_code='a3ff0639-cbc3-47b0-ac4a-7cd2855d19d3'),
    dict(name='Declyn Tanner',   initials='DT', event_group=None,       squad=None,          assessment_code='21a8cd86-a1c0-448e-852c-64abf877047d'),
    dict(name='Ethan Palmara',   initials='EP', event_group=None,       squad=None,          assessment_code='b42b4f54-d35f-47b1-8364-f651af852097'),
    dict(name='Michael Robson',  initials='MR', event_group=None,       squad=None,          assessment_code='77b3eda6-8110-4b27-b9a2-4dff674e7420'),
    dict(name='Sami Merhi',      initials='SM', event_group=None,       squad=None,          assessment_code='bdf8c510-fa2f-46c9-9165-caae0db552f7'),
    dict(name='Samson Wren',     initials='SW', event_group=None,       squad=None,          assessment_code='e6f83d10-ddde-4cce-8e85-ff80c371b08a'),
    dict(name='Stu Simpson',     initials='SS', event_group=None,       squad=None,          assessment_code='3ca964c6-a06e-4be3-83c9-77c55982b830'),
]

print("\n" + "═" * 60)
print("  P2A Coach Hub — Add Athletes")
print("═" * 60 + "\n")

added = 0
skipped = 0
errors = 0

for a in ATHLETES:
    try:
        cur.execute("""
            INSERT INTO public.athletes (name, initials, event_group, squad, assessment_code)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (assessment_code) DO NOTHING
        """, (a['name'], a['initials'], a['event_group'], a['squad'], a['assessment_code']))

        if cur.rowcount == 1:
            print(f"  ✅  Added   — {a['name']}")
            added += 1
        else:
            print(f"  ⏭   Skipped — {a['name']} (already exists)")
            skipped += 1
    except Exception as e:
        print(f"  ❌  Error   — {a['name']}: {e}")
        errors += 1

# ── Summary ────────────────────────────────────────────────────────────
print(f"\n{'─' * 60}")
print(f"  Added: {added}   Skipped: {skipped}   Errors: {errors}")

# ── Show final athlete list with link status ───────────────────────────
print(f"\n{'─' * 60}")
print("  All athletes now in database:")
print("─" * 60)
cur.execute("""
    SELECT a.id, a.name, a.initials,
           c.first_name IS NOT NULL AS linked
    FROM public.athletes a
    LEFT JOIN public.clients c ON a.assessment_code = c.setmore_customer_id
    ORDER BY a.name
""")
for row in cur.fetchall():
    status = '✓ linked' if row['linked'] else '— no link'
    print(f"  [{row['id']:>2}] {row['name']:<22} {row['initials'] or '  '}  {status}")

print("\n" + "═" * 60 + "\n")
conn.close()
