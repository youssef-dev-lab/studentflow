import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from app import create_app
from studentflow.dashboard import dashboard_context
from studentflow.database import Database
from studentflow.plans import create_plan


class FeatureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'test.db'
        self.app = create_app(self.path)
        self.app.config.update(TESTING=True, TODAY=date(2027, 1, 1))
        self.client = self.app.test_client()
        self.db = Database(self.path)
        self.client.post('/courses', data={'name': 'Artificial Intelligence', 'code': 'CSC 3326',
                                          'instructor': 'Professor Sample', 'color': '#72ae9e'})
        self.course = self.db.query('SELECT * FROM courses', fetch=True)[0]

    def tasks(self):
        return self.db.query('SELECT * FROM tasks ORDER BY rowid', fetch=True)

    def add_task(self, **changes):
        values = dict(title='AI Midterm', course_id=self.course['id'], kind='exam',
                      due_date='2027-01-08', priority='high', minutes='240', notes='Chapters 1–3')
        values.update(changes)
        response = self.client.post('/tasks', data=values)
        self.assertEqual(response.status_code, 303)
        return self.tasks()[-1]

    def context(self, **filters):
        return dashboard_context(self.db, self.app.config['TODAY'], filters)

    def test_course_edit_and_detail_are_persistent(self):
        course_id = self.course['id']
        page = self.client.get(f'/courses/{course_id}').get_data(as_text=True)
        self.assertIn('Professor Sample', page)
        self.assertIn('#72ae9e', page)
        self.assertIn('course-detail', page)
        values = dict(name='Machine Learning', code='CSC 4400', color='#123abc', instructor='Dr. Smith')
        response = self.client.post(f'/courses/{course_id}/edit', data=values)
        self.assertEqual(response.status_code, 303)
        restarted = create_app(self.path).test_client()
        page = restarted.get(f'/courses/{course_id}').get_data(as_text=True)
        self.assertIn('Machine Learning', page)
        self.assertIn('Dr. Smith', page)
        self.assertIn('#123abc', page)
        self.assertEqual(self.db.query('SELECT created_at FROM courses', fetch=True)[0]['created_at'], self.course['created_at'])
        bad = self.client.post(f'/courses/{course_id}/edit', data=dict(values, color='red;display:none'))
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(self.db.query('SELECT color FROM courses', fetch=True)[0]['color'], '#123abc')
        self.assertEqual(self.client.get('/courses/missing').status_code, 404)

    def test_calendar_and_combined_filters(self):
        a = self.add_task(title='Today high', kind='assignment', due_date='2027-01-01')
        self.add_task(title='Tomorrow normal', kind='assignment', due_date='2027-01-02', priority='normal')
        self.add_task(title='Tomorrow exam', due_date='2027-01-02')
        result = self.context(course=self.course['id'], type='assignment', priority='high', date='2027-01-01')
        self.assertEqual([task['id'] for task in result['tasks']], [a['id']])
        page = self.client.get('/?view=week&date=2027-01-02').get_data(as_text=True)
        self.assertIn('Items for Jan 02, 2027', page)
        self.assertIn('date=2027-01-02', page)
        self.assertEqual(self.client.get('/?date=invalid').status_code, 400)
        self.assertEqual(self.client.get('/?type=unknown').status_code, 400)
        self.assertEqual(self.client.get('/?priority=unknown').status_code, 400)

    def test_completion_records_and_clears_timestamp(self):
        item = self.add_task()
        self.assertIsNone(item['completed_at'])
        response = self.client.post(f"/tasks/{item['id']}/toggle", data={'view': 'week', 'type': 'exam', 'priority': 'high'})
        self.assertIn('type=exam', response.location)
        completed = self.tasks()[0]
        self.assertTrue(completed['completed_at'].endswith('+00:00'))
        self.assertEqual(self.context()['progress'], 100)
        self.assertEqual(self.context()['active'], [])
        create_app(self.path)
        self.assertEqual(self.tasks()[0]['completed_at'], completed['completed_at'])
        self.client.post(f"/tasks/{item['id']}/toggle")
        self.assertIsNone(self.tasks()[0]['completed_at'])
        self.assertEqual(self.tasks()[0]['created_at'], item['created_at'])

    def test_generate_no_duplicates_workload_and_completion(self):
        parent = self.add_task()
        endpoint = f"/tasks/{parent['id']}/plan"
        self.assertEqual(self.client.post(endpoint).status_code, 303)
        sessions = [task for task in self.tasks() if task['parent_id']]
        self.assertEqual(len(sessions), 6)
        self.assertEqual(sum(task['minutes'] for task in sessions), 240)
        self.assertTrue(all(task['due_date'] < parent['due_date'] for task in sessions))
        self.assertEqual(self.client.post(endpoint).status_code, 303)
        self.assertEqual([task for task in self.tasks() if task['parent_id']], sessions)
        context = self.context()
        self.assertEqual(sum(task['workload_minutes'] for task in context['active']), 240)
        self.assertTrue(context['recommendation']['item']['parent_id'])
        self.client.post(f"/tasks/{sessions[0]['id']}/toggle")
        context = self.context()
        enriched_parent = next(task for task in context['all_tasks'] if task['id'] == parent['id'])
        self.assertEqual(enriched_parent['remaining_minutes'], 200)
        self.client.post(f"/tasks/{parent['id']}/toggle")
        self.assertTrue(all(task['completed'] and task['completed_at'] for task in self.tasks()))
        self.assertEqual(self.client.post(f"/tasks/{sessions[0]['id']}/toggle").status_code, 400)
        self.client.post(f"/tasks/{parent['id']}/toggle")
        self.assertTrue(all(task['completed'] for task in self.tasks() if task['parent_id']))
        self.assertEqual(self.context()['recommendation']['item']['id'], parent['id'])

    def test_simultaneous_plan_requests_do_not_duplicate_sessions(self):
        parent = self.add_task()
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(create_plan, self.db, parent['id'], self.app.config['TODAY']) for _ in range(2)]
            self.assertEqual(sorted(future.result() for future in futures), [0, 6])
        self.assertEqual(len([task for task in self.tasks() if task['parent_id']]), 6)

    def test_parent_priority_updates_preparation_sessions(self):
        parent = self.add_task(priority='normal')
        self.client.post(f"/tasks/{parent['id']}/plan")
        response = self.client.post(f"/tasks/{parent['id']}/edit", data=dict(parent, priority='high'))
        self.assertEqual(response.status_code, 303)
        self.assertTrue(all(task['priority'] == 'high' for task in self.tasks()))

    def test_bulk_planning_prioritizes_near_deadlines(self):
        later = self.add_task(title='Later', due_date='2027-01-05', minutes=45)
        nearer = self.add_task(title='Nearer', due_date='2027-01-02', minutes=45)
        self.add_task(title='Late', due_date='2026-12-31')
        self.assertEqual(self.client.post('/plans/generate').status_code, 303)
        children = [task for task in self.tasks() if task['parent_id']]
        self.assertEqual(len(children), 2)
        self.assertEqual(next(task for task in children if task['parent_id'] == nearer['id'])['due_date'], '2027-01-01')
        self.assertEqual(next(task for task in children if task['parent_id'] == later['id'])['due_date'], '2027-01-02')
        self.client.post('/plans/generate')
        self.assertEqual([task for task in self.tasks() if task['parent_id']], children)

    def test_plan_edits_clear_and_delete_preserve_consistency(self):
        parent = self.add_task()
        self.client.post(f"/tasks/{parent['id']}/plan")
        session = self.tasks()[1]
        self.assertEqual(self.client.post(f"/tasks/{parent['id']}/edit", data=dict(parent, minutes=120)).status_code, 400)
        self.assertEqual(self.client.post(f"/tasks/{session['id']}/edit", data=dict(session, due_date='2027-02-01')).status_code, 400)
        self.assertEqual(self.client.post(f"/tasks/{session['id']}/delete").status_code, 400)
        self.assertEqual(self.client.post(f"/tasks/{parent['id']}/delete").status_code, 400)
        self.assertEqual(len(self.tasks()), 7)
        clear = f"/tasks/{parent['id']}/plan/clear"
        self.assertEqual(self.client.get(clear).status_code, 200)
        self.assertEqual(self.client.post(clear).status_code, 400)
        self.assertEqual(self.client.post(clear, data={'confirm': 'yes'}).status_code, 303)
        self.assertEqual(len(self.tasks()), 1)
        self.assertEqual(self.client.post(f"/tasks/{parent['id']}/edit", data=dict(parent, minutes=120)).status_code, 303)
        self.client.post(f"/tasks/{parent['id']}/plan")
        self.assertEqual(sum(task['minutes'] for task in self.tasks() if task['parent_id']), 120)
        self.assertEqual(self.client.post(f"/tasks/{parent['id']}/delete", data={'confirm': 'yes'}).status_code, 303)
        self.assertEqual(self.tasks(), [])

    def test_course_confirmation_deletes_associated_items_only(self):
        parent = self.add_task()
        self.client.post(f"/tasks/{parent['id']}/plan")
        self.client.post('/courses', data={'name': 'Other', 'code': 'OTHER'})
        endpoint = f"/courses/{self.course['id']}/delete"
        self.assertIn(b'7 associated study items', self.client.get(endpoint).data)
        self.assertEqual(self.client.post(endpoint).status_code, 400)
        self.assertEqual(len(self.tasks()), 7)
        self.assertEqual(self.client.post(endpoint, data={'confirm': 'yes'}).status_code, 303)
        self.assertEqual(self.tasks(), [])
        self.assertEqual(self.db.query('SELECT code FROM courses', fetch=True), [{'code': 'OTHER'}])

    def test_overdue_and_today_planning(self):
        overdue = self.add_task(due_date='2026-12-31')
        self.assertEqual(self.client.post(f"/tasks/{overdue['id']}/plan").status_code, 400)
        self.assertEqual(len(self.tasks()), 1)
        today = self.add_task(title='Today', due_date='2027-01-01')
        self.assertEqual(self.client.post(f"/tasks/{today['id']}/plan").status_code, 303)
        self.assertTrue(all(task['due_date'] == '2027-01-01' for task in self.tasks() if task['parent_id']))

    def test_full_course_to_plan_to_completion_flow(self):
        item = self.add_task(kind='assignment', due_date='2027-01-01', minutes=90)
        context = self.context(view='today')
        self.assertEqual(len(context['urgent']), 1)
        self.assertEqual(context['courses'][0]['pending'], 1)
        focus = self.client.get(f"/tasks/{item['id']}/focus").get_data(as_text=True)
        self.assertIn('ONE THING AT A TIME', focus)
        self.assertIn('Chapters 1–3', focus)
        self.client.post(f"/tasks/{item['id']}/plan")
        sessions = [task for task in self.tasks() if task['parent_id']]
        self.assertEqual(len(sessions), 2)
        self.assertEqual(self.context()['remaining_minutes'], 90)
        self.assertEqual(self.context()['courses'][0]['pending'], 3)
        for session in sessions:
            self.client.post(f"/tasks/{session['id']}/toggle")
        self.assertEqual(self.context()['remaining_minutes'], 0)
        self.assertEqual(len(self.context()['active']), 1)
        self.client.post(f"/tasks/{item['id']}/toggle")
        self.assertEqual(self.context()['progress'], 100)
        restarted = create_app(self.path).test_client()
        completed = restarted.get('/?view=completed').get_data(as_text=True)
        self.assertIn('Completed work', completed)
        self.assertIn('100%', completed)
        self.assertEqual(len(self.context(view='completed')['tasks']), 3)
        self.assertEqual(self.context()['courses'][0]['pending'], 0)

    def test_empty_dashboard_does_not_claim_completion(self):
        page = self.client.get('/').get_data(as_text=True)
        self.assertIn('No study items yet', page)
        self.assertNotIn('0% of your study plan', page)
        self.assertIsNone(self.context()['progress'])

    def test_server_html_supports_ajax_and_normal_forms(self):
        item = self.add_task(title='<script>alert(1)</script>')
        response = self.client.post(f"/tasks/{item['id']}/toggle", follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'id="app-shell"', response.data)
        self.assertIn(b'role="status"', response.data)
        page = self.client.get('/?view=completed')
        self.assertNotIn(b'<script>alert(1)</script>', page.data)
        self.assertIn(b'&lt;script&gt;', page.data)
        with self.client.get('/static/app.js') as response:
            self.assertEqual(response.status_code, 200)
        endpoint = urlsplit(self.client.post('/plans/generate').location)
        self.assertEqual(endpoint.path, '/')


class MigrationTests(unittest.TestCase):
    def test_existing_database_migrates_once_without_losing_records(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'old.db'
            with sqlite3.connect(path) as connection:
                connection.execute('CREATE TABLE courses (id TEXT PRIMARY KEY, name TEXT NOT NULL, code TEXT NOT NULL)')
                connection.execute('CREATE TABLE tasks (id TEXT PRIMARY KEY, title TEXT NOT NULL, course_id TEXT NOT NULL REFERENCES courses(id), kind TEXT NOT NULL, due_date TEXT NOT NULL, priority TEXT NOT NULL, minutes INTEGER NOT NULL, notes TEXT NOT NULL DEFAULT "", completed INTEGER NOT NULL DEFAULT 0)')
                connection.execute("INSERT INTO courses VALUES ('course', 'Math', 'M101')")
                connection.execute("INSERT INTO tasks VALUES ('task', 'Practice', 'course', 'study', '2026-12-31', 'normal', 30, 'Original notes', 1)")
            db = Database(path)
            db.initialize()
            self.assertTrue(path.with_suffix('.pre-planner.bak').exists())
            original = db.query('SELECT * FROM tasks', fetch=True)
            self.assertEqual(original[0]['kind'], 'study-session')
            self.assertEqual(original[0]['notes'], 'Original notes')
            self.assertEqual(original[0]['completed'], 1)
            self.assertIsNone(original[0]['completed_at'])
            self.assertIsNotNone(original[0]['created_at'])
            db.initialize()
            self.assertEqual(original, db.query('SELECT * FROM tasks', fetch=True))
            with sqlite3.connect(path.with_suffix('.pre-planner.bak')) as backup:
                self.assertEqual(backup.execute('SELECT kind FROM tasks').fetchone()[0], 'study')
