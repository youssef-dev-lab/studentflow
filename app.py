"""StudentFlow: courses, deadlines, and a practical plan for your day."""
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from uuid import uuid4

from flask import Flask, abort, redirect, render_template, request, url_for


PRIORITIES = {'high': 0, 'normal': 1, 'low': 2}
VIEWS = {'all': 'Your study plan', 'today': 'Due today & overdue',
         'week': 'The next seven days', 'completed': 'Completed work'}


def create_app(database_path=None):
    app = Flask(__name__)
    Path(app.instance_path).mkdir(exist_ok=True)
    app.config['DATABASE'] = database_path or Path(app.instance_path) / 'studentflow.db'

    def query(sql, parameters=(), fetch=False):
        connection = sqlite3.connect(app.config['DATABASE'])
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys = ON')
        try:
            with connection:
                result = connection.execute(sql, parameters)
                return [dict(row) for row in result.fetchall()] if fetch else None
        finally:
            connection.close()

    # Existing course data stays intact when the planner is added.
    query('CREATE TABLE IF NOT EXISTS courses '
          '(id TEXT PRIMARY KEY, name TEXT NOT NULL, code TEXT NOT NULL)')
    query('CREATE TABLE IF NOT EXISTS tasks ('
          'id TEXT PRIMARY KEY, title TEXT NOT NULL, '
          'course_id TEXT NOT NULL REFERENCES courses(id), '
          'kind TEXT NOT NULL, due_date TEXT NOT NULL, priority TEXT NOT NULL, '
          'minutes INTEGER NOT NULL, notes TEXT NOT NULL DEFAULT "", '
          'completed INTEGER NOT NULL DEFAULT 0)')

    def today():
        return app.config.get('TODAY', date.today())

    def dashboard(error=None, status=200, editing=None):
        current_day = today()
        courses = query('SELECT * FROM courses ORDER BY rowid', fetch=True)
        tasks = query('SELECT tasks.*, courses.name AS course_name, courses.code AS course_code '
                      'FROM tasks JOIN courses ON courses.id = tasks.course_id', fetch=True)
        for task in tasks:
            due = date.fromisoformat(task['due_date'])
            days = (due - current_day).days
            task['days'] = days
            task['due_label'] = ('Overdue · ' + due.strftime('%b %d') if days < 0 else
                                 'Today' if days == 0 else 'Tomorrow' if days == 1 else due.strftime('%b %d'))
        tasks.sort(key=lambda task: (task['due_date'], PRIORITIES[task['priority']], task['title'].lower()))
        active = [task for task in tasks if not task['completed']]
        completed = [task for task in tasks if task['completed']]
        urgent = [task for task in active if task['days'] <= 0]
        upcoming = [task for task in active if 0 <= task['days'] < 7]
        view = request.args.get('view', 'all')
        if view not in VIEWS:
            view = 'all'
        course_filter = request.args.get('course', '')
        visible = {'all': active, 'today': urgent, 'week': upcoming, 'completed': completed}[view]
        if course_filter:
            visible = [task for task in visible if task['course_id'] == course_filter]
        week = []
        for offset in range(7):
            day = current_day + timedelta(days=offset)
            due_tasks = [task for task in active if task['due_date'] == day.isoformat()]
            week.append({'label': day.strftime('%a'), 'number': day.day, 'tasks': due_tasks})
        for course in courses:
            course['pending'] = sum(task['course_id'] == course['id'] for task in active)
            course['total'] = sum(task['course_id'] == course['id'] for task in tasks)
        return render_template(
            'index.html', courses=courses, tasks=visible, active=active, completed=completed,
            urgent=urgent, upcoming=upcoming, week=week, view=view, course_filter=course_filter,
            heading=VIEWS[view], today=current_day, next_task=active[0] if active else None,
            progress=round(len(completed) / len(tasks) * 100) if tasks else 0,
            remaining_minutes=sum(task['minutes'] for task in urgent),
            error=error, editing=editing, form=request.form,
        ), status

    @app.get('/')
    def home():
        return dashboard()

    @app.post('/courses')
    def add_course():
        name = request.form.get('name', '').strip()
        code = request.form.get('code', '').strip()
        if not name or not code:
            return dashboard('Please enter both a course name and a course code.', 400)
        if len(name) > 120 or len(code) > 24:
            return dashboard('Use up to 120 characters for a course name and 24 for its code.', 400)
        query('INSERT INTO courses (id, name, code) VALUES (?, ?, ?)', (str(uuid4()), name, code))
        return redirect(url_for('home', _anchor='courses'), code=303)

    @app.post('/courses/<course_id>/delete')
    def delete_course(course_id):
        if query('SELECT id FROM tasks WHERE course_id = ?', (course_id,), fetch=True):
            return dashboard('This course has study items. Delete those items before removing the course.', 400)
        query('DELETE FROM courses WHERE id = ?', (course_id,))
        return redirect(url_for('home', _anchor='courses'), code=303)

    def task_values():
        title = request.form.get('title', '').strip()
        course_id = request.form.get('course_id', '')
        kind = request.form.get('kind', '')
        due_date = request.form.get('due_date', '')
        priority = request.form.get('priority', 'normal')
        notes = request.form.get('notes', '').strip()
        if not title or len(title) > 180:
            raise ValueError('Give your study item a title of 1–180 characters.')
        if not query('SELECT id FROM courses WHERE id = ?', (course_id,), fetch=True):
            raise ValueError('Choose an existing course first.')
        if kind not in ('assignment', 'exam', 'study') or priority not in PRIORITIES:
            raise ValueError('Choose a valid item type and priority.')
        try:
            due_date = date.fromisoformat(due_date).isoformat()
        except ValueError:
            raise ValueError('Choose a valid deadline.') from None
        try:
            minutes = int(request.form.get('minutes', '30'))
        except ValueError:
            raise ValueError('Enter an estimated time in whole minutes.') from None
        if not 5 <= minutes <= 1440:
            raise ValueError('Estimated time must be between 5 and 1,440 minutes.')
        if len(notes) > 4000:
            raise ValueError('Keep notes under 4,000 characters.')
        return title, course_id, kind, due_date, priority, minutes, notes

    @app.post('/tasks')
    def add_task():
        try:
            values = task_values()
        except ValueError as error:
            return dashboard(str(error), 400)
        query('INSERT INTO tasks (id, title, course_id, kind, due_date, priority, minutes, notes) '
              'VALUES (?, ?, ?, ?, ?, ?, ?, ?)', (str(uuid4()), *values))
        return redirect(url_for('home', _anchor='plan'), code=303)

    @app.route('/tasks/<task_id>/edit', methods=['GET', 'POST'])
    def edit_task(task_id):
        matches = query('SELECT * FROM tasks WHERE id = ?', (task_id,), fetch=True)
        if not matches:
            abort(404)
        if request.method == 'GET':
            return dashboard(editing=matches[0])
        try:
            values = task_values()
        except ValueError as error:
            return dashboard(str(error), 400, editing=matches[0])
        query('UPDATE tasks SET title=?, course_id=?, kind=?, due_date=?, priority=?, minutes=?, notes=? '
              'WHERE id=?', (*values, task_id))
        return redirect(url_for('home', _anchor='plan'), code=303)

    @app.post('/tasks/<task_id>/toggle')
    def toggle_task(task_id):
        query('UPDATE tasks SET completed = 1 - completed WHERE id = ?', (task_id,))
        view = request.form.get('view', 'all')
        return redirect(url_for('home', view=view if view in VIEWS else 'all',
                                course=request.form.get('course', ''), _anchor='plan'), code=303)

    @app.post('/tasks/<task_id>/delete')
    def delete_task(task_id):
        query('DELETE FROM tasks WHERE id = ?', (task_id,))
        return redirect(url_for('home', _anchor='plan'), code=303)

    return app


if __name__ == '__main__':
    create_app().run(port=5000)
