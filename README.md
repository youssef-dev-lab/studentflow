# StudentFlow

StudentFlow is a local academic planner that helps university students turn
courses and deadlines into manageable study sessions. It builds on a Python/Flask
application and preserves the existing StudentFlow dashboard design.

## Features

- Create, view, edit, and delete courses with a code, name, color, and optional instructor.
- Open a course from the sidebar to see its items and remaining workload.
- Add assignments, exams, and study sessions with deadlines, priorities, estimates, and notes.
- View overdue work, today's work, the next seven days, and completed items.
- Click calendar dates and combine course, type, and priority filters.
- Complete and reopen items, with completion timestamps and live dashboard counts.
- Get an explained, deterministic recommendation for what to work on next.
- Open a focused task view and generate manageable preparation sessions.
- Confirm deletion of items, courses, and generated plans.
- Save changes to SQLite across refreshes and restarts.
- Submit forms without a full reload when JavaScript is available; normal HTML forms
  remain functional without JavaScript.

## Why I Built It

StudentFlow is designed to help university students turn academic deadlines into
manageable study plans. A deadline alone does not explain what to do today.
Courses, workload estimates, and small preparation sessions give each day a clearer
starting point while keeping the whole semester in view.

## Tech Stack

- **Python 3.9+** for application and planning logic.
- **Flask** for routes and validation, and **Jinja** for HTML templates.
- **SQLite**, through Python's standard library, for local persistence.
- **HTML and CSS** for the existing responsive dashboard.
- **Small vanilla JavaScript enhancement** for asynchronous form submissions.
- **unittest** for automated tests; no additional test dependencies.

The archived Next.js/React/TypeScript source in `legacy/nextjs/` is reference
material. It is not used to run this application. No Node build is required.

## How It Works

### Courses and study items

A course stores its identity, color, instructor, and creation timestamp. Each study
item belongs to a course and records a type, deadline, priority, estimated minutes,
notes, completion state, and timestamps. Generated sessions reference their original
assignment or exam; course names are read through the relationship rather than
copied into every item.

The sidebar counts all incomplete items in each course, including generated sessions.
Completion percentage is completed items divided by all items, including generated
sessions and their original items. An empty plan shows a dash instead of a misleading
completion percentage. Workload minutes count a planned item's sessions instead of
counting both the sessions and their parent estimate.

### Priority recommendation

`studentflow/planning.py` scores incomplete actionable work using:

- Overdue: **10,000 + 100 per late day**, capped at 30 late days.
- Otherwise: **1,000 / (days until deadline + 1)**, rounded down.
- Priority: high **+300**, normal **+100**, low **+0**.
- Remaining work per available day: up to **+120**.
- Type: exam **+80**, assignment **+40**, study session **+20**.

Overdue work always outranks future work. Deadline, creation timestamp, and ID
resolve ties consistently. A parent with unfinished generated sessions is excluded
from recommendations so an actionable session can appear instead. Course detail
views recommend work for the selected course. The focus card explains the choice.
No AI service is involved, and opening a focus view does not start a timer.

### Automatic study planning

Open an incomplete assignment or exam and choose **Generate study sessions**, or
use the dashboard button to plan all eligible items. The planner:

1. Plans nearer deadlines first when processing multiple items.
2. Splits the exact estimated workload into balanced sessions of at most 45 minutes.
3. Assigns each session to the least-loaded available day, breaking ties by earlier date.
4. Uses days before the deadline; for a deadline today, uses today.
5. Refuses overdue deadlines until you update their date.
6. Saves linked sessions atomically, preventing duplicate plans from repeated clicks.

For example, 240 minutes becomes six 40-minute sessions. Existing workload affects
the dates. At most the next 56 preparation days are considered. The planner does not
yet know your class timetable, free hours, or daily capacity, so several sessions can
land on the same day when time is short.

Completing a session leaves the original assignment or exam open. Complete the
original item when the work is submitted or the exam is finished. Completing it also
completes any remaining linked sessions. Reopening the original preserves completed
preparation; individual sessions can then be reopened if necessary.

To change the course, type, deadline, or estimated workload of a planned item, clear
its generated plan first. This asks for confirmation and removes those sessions,
including their completion history. The original item remains. Titles, priorities,
and notes remain editable. Changing the original item’s priority also updates its
generated sessions. Generated sessions cannot be individually removed or
rescheduled, because that would break the exact workload allocation.

### Dates and local persistence

Deadlines are calendar dates in the computer's local timezone. Today and overdue
are calculated from the actual date, and the next-seven-days view includes today
plus six days. Audit timestamps are stored as timezone-aware UTC values.

All data lives in `instance/studentflow.db`, on the computer running Flask, not in
browser localStorage. It is excluded from Git. This is a local single-user app;
browsers using the same server share the same data.

Startup applies additive schema migrations. When upgrading the original database,
a one-time `instance/studentflow.pre-planner.bak` backup is made first. Existing
records stay intact. Original creation times were not recorded, so migrated records
use the migration time. Previously completed records retain an unknown completion
time, displayed as “Completed earlier”, rather than an invented timestamp.

## Getting Started

From the `studentflow` directory:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

Open [StudentFlow locally](http://127.0.0.1:5000). Stop with Ctrl+C.
On subsequent visits, activate the environment and run `python app.py`.
If port 5000 is busy, run `python -m flask --app app run --port 5001` instead.

### Manual walkthrough

1. Add a course with a name, code, color, and instructor.
2. Click it in the sidebar, then edit its details.
3. Add an assignment due today and an exam several days away; give the exam a
   240-minute estimate.
4. Check Today, This week, date links, and the type/priority filters.
5. Open the exam and generate study sessions. Verify the total is 240 minutes.
6. Generate again: no duplicates should appear.
7. Complete a session, inspect Completed, and reopen it.
8. Refresh or restart the app: courses, edits, plans, and progress remain saved.
9. Try deleting a course with items. Cancel first, then confirm only if you intend
   to remove the course and all associated work.

### Tests and checks

```sh
python -m unittest discover -s tests -v
python -m compileall -q app.py studentflow tests
```

Optional, if Node.js is installed, check the small enhancement script:

```sh
node --check static/app.js
```

Tests use temporary SQLite databases and Flask's test client; they do not start a
listening server or modify your real study data. They cover the original eight
workflows, migrations, date boundaries, recommendation scoring, session totals,
duplicate prevention, filtering, completion history, and deletion safety.
There is no configured standalone Python linter, static type checker, or build step.

### Code layout

- `app.py`: Flask routes and response handling.
- `studentflow/database.py`: database access, migrations, and backup.
- `studentflow/models.py`: record shapes and shared vocabulary.
- `studentflow/dates.py`: calendar-date utilities and audit timestamps.
- `studentflow/validation.py`: form validation.
- `studentflow/dashboard.py`: derived counts, filters, and display data.
- `studentflow/planning.py`: pure recommendation and session-distribution logic.
- `studentflow/plans.py`: transactional plan storage.
- `templates/`: the dashboard and reusable Jinja partials.
- `static/style.css`: existing styling with small feature additions.
- `static/app.js`: progressive form enhancement; no duplicated planning logic.
- `tests/`: regression and business-logic tests.

## Future Improvements

- User accounts and separate workspaces.
- PostgreSQL and cloud sync.
- Notifications and deadline reminders.
- Calendar integration and scheduling around personal availability.
- Optional AI-assisted task breakdown.

These are future ideas, not current features. The app does not currently provide
cloud sync, background reminders, external calendars, or a focus timer.
