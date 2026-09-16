# StudentFlow

A daily study planner built with Python, Flask, and SQLite. Open it to see what
needs attention and choose a realistic next step.

## What you can do

- Organize courses and add assignments, exams, or study sessions.
- Set deadlines, priorities, estimated minutes, and notes.
- See overdue work, today's deadlines, and the next seven days.
- Filter the plan by course; the nearest deadline appears first, with priority
  breaking ties on the same date.
- Edit items, mark them complete, or reopen them from Completed.
- Track completion and estimated work for today (including overdue items).
- Keep your plan after refreshes and server restarts.

Start by adding a course under **My courses**, then use **Get it off your mind**
to add your first deadline. The next-step card and calendar update from your data.
Deleting a course is blocked while it still has study items, including completed
ones. Item deletion is permanent and available from the edit form.

The calendar uses the computer's local date. Next seven days includes today and
six more days. Estimates are planning aids, not a running time tracker. There are
no background notifications or external calendar connections.

## Run locally

Requires Python 3.9 or newer. From this directory:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000. Stop with Ctrl+C. On later visits, only activate the
environment and run `python app.py`.
If port 5000 is busy: `python -m flask --app app run --port 5001`.

## Learning the code

- `app.py`: Python routes, validation, deadline sorting, and database queries.
- `templates/index.html`: the dashboard and HTML forms (Flask fills in your data).
- `static/style.css`: colors, spacing, and mobile layout.
- `instance/studentflow.db`: automatically created SQLite database, ignored by Git.

Python handles the application logic; the browser displays HTML and CSS.
No JavaScript or TypeScript is required to run the new app.
This is a local single-user app; visitors to the same server share courses.

The old Next.js source, including the unfinished unique-ID changes, is preserved
in `legacy/nextjs/` for reference and is not used by the Python app.

## Tests

```sh
python -m unittest discover -s tests -v
```

[Flask introduction](https://flask.palletsprojects.com/en/stable/quickstart/)
