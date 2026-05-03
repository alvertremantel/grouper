"""Data fetching and HTML helper functions for the web dashboard.

These are used by Jinja2 templates and route handlers.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from grouper_core.colors import theme_colors
from grouper_core.config import get_config
from markupsafe import Markup

# ---------------------------------------------------------------------------
# Display-limit constants
# ---------------------------------------------------------------------------

DASHBOARD_UPCOMING_LIMIT = 10
DASHBOARD_DISPLAY_LIMIT = 8
SUMMARY_TOP_ACTIVITIES = 10
SUMMARY_DEFAULT_DAYS = 7

# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def fmt_seconds(secs: int) -> str:
    h, r = divmod(secs, 3600)
    m, s = divmod(r, 60)
    return f"{h}h {m:02d}m {s:02d}s"


def fmt_hours(secs: int) -> str:
    h = secs / 3600
    return f"{h:.1f}h"


def priority_chip(priority: int) -> Markup:
    labels = {1: "P1", 2: "P2", 3: "P3", 4: "P4"}
    css_cls = {1: "p1", 2: "p2", 3: "p3", 4: "p4"}
    if priority not in labels:
        return Markup("")
    return Markup('<span class="priority-chip %s">%s</span>') % (
        css_cls[priority],
        labels[priority],
    )


def due_span(due_date: datetime | None, now: datetime | None = None) -> Markup:
    if due_date is None:
        return Markup("")
    today = (now or datetime.now()).date()
    d = due_date.date() if isinstance(due_date, datetime) else due_date
    delta = (d - today).days
    if delta < 0:
        css = "due-overdue"
        label = f"overdue {abs(delta)}d"
    elif delta == 0:
        css = "due-today"
        label = "due today"
    elif delta <= 3:
        css = "due-soon"
        label = f"due {d.strftime('%b %d')}"
    else:
        css = "due-date"
        label = d.strftime("%b %d")
    return Markup('<span class="%s">%s</span>') % (css, label)


# ---------------------------------------------------------------------------
# Data loaders — fetch from DB and return template-ready dicts
# ---------------------------------------------------------------------------


def get_dashboard_data(now: datetime | None = None) -> dict:
    """Fetch data for the dashboard page."""
    from grouper_core.database.projects import get_project_by_id
    from grouper_core.database.sessions import get_active_sessions
    from grouper_core.database.tasks import get_tasks_with_due_dates

    now = now or datetime.now()
    active = get_active_sessions()
    upcoming = get_tasks_with_due_dates()[:DASHBOARD_UPCOMING_LIMIT]

    # Batch-load projects to avoid N+1
    display_tasks = upcoming[:DASHBOARD_DISPLAY_LIMIT]
    project_ids = {t.project_id for t in display_tasks}
    project_map: dict[int, str] = {}
    for pid in project_ids:
        proj = get_project_by_id(pid)
        project_map[pid] = proj.name if proj else f"#{pid}"

    return {
        "active_sessions": active,
        "upcoming_tasks": display_tasks,
        "project_map": project_map,
        "now": now,
    }


def get_tasks_data(now: datetime | None = None) -> dict:
    """Fetch data for the tasks page."""
    from grouper_core.database.boards import list_boards
    from grouper_core.database.projects import list_projects
    from grouper_core.database.tasks import get_tasks_by_board

    now = now or datetime.now()
    boards = list_boards()
    board_data = []

    for board in boards:
        projects = list_projects(board_id=board.id)
        if not projects:
            continue

        all_board_tasks = [t for t in get_tasks_by_board(board.id) if not t.is_completed]
        tasks_by_project: dict[int, list] = {}
        for t in all_board_tasks:
            tasks_by_project.setdefault(t.project_id, []).append(t)

        project_data = []
        total_tasks = 0
        for proj in projects:
            tasks = tasks_by_project.get(proj.id, [])
            total_tasks += len(tasks)
            if tasks:
                project_data.append({"project": proj, "tasks": tasks})

        board_data.append(
            {
                "board": board,
                "projects": project_data,
                "total_tasks": total_tasks,
            }
        )

    return {"boards": board_data, "now": now}


def get_summary_data(now: datetime | None = None) -> dict:
    """Fetch data for the summary page."""
    from grouper_core.database.sessions import get_summary
    from grouper_core.database.tasks import get_tasks_with_due_dates

    now = now or datetime.now()
    p = theme_colors(get_config().theme)
    end = now
    start = end - timedelta(days=SUMMARY_DEFAULT_DAYS)
    totals = get_summary(start_date=start, end_date=end)

    total_secs = sum(totals.values())
    top = sorted(totals.items(), key=lambda x: x[1], reverse=True)[:SUMMARY_TOP_ACTIVITIES]
    max_secs = top[0][1] if top else 1

    upcoming = get_tasks_with_due_dates()
    today = now.date()
    overdue = [t for t in upcoming if t.due_date and t.due_date.date() < today]
    due_today = [t for t in upcoming if t.due_date and t.due_date.date() == today]

    return {
        "total_secs": total_secs,
        "num_activities": len(totals),
        "num_open_tasks": len(upcoming),
        "num_overdue": len(overdue),
        "num_due_today": len(due_today),
        "top_activities": top,
        "max_secs": max_secs,
        "days": SUMMARY_DEFAULT_DAYS,
        "palette": p,
        "now": now,
    }
