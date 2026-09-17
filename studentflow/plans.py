"""Save generated plans atomically and prevent duplicate sessions."""
from uuid import uuid4

from .dates import utc_now
from .planning import generate_sessions


def create_plan(database, task_id, today):
    with database.connection() as connection:
        # Serializes simultaneous clicks/tabs before checking whether a plan exists.
        connection.execute('BEGIN IMMEDIATE')
        row = connection.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchone()
        if row is None:
            raise ValueError('This study item no longer exists.')
        item = dict(row)
        if item['completed'] or item['parent_id'] or item['kind'] not in ('assignment', 'exam'):
            raise ValueError('Choose an incomplete assignment or exam to generate a study plan.')
        if connection.execute('SELECT id FROM tasks WHERE parent_id = ?', (task_id,)).fetchone():
            return 0
        # Planned parents do not contribute again: only their sessions carry load.
        rows = connection.execute(
            'SELECT due_date, SUM(minutes) AS minutes FROM tasks WHERE completed = 0 '
            'AND id != ? AND NOT EXISTS (SELECT 1 FROM tasks child WHERE child.parent_id = tasks.id) '
            'GROUP BY due_date', (task_id,)).fetchall()
        load = {row['due_date']: row['minutes'] for row in rows}
        sessions = generate_sessions(item, today, load)
        now = utc_now()
        for index, session in enumerate(sessions, start=1):
            connection.execute(
                'INSERT INTO tasks (id, title, course_id, kind, due_date, priority, minutes, notes, '
                'created_at, parent_id, session_index) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (str(uuid4()), f"Study {index}: {item['title']}"[:180], item['course_id'], 'study-session',
                 session.due_date, item['priority'], session.minutes, '', now, task_id, index))
        return len(sessions)


def create_all_plans(database, today):
    # Earlier deadlines reserve capacity before later ones.
    candidates = database.query(
        "SELECT id FROM tasks WHERE completed = 0 AND parent_id IS NULL "
        "AND kind IN ('assignment', 'exam') AND due_date >= ? "
        "ORDER BY due_date, CASE priority WHEN 'high' THEN 0 WHEN 'normal' THEN 1 ELSE 2 END, created_at, id",
        (today.isoformat(),), fetch=True)
    return sum(create_plan(database, item['id'], today) for item in candidates)
