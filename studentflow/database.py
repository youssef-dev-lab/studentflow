"""SQLite access and additive migrations; no database work is hidden in the UI."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .dates import utc_now


class Database:
    def __init__(self, path):
        self.path = Path(path)

    @contextmanager
    def connection(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys = ON')
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def query(self, sql, parameters=(), fetch=False):
        with self.connection() as connection:
            result = connection.execute(sql, parameters)
            return [dict(row) for row in result.fetchall()] if fetch else None

    def initialize(self):
        # Back up an existing pre-migration database once before altering its schema.
        if self.path.exists():
            with self.connection() as connection:
                columns = {row['name'] for row in connection.execute('PRAGMA table_info(courses)')}
                backup = self.path.with_suffix('.pre-planner.bak')
                if columns and 'created_at' not in columns and not backup.exists():
                    destination = sqlite3.connect(backup)
                    try:
                        connection.backup(destination)
                    finally:
                        destination.close()
        with self.connection() as connection:
            connection.execute('CREATE TABLE IF NOT EXISTS courses '
                               '(id TEXT PRIMARY KEY, name TEXT NOT NULL, code TEXT NOT NULL)')
            connection.execute('CREATE TABLE IF NOT EXISTS tasks ('
                               'id TEXT PRIMARY KEY, title TEXT NOT NULL, '
                               'course_id TEXT NOT NULL REFERENCES courses(id), '
                               'kind TEXT NOT NULL, due_date TEXT NOT NULL, priority TEXT NOT NULL, '
                               'minutes INTEGER NOT NULL, notes TEXT NOT NULL DEFAULT "", '
                               'completed INTEGER NOT NULL DEFAULT 0)')
            additions = {
                'courses': {'color': "TEXT NOT NULL DEFAULT '#9b88d5'",
                            'instructor': "TEXT NOT NULL DEFAULT ''", 'created_at': 'TEXT'},
                'tasks': {'created_at': 'TEXT', 'completed_at': 'TEXT',
                          'parent_id': 'TEXT REFERENCES tasks(id) ON DELETE CASCADE',
                          'session_index': 'INTEGER'},
            }
            for table, fields in additions.items():
                existing = {row['name'] for row in connection.execute(f'PRAGMA table_info({table})')}
                for name, definition in fields.items():
                    if name not in existing:
                        connection.execute(f'ALTER TABLE {table} ADD COLUMN {name} {definition}')
                # Original creation dates were never recorded; this is the import time.
                connection.execute(f'UPDATE {table} SET created_at = ? WHERE created_at IS NULL', (utc_now(),))
            connection.execute("UPDATE tasks SET kind = 'study-session' WHERE kind = 'study'")
            connection.execute('CREATE UNIQUE INDEX IF NOT EXISTS unique_plan_session '
                               'ON tasks(parent_id, session_index) WHERE parent_id IS NOT NULL')
            connection.execute('CREATE INDEX IF NOT EXISTS tasks_by_course ON tasks(course_id)')
            connection.execute('CREATE INDEX IF NOT EXISTS tasks_by_deadline ON tasks(due_date)')
