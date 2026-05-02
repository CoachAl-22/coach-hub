from datetime import date, timedelta


def get_current_or_next_term(db):
    today = date.today().isoformat()
    # Current term (today falls within it)
    term = db.execute(
        'SELECT * FROM terms WHERE start_date <= ? AND end_date >= ? ORDER BY start_date LIMIT 1',
        (today, today)
    ).fetchone()
    if term:
        return term
    # Next upcoming term
    term = db.execute(
        'SELECT * FROM terms WHERE start_date > ? ORDER BY start_date LIMIT 1',
        (today,)
    ).fetchone()
    return term


def get_session_dates_for_term(term, day_of_week):
    """Return all dates within a term that fall on the given day of week."""
    day_map = {
        'Monday': 0, 'Tuesday': 1, 'Wednesday': 2,
        'Thursday': 3, 'Friday': 4, 'Saturday': 5, 'Sunday': 6
    }
    target_day = day_map.get(day_of_week, 0)
    start = date.fromisoformat(term['start_date'])
    end = date.fromisoformat(term['end_date'])

    dates = []
    current = start
    while current <= end:
        if current.weekday() == target_day:
            dates.append(current)
        current += timedelta(days=1)
    return dates
