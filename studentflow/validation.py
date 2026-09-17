"""Validate incoming HTML forms once, on the Python side."""
import re

from .dates import parse_date
from .models import DEFAULT_COLOR, KINDS, PRIORITIES


def course_values(form):
    name = form.get('name', '').strip()
    code = form.get('code', '').strip()
    color = form.get('color', DEFAULT_COLOR).lower()
    instructor = form.get('instructor', '').strip()
    if not name or not code:
        raise ValueError('Please enter both a course name and a course code.')
    if len(name) > 120 or len(code) > 24 or len(instructor) > 120:
        raise ValueError('Use up to 120 characters for names and 24 for the course code.')
    if not re.fullmatch(r'#[0-9a-f]{6}', color):
        raise ValueError('Choose a valid course color.')
    return name, code, color, instructor


def task_values(form, database):
    title = form.get('title', '').strip()
    course_id = form.get('course_id', '')
    kind = form.get('kind', '')
    if kind == 'study':  # Accept forms from an older open tab.
        kind = 'study-session'
    due_date = form.get('due_date', '')
    priority = form.get('priority', 'normal')
    notes = form.get('notes', '').strip()
    if not title or len(title) > 180:
        raise ValueError('Give your study item a title of 1–180 characters.')
    if not database.query('SELECT id FROM courses WHERE id = ?', (course_id,), fetch=True):
        raise ValueError('Choose an existing course first.')
    if kind not in KINDS or priority not in PRIORITIES:
        raise ValueError('Choose a valid item type and priority.')
    try:
        parse_date(due_date)
    except ValueError:
        raise ValueError('Choose a valid deadline.') from None
    try:
        minutes = int(form.get('minutes', '30'))
    except ValueError:
        raise ValueError('Enter an estimated time in whole minutes.') from None
    if not 5 <= minutes <= 1440:
        raise ValueError('Estimated time must be between 5 and 1,440 minutes.')
    if len(notes) > 4000:
        raise ValueError('Keep notes under 4,000 characters.')
    return title, course_id, kind, due_date, priority, minutes, notes
