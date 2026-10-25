from datetime import date, datetime


def _as_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def effective_session_bounds(term_start, term_end, override=None):
    """Return effective date bounds, allowing an explicit override start before term start."""
    term_start = _as_date(term_start)
    term_end = _as_date(term_end)
    override = override or {}
    start = _as_date(override.get('override_start', override.get('start_date')))
    end = _as_date(override.get('override_end', override.get('end_date')))
    return start or term_start, end or term_end


def is_within_effective_session_bounds(session_date, term_start, term_end, override=None):
    session_date = _as_date(session_date)
    start, end = effective_session_bounds(term_start, term_end, override)
    return start <= session_date <= end


def load_week_session_schedules(db, week_start, week_end):
    """Fetch term dates and all session overrides for terms overlapping this week."""
    rows = db.execute('''
        SELECT t.id AS term_id, t.start_date AS term_start, t.end_date AS term_end,
               so.session_id, so.start_date AS override_start, so.end_date AS override_end
        FROM terms t
        LEFT JOIN session_overrides so ON so.term_id = t.id
        WHERE t.start_date <= %s AND t.end_date >= %s
        ORDER BY t.start_date
    ''', (week_end.isoformat(), week_start.isoformat())).fetchall()

    schedules = {}
    for row in rows:
        term_id = row['term_id']
        schedule = schedules.setdefault(term_id, {
            'term_start': row['term_start'],
            'term_end': row['term_end'],
            'overrides': {},
        })
        if row['session_id'] is not None:
            schedule['overrides'][row['session_id']] = {
                'override_start': row['override_start'],
                'override_end': row['override_end'],
            }
    return list(schedules.values())


def session_occurs_in_week(session_id, session_date, term_schedules):
    """Apply bounds only when this session has an override in a term for the week."""
    session_date = _as_date(session_date)
    if not term_schedules:
        return True

    containing = [
        schedule for schedule in term_schedules
        if _as_date(schedule['term_start']) <= session_date <= _as_date(schedule['term_end'])
    ]
    if containing:
        schedule = max(containing, key=lambda item: _as_date(item['term_start']))
    else:
        future = [
            schedule for schedule in term_schedules
            if _as_date(schedule['term_start']) > session_date
        ]
        if future:
            schedule = min(future, key=lambda item: _as_date(item['term_start']))
        else:
            schedule = max(term_schedules, key=lambda item: _as_date(item['term_end']))

    override = schedule['overrides'].get(session_id)
    if override is None:
        # Preserve the established week view for sessions without a term override.
        return True
    return is_within_effective_session_bounds(
        session_date, schedule['term_start'], schedule['term_end'], override
    )