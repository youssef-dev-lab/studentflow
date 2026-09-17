"""Shared vocabulary for SQLite records, validation, and templates."""
from typing import Optional, TypedDict

PRIORITIES = {'high': 0, 'normal': 1, 'low': 2}
KINDS = {'assignment': 'Assignment', 'exam': 'Exam', 'study-session': 'Study session'}
DEFAULT_COLOR = '#9b88d5'


class Course(TypedDict):
    id: str
    name: str
    code: str
    color: str
    instructor: str
    created_at: str


class StudyItem(TypedDict):
    id: str
    title: str
    course_id: str
    kind: str
    due_date: str
    priority: str
    minutes: int
    notes: str
    completed: int
    created_at: str
    completed_at: Optional[str]
    parent_id: Optional[str]
    session_index: Optional[int]
