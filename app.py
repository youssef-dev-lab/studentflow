"""StudentFlow's Flask routes. Planning and persistence live in studentflow/."""
from datetime import date
from pathlib import Path
from uuid import uuid4

from flask import Flask, abort, redirect, render_template, request, url_for

from studentflow.dashboard import dashboard_context
from studentflow.database import Database
from studentflow.dates import utc_now
from studentflow.models import DEFAULT_COLOR
from studentflow.plans import create_all_plans, create_plan
from studentflow.validation import course_values, task_values

NOTICES = {'course-saved': 'Course saved.', 'item-saved': 'Study item saved.',
           'deleted': 'Removed from your plan.', 'completed': 'Progress updated.',
           'planned': 'Study sessions saved. Existing plans were kept.',
           'cleared': 'Generated sessions removed. You can now adjust the original item.'}


def create_app(database_path=None):
    app = Flask(__name__)
    Path(app.instance_path).mkdir(exist_ok=True)
    app.config['DATABASE'] = database_path or Path(app.instance_path) / 'studentflow.db'
    database = Database(app.config['DATABASE'])
    database.initialize()

    def today():
        return app.config.get('TODAY', date.today())

    def find(table, record_id):
        rows = database.query(f'SELECT * FROM {table} WHERE id = ?', (record_id,), fetch=True)
        if not rows:
            abort(404)
        return rows[0]

    def dashboard(error=None, status=200, editing=None, course_edit=None, course_id=None, confirmation=None, focused_id=None):
        try:
            context = dashboard_context(database, today(), request.args, course_id)
        except ValueError as invalid_filter:
            context = dashboard_context(database, today(), {}, course_id)
            error, status = str(invalid_filter), 400
        return render_template(
            'index.html', **context, error=error, editing=editing, course_edit=course_edit,
            confirmation=confirmation, form=request.form, default_color=DEFAULT_COLOR,
            focused_item=next((item for item in context['all_tasks'] if item['id'] == focused_id), None),
            notice=NOTICES.get(request.args.get('notice')),
        ), status

    def saved(notice, anchor='plan', **filters):
        return redirect(url_for('home', notice=notice, _anchor=anchor, **filters), code=303)

    @app.get('/')
    def home():
        return dashboard()

    @app.get('/courses/<course_id>')
    def course_detail(course_id):
        find('courses', course_id)
        return dashboard(course_id=course_id)

    @app.post('/courses')
    def add_course():
        try:
            values = course_values(request.form)
        except ValueError as error:
            return dashboard(str(error), 400)
        database.query('INSERT INTO courses (id, name, code, color, instructor, created_at) VALUES (?, ?, ?, ?, ?, ?)',
                       (str(uuid4()), *values, utc_now()))
        return saved('course-saved', 'courses')

    @app.route('/courses/<course_id>/edit', methods=['GET', 'POST'])
    def edit_course(course_id):
        course = find('courses', course_id)
        if request.method == 'GET':
            return dashboard(course_edit=course, course_id=course_id)
        try:
            values = course_values(request.form)
        except ValueError as error:
            return dashboard(str(error), 400, course_edit=course, course_id=course_id)
        database.query('UPDATE courses SET name=?, code=?, color=?, instructor=? WHERE id=?', (*values, course_id))
        return saved('course-saved', 'courses', course=course_id)

    @app.route('/courses/<course_id>/delete', methods=['GET', 'POST'])
    def delete_course(course_id):
        course = find('courses', course_id)
        items = database.query('SELECT id FROM tasks WHERE course_id=?', (course_id,), fetch=True)
        if request.method == 'GET':
            return dashboard(confirmation=dict(title=f"Delete {course['name']}?",
                message=f"This removes the course and all {len(items)} associated study items, including generated sessions and completed work.",
                action=url_for('delete_course', course_id=course_id), button='Delete course and its items'), course_id=course_id)
        if items and request.form.get('confirm') != 'yes':
            return dashboard('Confirm course deletion first. Its study items have been kept.', 400)
        with database.connection() as connection:
            connection.execute('DELETE FROM tasks WHERE course_id=?', (course_id,))
            connection.execute('DELETE FROM courses WHERE id=?', (course_id,))
        return saved('deleted', 'courses')

    @app.post('/tasks')
    def add_task():
        try:
            values = task_values(request.form, database)
        except ValueError as error:
            return dashboard(str(error), 400)
        database.query('INSERT INTO tasks (id, title, course_id, kind, due_date, priority, minutes, notes, created_at) '
                       'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)', (str(uuid4()), *values, utc_now()))
        return saved('item-saved')

    @app.route('/tasks/<task_id>/edit', methods=['GET', 'POST'])
    def edit_task(task_id):
        item = find('tasks', task_id)
        if request.method == 'GET':
            return dashboard(editing=item)
        try:
            values = task_values(request.form, database)
            # Plan durations must continue to add up to the original workload.
            has_plan = database.query('SELECT id FROM tasks WHERE parent_id=?', (task_id,), fetch=True)
            if has_plan or item['parent_id']:
                proposed = (values[1], values[2], values[3], values[5])
                existing = (item['course_id'], item['kind'], item['due_date'], item['minutes'])
                if proposed != existing:
                    raise ValueError('Clear the generated plan on the original item before changing its course, type, deadline, or estimate.')
        except ValueError as error:
            return dashboard(str(error), 400, editing=item)
        with database.connection() as connection:
            connection.execute('UPDATE tasks SET title=?, course_id=?, kind=?, due_date=?, priority=?, minutes=?, notes=? WHERE id=?',
                               (*values, task_id))
            if not item['parent_id']:
                connection.execute('UPDATE tasks SET priority=? WHERE parent_id=?', (values[4], task_id))
        return saved('item-saved')

    @app.get('/tasks/<task_id>/focus')
    def focus_task(task_id):
        find('tasks', task_id)
        return dashboard(focused_id=task_id)

    @app.post('/tasks/<task_id>/toggle')
    def toggle_task(task_id):
        find('tasks', task_id)
        with database.connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            item = connection.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
            completing = not item['completed']
            if item['parent_id'] and not completing:
                parent = connection.execute('SELECT completed FROM tasks WHERE id=?', (item['parent_id'],)).fetchone()
                if parent['completed']:
                    return dashboard('Reopen the original item before reopening its study sessions.', 400)
            connection.execute('UPDATE tasks SET completed=?, completed_at=? WHERE id=?',
                               (int(completing), utc_now() if completing else None, task_id))
            if completing:
                # Finishing the original work retires its remaining preparation sessions.
                connection.execute('UPDATE tasks SET completed=1, completed_at=? WHERE parent_id=? AND completed=0',
                                   (utc_now(), task_id))
        filters = {key: request.form.get(key, '') for key in ('view', 'course', 'type', 'priority', 'date')}
        return saved('completed', **filters)

    @app.route('/tasks/<task_id>/delete', methods=['GET', 'POST'])
    def delete_task(task_id):
        item = find('tasks', task_id)
        children = database.query('SELECT id FROM tasks WHERE parent_id=?', (task_id,), fetch=True)
        if request.method == 'GET':
            return dashboard(confirmation=dict(title=f"Delete {item['title']}?",
                message=f"This permanently removes the item, its notes, and {len(children)} generated study sessions.",
                action=url_for('delete_task', task_id=task_id), button='Delete item'))
        if item['parent_id']:
            return dashboard('Clear the plan on the original item to remove generated sessions safely.', 400)
        if children and request.form.get('confirm') != 'yes':
            return dashboard('Confirm deletion of the item and its generated sessions first.', 400)
        database.query('DELETE FROM tasks WHERE id=?', (task_id,))
        return saved('deleted')

    @app.post('/tasks/<task_id>/plan')
    def plan_task(task_id):
        item = find('tasks', task_id)
        try:
            create_plan(database, task_id, today())
        except ValueError as error:
            return dashboard(str(error), 400, editing=item)
        return saved('planned')

    @app.post('/plans/generate')
    def plan_all():
        create_all_plans(database, today())
        return saved('planned')

    @app.route('/tasks/<task_id>/plan/clear', methods=['GET', 'POST'])
    def clear_plan(task_id):
        item = find('tasks', task_id)
        if item['parent_id']:
            abort(400)
        if request.method == 'GET':
            return dashboard(confirmation=dict(title='Clear generated study sessions?',
                message='This removes all generated sessions for this item, including their completion history. The original item stays saved.',
                action=url_for('clear_plan', task_id=task_id), button='Clear generated plan'))
        if request.form.get('confirm') != 'yes':
            return dashboard('Confirm before clearing the generated plan.', 400)
        database.query('DELETE FROM tasks WHERE parent_id=?', (task_id,))
        return saved('cleared')

    return app


if __name__ == '__main__':
    create_app().run(port=5000)
