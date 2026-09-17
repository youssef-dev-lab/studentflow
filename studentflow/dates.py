"""Calendar dates are local days; audit timestamps are timezone-aware UTC."""
from datetime import date, datetime, timedelta, timezone


def parse_date(value: str) -> date:
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError('Use a date in YYYY-MM-DD format.')
    return parsed


def days_until(value: str, today: date) -> int:
    return (parse_date(value) - today).days


def is_overdue(value: str, today: date) -> bool:
    return days_until(value, today) < 0


def is_today(value: str, today: date) -> bool:
    return days_until(value, today) == 0


def in_next_seven_days(value: str, today: date) -> bool:
    return 0 <= days_until(value, today) < 7


def next_seven_days(today: date):
    return [today + timedelta(days=offset) for offset in range(7)]


def current_week(today: date):
    monday = today - timedelta(days=today.weekday())
    return next_seven_days(monday)


def due_label(value: str, today: date) -> str:
    days = days_until(value, today)
    label = parse_date(value).strftime('%b %d, %Y')
    if days < 0:
        return 'Overdue · ' + label
    return 'Today' if days == 0 else 'Tomorrow' if days == 1 else label


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def timestamp_date(value):
    """Display audit dates in the same local timezone as the dashboard."""
    return datetime.fromisoformat(value).astimezone().date().isoformat() if value else 'earlier'
