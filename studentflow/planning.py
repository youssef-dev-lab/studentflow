"""Deterministic recommendations and manageable, load-balanced study sessions."""
from dataclasses import dataclass
from datetime import date, timedelta
from math import ceil

from .dates import days_until, parse_date


@dataclass(frozen=True)
class PlannedSession:
    due_date: str
    minutes: int


def completion_percentage(items):
    return round(100 * sum(bool(item['completed']) for item in items) / len(items)) if items else None


def priority_score(item, today: date) -> int:
    """Overdue always outranks future work. Remaining factors are bounded.

    Overdue: 10000 + 100 per late day (up to 30 days).
    Upcoming: 1000 / (days + 1), rounded down; closer means more urgent.
    Priority: high +300, normal +100, low +0.
    Workload: up to +120 for remaining minutes spread over available days.
    Type: exam +80, assignment +40, study session +20.
    Ties are resolved by deadline, creation time, and ID, never random order.
    """
    days = days_until(item['due_date'], today)
    urgency = 10000 + min(-days, 30) * 100 if days < 0 else 1000 // (days + 1)
    priority = {'high': 300, 'normal': 100, 'low': 0}[item['priority']]
    workload = min(120, ceil(item.get('remaining_minutes', item['minutes']) / max(1, days)))
    kind = {'exam': 80, 'assignment': 40, 'study-session': 20}[item['kind']]
    return urgency + priority + workload + kind


def recommend(items, today: date):
    # Planned parents remain visible, but their sessions are the actionable work.
    candidates = [item for item in items if not item['completed'] and not item.get('has_active_sessions')]
    if not candidates:
        return None
    chosen = min(candidates, key=lambda item: (
        -priority_score(item, today), item['due_date'], item.get('created_at', ''), item['id']))
    days = days_until(chosen['due_date'], today)
    deadline = (f'{-days} day(s) overdue' if days < 0 else 'Due today' if days == 0 else
                f'Due in {days} day(s)')
    explanation = f"{deadline} · {chosen['priority'].title()} priority"
    if chosen['kind'] == 'exam':
        explanation += ' · Exam preparation'
    remaining = chosen.get('remaining_minutes', chosen['minutes'])
    explanation += f' · {remaining} min remaining'
    return {'item': chosen, 'score': priority_score(chosen, today), 'reason': explanation}


def generate_sessions(item, today: date, daily_load=None):
    """Split exact work into <=45-minute balanced sessions before the deadline.

    At most 56 preparation days are considered, ending the day before the due
    date. Today's deadlines use today. Each chunk goes to the least-loaded day;
    an earlier date breaks ties. Existing scheduled work contributes to load.
    Past deadlines return no plan: silently assigning work after a deadline
    would be misleading. The caller must ask the student to change the date.
    """
    due = parse_date(item['due_date'])
    if due < today:
        raise ValueError('This deadline has passed. Choose a new deadline before generating a plan.')
    minutes = item['minutes']
    if not isinstance(minutes, int) or isinstance(minutes, bool) or not 5 <= minutes <= 1440:
        raise ValueError('The workload must be between 5 and 1,440 minutes.')
    count = ceil(minutes / 45)
    base, extra = divmod(minutes, count)
    day_count = max(1, min((due - today).days, 56))
    days = [today + timedelta(days=offset) for offset in range(day_count)]
    loads = {day: (daily_load or {}).get(day.isoformat(), 0) for day in days}
    sessions = []
    for index in range(count):
        day = min(days, key=lambda candidate: (loads[candidate], candidate))
        duration = base + (1 if index < extra else 0)
        sessions.append(PlannedSession(day.isoformat(), duration))
        loads[day] += duration
    return sorted(sessions, key=lambda session: session.due_date)
