def get_auth_version(db, coach_id):
    row = db.execute(
        'SELECT auth_version FROM public.coach_auth_state WHERE coach_id = %s',
        (coach_id,),
    ).fetchone()
    return row['auth_version'] if row else 0


def bump_auth_version(db, coach_id):
    row = db.execute('''
        INSERT INTO public.coach_auth_state AS state (coach_id, auth_version)
        VALUES (%s, 1)
        ON CONFLICT (coach_id) DO UPDATE
        SET auth_version = state.auth_version + 1
        RETURNING auth_version
    ''', (coach_id,)).fetchone()
    return row['auth_version']