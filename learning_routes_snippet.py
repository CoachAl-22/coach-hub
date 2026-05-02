# ============================================================
# LEARNING HUB ROUTES — Paste into main.py
#
# Also add this import near the top of main.py (after existing imports):
#   from learning_content import INDUCTION_MODULES, LESSON_WEEKS, PROGRESSION_LEVELS
#
# And add this near the top (after existing imports):
#   from collections import OrderedDict
#
# Uses: current_user (flask_login), %s placeholders, no ch. prefix
# ============================================================


# ── LEARNING HUB DASHBOARD ────────────────────────────────────────────────

@app.route('/learning')
@login_required
def learning_hub():
    db = get_db()

    rows = db.execute(
        'SELECT module_key FROM module_completions WHERE coach_id = %s',
        (current_user.id,)
    ).fetchall()
    completed_keys = {r['module_key'] for r in rows}

    induction_total = len(INDUCTION_MODULES)
    induction_done  = sum(1 for m in INDUCTION_MODULES if m['key'] in completed_keys)

    lesson_total = len(LESSON_WEEKS)
    lesson_done  = sum(1 for w in LESSON_WEEKS if f"lesson_week_{w['week']}" in completed_keys)

    prog_total = len(PROGRESSION_LEVELS)
    prog_done  = sum(1 for l in PROGRESSION_LEVELS if l['key'] in completed_keys)

    checklist_total = db.execute(
        'SELECT COUNT(*) AS c FROM induction_checklist_items'
    ).fetchone()['c']

    checklist_done = db.execute(
        'SELECT COUNT(*) AS c FROM induction_checklist_progress WHERE coach_id = %s AND completed_at IS NOT NULL',
        (current_user.id,)
    ).fetchone()['c']

    db.close()

    return render_template('learning_hub.html',
        is_admin=current_user.is_admin,
        induction_total=induction_total,
        induction_done=induction_done,
        lesson_total=lesson_total,
        lesson_done=lesson_done,
        prog_total=prog_total,
        prog_done=prog_done,
        checklist_total=checklist_total,
        checklist_done=checklist_done,
    )


# ── INDUCTION TRACK ───────────────────────────────────────────────────────

@app.route('/learning/induction')
@login_required
def learning_induction():
    db = get_db()
    rows = db.execute(
        'SELECT module_key FROM module_completions WHERE coach_id = %s',
        (current_user.id,)
    ).fetchall()
    completed_keys = {r['module_key'] for r in rows}
    db.close()

    modules_with_status = [
        {**m, 'completed': m['key'] in completed_keys}
        for m in INDUCTION_MODULES
    ]
    return render_template('learning_induction.html', modules=modules_with_status)


@app.route('/learning/induction/<module_key>')
@login_required
def learning_module(module_key):
    module = next((m for m in INDUCTION_MODULES if m['key'] == module_key), None)
    if not module:
        return redirect(url_for('learning_induction'))

    db = get_db()
    row = db.execute(
        'SELECT id FROM module_completions WHERE coach_id = %s AND module_key = %s',
        (current_user.id, module_key)
    ).fetchone()
    completed = row is not None
    db.close()

    idx = next(i for i, m in enumerate(INDUCTION_MODULES) if m['key'] == module_key)
    prev_module = INDUCTION_MODULES[idx - 1] if idx > 0 else None
    next_module = INDUCTION_MODULES[idx + 1] if idx < len(INDUCTION_MODULES) - 1 else None

    return render_template('learning_module.html',
        module=module,
        completed=completed,
        prev_module=prev_module,
        next_module=next_module,
    )


@app.route('/learning/induction/<module_key>/complete', methods=['POST'])
@login_required
def complete_module(module_key):
    db = get_db()
    db.execute(
        'INSERT INTO module_completions (coach_id, module_key) VALUES (%s, %s) ON CONFLICT DO NOTHING',
        (current_user.id, module_key)
    )
    db.commit()
    db.close()
    return redirect(url_for('learning_module', module_key=module_key))


# ── INDUCTION CHECKLIST ───────────────────────────────────────────────────

@app.route('/learning/checklist')
@login_required
def learning_checklist():
    db = get_db()

    items = db.execute(
        'SELECT * FROM induction_checklist_items ORDER BY sequence_order'
    ).fetchall()

    rows = db.execute(
        'SELECT item_id, completed_at, admin_signoff_at FROM induction_checklist_progress WHERE coach_id = %s',
        (current_user.id,)
    ).fetchall()
    progress = {r['item_id']: r for r in rows}

    grouped = OrderedDict()
    for item in items:
        cat = item['category']
        if cat not in grouped:
            grouped[cat] = []
        p = progress.get(item['id'])
        grouped[cat].append({
            'id':             item['id'],
            'text':           item['item_text'],
            'requires_admin': item['requires_admin_signoff'],
            'completed':      bool(p and p['completed_at']),
            'admin_signed':   bool(p and p['admin_signoff_at']),
        })

    db.close()
    return render_template('learning_checklist.html',
        grouped=grouped,
        is_admin=current_user.is_admin,
        coach_id=current_user.id,
    )


@app.route('/learning/checklist/<int:item_id>/complete', methods=['POST'])
@login_required
def complete_checklist_item(item_id):
    db = get_db()
    db.execute('''
        INSERT INTO induction_checklist_progress (coach_id, item_id, completed_at)
        VALUES (%s, %s, NOW())
        ON CONFLICT (coach_id, item_id) DO UPDATE SET completed_at = NOW()
    ''', (current_user.id, item_id))
    db.commit()
    db.close()
    return redirect(url_for('learning_checklist'))


@app.route('/learning/checklist/<int:item_id>/signoff', methods=['POST'])
@login_required
def signoff_checklist_item(item_id):
    if not current_user.is_admin:
        return redirect(url_for('learning_hub'))
    coach_id = request.form.get('coach_id', type=int)
    db = get_db()
    db.execute('''
        INSERT INTO induction_checklist_progress (coach_id, item_id, admin_signoff_at)
        VALUES (%s, %s, NOW())
        ON CONFLICT (coach_id, item_id) DO UPDATE SET admin_signoff_at = NOW()
    ''', (coach_id, item_id))
    db.commit()
    db.close()
    return redirect(url_for('admin_coach_induction', coach_id=coach_id))


# ── LESSON PLANS ──────────────────────────────────────────────────────────

@app.route('/learning/lesson-plans')
@login_required
def learning_lesson_plans():
    db = get_db()
    rows = db.execute(
        'SELECT module_key FROM module_completions WHERE coach_id = %s',
        (current_user.id,)
    ).fetchall()
    completed_keys = {r['module_key'] for r in rows}
    db.close()

    weeks_with_status = [
        {**w, 'completed': f"lesson_week_{w['week']}" in completed_keys}
        for w in LESSON_WEEKS
    ]
    return render_template('learning_lesson_plans.html', weeks=weeks_with_status)


@app.route('/learning/lesson-plans/<int:week_num>')
@login_required
def learning_lesson_week(week_num):
    week = next((w for w in LESSON_WEEKS if w['week'] == week_num), None)
    if not week:
        return redirect(url_for('learning_lesson_plans'))

    db = get_db()
    row = db.execute(
        'SELECT id FROM module_completions WHERE coach_id = %s AND module_key = %s',
        (current_user.id, f'lesson_week_{week_num}')
    ).fetchone()
    completed = row is not None
    db.close()

    prev_week = next((w for w in LESSON_WEEKS if w['week'] == week_num - 1), None)
    next_week = next((w for w in LESSON_WEEKS if w['week'] == week_num + 1), None)

    return render_template('learning_lesson_week.html',
        week=week,
        completed=completed,
        prev_week=prev_week,
        next_week=next_week,
    )


@app.route('/learning/lesson-plans/<int:week_num>/complete', methods=['POST'])
@login_required
def complete_lesson_week(week_num):
    db = get_db()
    db.execute(
        'INSERT INTO module_completions (coach_id, module_key) VALUES (%s, %s) ON CONFLICT DO NOTHING',
        (current_user.id, f'lesson_week_{week_num}')
    )
    db.commit()
    db.close()
    return redirect(url_for('learning_lesson_week', week_num=week_num))


# ── PROGRESSION TRACK ─────────────────────────────────────────────────────

@app.route('/learning/progression')
@login_required
def learning_progression():
    db = get_db()
    rows = db.execute(
        'SELECT module_key FROM module_completions WHERE coach_id = %s',
        (current_user.id,)
    ).fetchall()
    completed_keys = {r['module_key'] for r in rows}
    db.close()

    levels_with_status = [
        {**l, 'completed': l['key'] in completed_keys}
        for l in PROGRESSION_LEVELS
    ]
    return render_template('learning_progression.html', levels=levels_with_status)


@app.route('/learning/progression/<level_key>')
@login_required
def learning_progression_level(level_key):
    level = next((l for l in PROGRESSION_LEVELS if l['key'] == level_key), None)
    if not level:
        return redirect(url_for('learning_progression'))

    db = get_db()
    row = db.execute(
        'SELECT id FROM module_completions WHERE coach_id = %s AND module_key = %s',
        (current_user.id, level_key)
    ).fetchone()
    completed = row is not None
    db.close()

    idx = next(i for i, l in enumerate(PROGRESSION_LEVELS) if l['key'] == level_key)
    prev_level = PROGRESSION_LEVELS[idx - 1] if idx > 0 else None
    next_level = PROGRESSION_LEVELS[idx + 1] if idx < len(PROGRESSION_LEVELS) - 1 else None

    return render_template('learning_progression_level.html',
        level=level,
        completed=completed,
        prev_level=prev_level,
        next_level=next_level,
    )


@app.route('/learning/progression/<level_key>/complete', methods=['POST'])
@login_required
def complete_progression_level(level_key):
    db = get_db()
    db.execute(
        'INSERT INTO module_completions (coach_id, module_key) VALUES (%s, %s) ON CONFLICT DO NOTHING',
        (current_user.id, level_key)
    )
    db.commit()
    db.close()
    return redirect(url_for('learning_progression_level', level_key=level_key))


# ── ADMIN — ALL COACH PROGRESS ────────────────────────────────────────────

@app.route('/learning/admin/progress')
@login_required
def admin_learning_progress():
    if not current_user.is_admin:
        return redirect(url_for('learning_hub'))

    db = get_db()
    coaches = db.execute(
        'SELECT id, name FROM coaches WHERE is_active = 1 ORDER BY name'
    ).fetchall()

    checklist_total = db.execute(
        'SELECT COUNT(*) AS c FROM induction_checklist_items'
    ).fetchone()['c']

    coach_progress = []
    for coach in coaches:
        done_rows = db.execute(
            'SELECT module_key FROM module_completions WHERE coach_id = %s',
            (coach['id'],)
        ).fetchall()
        done_keys = {r['module_key'] for r in done_rows}

        checklist_done = db.execute(
            'SELECT COUNT(*) AS c FROM induction_checklist_progress WHERE coach_id = %s AND completed_at IS NOT NULL',
            (coach['id'],)
        ).fetchone()['c']

        coach_progress.append({
            'id':              coach['id'],
            'name':            coach['name'],
            'induction_done':  sum(1 for m in INDUCTION_MODULES if m['key'] in done_keys),
            'induction_total': len(INDUCTION_MODULES),
            'lesson_done':     sum(1 for w in LESSON_WEEKS if f"lesson_week_{w['week']}" in done_keys),
            'lesson_total':    len(LESSON_WEEKS),
            'prog_done':       sum(1 for l in PROGRESSION_LEVELS if l['key'] in done_keys),
            'prog_total':      len(PROGRESSION_LEVELS),
            'checklist_done':  checklist_done,
            'checklist_total': checklist_total,
        })

    db.close()
    return render_template('admin_learning_progress.html', coaches=coach_progress)


@app.route('/learning/admin/coach/<int:coach_id>/induction')
@login_required
def admin_coach_induction(coach_id):
    if not current_user.is_admin:
        return redirect(url_for('learning_hub'))

    db = get_db()
    coach = db.execute(
        'SELECT id, name FROM coaches WHERE id = %s',
        (coach_id,)
    ).fetchone()

    items = db.execute(
        'SELECT * FROM induction_checklist_items ORDER BY sequence_order'
    ).fetchall()

    rows = db.execute(
        'SELECT item_id, completed_at, admin_signoff_at FROM induction_checklist_progress WHERE coach_id = %s',
        (coach_id,)
    ).fetchall()
    progress = {r['item_id']: r for r in rows}

    grouped = OrderedDict()
    for item in items:
        cat = item['category']
        if cat not in grouped:
            grouped[cat] = []
        p = progress.get(item['id'])
        grouped[cat].append({
            'id':             item['id'],
            'text':           item['item_text'],
            'requires_admin': item['requires_admin_signoff'],
            'completed':      bool(p and p['completed_at']),
            'admin_signed':   bool(p and p['admin_signoff_at']),
        })

    db.close()
    return render_template('admin_coach_induction.html',
        coach=coach,
        grouped=grouped,
    )
