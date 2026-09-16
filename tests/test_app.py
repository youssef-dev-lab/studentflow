import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path

from app import create_app


class CourseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / 'test.db'
        self.app = create_app(self.database)
        self.app.config['TESTING'] = True
        self.app.config['TODAY'] = date(2026, 9, 16)
        self.client = self.app.test_client()

    def test_add_and_persist_after_restart(self):
        response = self.client.post('/courses', data={'name': ' Math ', 'code': ' M101 '})
        self.assertEqual(response.status_code, 303)
        page = create_app(self.database).test_client().get('/').get_data(as_text=True)
        self.assertIn('Math', page)
        self.assertIn('M101', page)
        self.assertIn('class="count">1</strong>', page)

    def test_blank_course_is_rejected(self):
        response = self.client.post('/courses', data={'name': '  ', 'code': 'M101'})
        self.assertEqual(response.status_code, 400)
        self.assertIn(b'No courses yet', response.data)

    def test_delete_only_selected_course(self):
        for _ in range(2):
            self.client.post('/courses', data={'name': 'Math', 'code': 'M101'})
        connection = sqlite3.connect(self.database)
        ids = [row[0] for row in connection.execute('SELECT id FROM courses')]
        connection.close()
        self.assertNotEqual(ids[0], ids[1])
        response = self.client.post(f'/courses/{ids[0]}/delete', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        connection = sqlite3.connect(self.database)
        remaining = connection.execute('SELECT id FROM courses').fetchall()
        connection.close()
        self.assertEqual(remaining, [(ids[1],)])

    def test_course_names_are_escaped(self):
        response = self.client.post('/courses', data={'name': '<script>alert(1)</script>', 'code': 'X'}, follow_redirects=True)
        self.assertNotIn(b'<script>', response.data)
        self.assertIn(b'&lt;script&gt;', response.data)

    def rows(self, table):
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        rows = [dict(row) for row in connection.execute(f'SELECT * FROM {table}')]
        connection.close()
        return rows

    def make_task(self, **overrides):
        if not self.rows('courses'):
            self.client.post('/courses', data={'name': 'Economics', 'code': 'ECON101'})
        values = {'title': 'Read chapter three', 'course_id': self.rows('courses')[0]['id'],
                  'kind': 'assignment', 'due_date': '2026-09-16', 'priority': 'normal',
                  'minutes': '30', 'notes': 'Focus on the review questions.'}
        values.update(overrides)
        response = self.client.post('/tasks', data=values)
        self.assertEqual(response.status_code, 303)
        return next(row for row in self.rows('tasks') if row['title'] == values['title'])

    def test_task_lifecycle_and_restart(self):
        task = self.make_task()
        task_id = task['id']
        restarted = create_app(self.database).test_client()
        self.assertIn(b'Read chapter three', restarted.get('/').data)
        self.assertIn(b'Focus on the review questions.', restarted.get('/').data)
        self.client.post(f'/tasks/{task_id}/toggle')
        self.assertEqual(self.rows('tasks')[0]['completed'], 1)
        page = self.client.get('/?view=completed').get_data(as_text=True)
        self.assertIn('Read chapter three', page)
        self.assertIn('100%', page)
        self.client.post(f'/tasks/{task_id}/toggle')
        self.assertEqual(self.rows('tasks')[0]['completed'], 0)
        self.assertEqual(self.client.get(f'/tasks/{task_id}/edit').status_code, 200)
        updated = dict(task, title='Prepare practice exam', kind='exam', due_date='2026-09-20')
        self.assertEqual(self.client.post(f'/tasks/{task_id}/edit', data=updated).status_code, 303)
        self.assertEqual(self.rows('tasks')[0]['title'], 'Prepare practice exam')
        self.client.post(f'/tasks/{task_id}/delete')
        self.assertEqual(self.rows('tasks'), [])
        self.assertEqual(self.client.get(f'/tasks/{task_id}/edit').status_code, 404)

    def test_deadline_views_and_priority(self):
        overdue = self.make_task(title='Overdue essay', due_date='2026-09-15')
        self.make_task(title='Due today', due_date='2026-09-16')
        self.make_task(title='High priority today', due_date='2026-09-16', priority='high')
        self.make_task(title='End of week', due_date='2026-09-22')
        self.make_task(title='Beyond week', due_date='2026-09-23')
        # Inspect just the task list, since the next-action card is intentionally global.
        def plan(url):
            page = self.client.get(url).get_data(as_text=True)
            return page.split('<div class="task-list">')[1].split('<section class="panel courses-panel"')[0]
        daily = plan('/?view=today')
        self.assertIn('Overdue essay', daily)
        self.assertIn('Due today', daily)
        self.assertNotIn('End of week', daily)
        self.assertLess(daily.index('High priority today'), daily.index('Due today'))
        week = plan('/?view=week')
        self.assertNotIn('Overdue essay', week)
        self.assertIn('End of week', week)
        self.assertNotIn('Beyond week', week)
        self.client.post(f"/tasks/{overdue['id']}/toggle")
        self.assertNotIn('Overdue essay', plan('/?view=today'))

    def test_course_filter_and_deletion_protection(self):
        task = self.make_task(title='Economics essay')
        self.client.post('/courses', data={'name': 'Math', 'code': 'MATH101'})
        other = self.rows('courses')[1]['id']
        self.make_task(title='Algebra practice', course_id=other)
        page = self.client.get(f'/?course={other}').get_data(as_text=True)
        task_list = page.split('<div class="task-list">')[1].split('<section class="panel courses-panel"')[0]
        self.assertIn('Algebra practice', task_list)
        self.assertNotIn('Economics essay', task_list)
        response = self.client.post(f"/courses/{task['course_id']}/delete")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(len(self.rows('courses')), 2)
        self.assertEqual(len(self.rows('tasks')), 2)

    def test_invalid_task_does_not_change_saved_work(self):
        task = self.make_task()
        for changes in [{'due_date': '2026-02-30'}, {'minutes': '0'}, {'minutes': 'abc'},
                        {'title': '  '}, {'course_id': 'missing'}, {'kind': 'unknown'},
                        {'priority': 'urgent'}, {'notes': 'a' * 4001}]:
            with self.subTest(changes=changes):
                response = self.client.post('/tasks', data=dict(task, **changes))
                self.assertEqual(response.status_code, 400)
                response = self.client.post(f"/tasks/{task['id']}/edit", data=dict(task, **changes))
                self.assertEqual(response.status_code, 400)
                self.assertEqual(self.rows('tasks'), [task])


if __name__ == '__main__':
    unittest.main()
