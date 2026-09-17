"""Prepare dashboard data in Python; templates only display it."""
from .dates import days_until, due_label, next_seven_days, parse_date, timestamp_date
from .models import KINDS, PRIORITIES
from .planning import completion_percentage, recommend

VIEWS = {'all': 'Your study plan', 'today': 'Due today & overdue',
         'week': 'The next seven days', 'completed': 'Completed work'}


def dashboard_context(database, today, filters, course_id=None):
    courses = database.query('SELECT * FROM courses ORDER BY rowid', fetch=True)
    tasks = database.query(
        'SELECT tasks.*, courses.name AS course_name, courses.code AS course_code, '
        'courses.color AS course_color FROM tasks JOIN courses ON courses.id = tasks.course_id', fetch=True)
    children = {}
    for task in tasks:
        if task['parent_id']:
            children.setdefault(task['parent_id'], []).append(task)
    for task in tasks:
        sessions = children.get(task['id'], [])
        studied = sum(child['minutes'] for child in sessions if child['completed'])
        task.update(days=days_until(task['due_date'], today), due_label=due_label(task['due_date'], today),
                    kind_label=KINDS[task['kind']], has_plan=bool(sessions),
                    has_active_sessions=any(not child['completed'] for child in sessions),
                    studied_minutes=studied, remaining_minutes=max(0, task['minutes'] - studied),
                    # Sessions replace the parent's estimated workload, not add to it.
                    workload_minutes=0 if sessions else task['minutes'])
        task['completed_label'] = timestamp_date(task['completed_at'])
    tasks.sort(key=lambda task: (task['due_date'], PRIORITIES[task['priority']], task['title'].lower(), task['id']))
    active = [task for task in tasks if not task['completed']]
    completed = [task for task in tasks if task['completed']]
    urgent = [task for task in active if task['days'] <= 0]
    urgent.sort(key=lambda task: (task['days'] >= 0, PRIORITIES[task['priority']], task['due_date'], task['id']))
    upcoming = [task for task in active if 0 <= task['days'] < 7]
    view = filters.get('view', 'all')
    if view not in VIEWS:
        view = 'all'
    course_filter = course_id or filters.get('course', '')
    selected_course = next((course for course in courses if course['id'] == course_filter), None)
    type_filter = filters.get('type', '')
    priority_filter = filters.get('priority', '')
    date_filter = filters.get('date', '')
    if type_filter and type_filter not in KINDS:
        raise ValueError('Choose a valid type filter.')
    if priority_filter and priority_filter not in PRIORITIES:
        raise ValueError('Choose a valid priority filter.')
    if date_filter:
        try:
            parse_date(date_filter)
        except ValueError:
            raise ValueError('Choose a valid calendar date.') from None
    visible = {'all': active, 'today': urgent, 'week': upcoming, 'completed': completed}[view]
    # A selected date is its own day view; do not intersect with today's list.
    if date_filter:
        visible = [task for task in (completed if view == 'completed' else active) if task['due_date'] == date_filter]
    for field, value in [('course_id', course_filter), ('kind', type_filter), ('priority', priority_filter)]:
        if value:
            visible = [task for task in visible if task[field] == value]
    week = []
    for day in next_seven_days(today):
        due_tasks = [task for task in active if task['due_date'] == day.isoformat()
                     and (not course_filter or task['course_id'] == course_filter)]
        week.append({'label': day.strftime('%a'), 'number': day.day, 'date': day.isoformat(),
                     'full_label': day.strftime('%A, %B %d, %Y'), 'short_label': day.strftime('%b %d'), 'tasks': due_tasks,
                     'kinds': [kind for kind in KINDS if any(task['kind'] == kind for task in due_tasks)]})
    for course in courses:
        course_tasks = [task for task in tasks if task['course_id'] == course['id']]
        course['pending'] = sum(not task['completed'] for task in course_tasks)
        course['total'] = len(course_tasks)
        course['remaining_minutes'] = sum(task['workload_minutes'] for task in course_tasks if not task['completed'])
    recommendation = recommend([task for task in active if not course_filter or task['course_id'] == course_filter], today)
    return dict(
        courses=courses, tasks=visible, all_tasks=tasks, active=active, completed=completed,
        urgent=urgent, upcoming=upcoming, week=week, view=view, course_filter=course_filter,
        type_filter=type_filter, priority_filter=priority_filter, date_filter=date_filter,
        selected_course=selected_course, kinds=KINDS,
        heading=f"Items for {parse_date(date_filter).strftime('%b %d, %Y')}" if date_filter else VIEWS[view],
        today=today, next_task=recommendation['item'] if recommendation else None,
        recommendation=recommendation, progress=completion_percentage(tasks),
        remaining_minutes=sum(task['workload_minutes'] for task in urgent),
        plannable=[task for task in active if task['kind'] in ('assignment', 'exam')
                   and not task['parent_id'] and not task['has_plan'] and task['days'] >= 0],
    )
