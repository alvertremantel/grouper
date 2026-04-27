"""dashboard.py — CLI commands for dashboard and summary views."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from typing import Any

import grouper_core.database.sessions as _sessions
import grouper_core.database.tasks as _tasks
from grouper_core.formatting import filter_upcoming_tasks, start_of_day

from cli.output import format_duration, print_json, print_table


def _format_session_brief(s: Any) -> dict[str, Any]:
    return {
        "id": s.id,
        "activity": s.activity_name,
        "duration_formatted": s.format_duration(),
        "paused": s.is_paused,
    }


def _format_task_brief(t: Any) -> dict[str, Any]:
    return {
        "id": t.id,
        "title": t.title,
        "due_date": t.due_date.isoformat() if t.due_date else "",
        "priority": t.priority,
    }


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def cmd_dashboard(args: argparse.Namespace) -> int:
    active = _sessions.get_active_sessions()
    upcoming_tasks = _tasks.get_tasks_with_due_dates()
    now = datetime.now()
    upcoming = filter_upcoming_tasks(upcoming_tasks, days=7)

    if args.json:
        print_json(
            {
                "active_sessions": [_format_session_brief(s) for s in active],
                "upcoming_tasks": [_format_task_brief(t) for t in upcoming],
                "generated_at": now.isoformat(),
            }
        )
    else:
        print("=== Active Sessions ===")
        if active:
            print_table(
                [_format_session_brief(s) for s in active],
                columns=["id", "activity", "duration_formatted", "paused"],
                headers=["ID", "Activity", "Duration", "Paused"],
            )
        else:
            print("  (none)")
        print()
        print("=== Upcoming Tasks (7 days) ===")
        if upcoming:
            print_table(
                [_format_task_brief(t) for t in upcoming],
                columns=["id", "title", "due_date", "priority"],
                headers=["ID", "Title", "Due Date", "Priority"],
            )
        else:
            print("  (none)")
    return 0


def cmd_summary_today(args: argparse.Namespace) -> int:
    today = start_of_day(datetime.now())
    summary = _sessions.get_summary(start_date=today)
    total = sum(summary.values())

    if args.json:
        print_json(
            {
                "date": today.date().isoformat(),
                "activities": summary,
                "total_seconds": total,
            }
        )
    else:
        print(f"=== Today ({today.date().isoformat()}) ===")
        if summary:
            rows = [
                {"activity": k, "time": format_duration(v)}
                for k, v in sorted(summary.items(), key=lambda kv: kv[1], reverse=True)
            ]
            print_table(rows, columns=["activity", "time"], headers=["Activity", "Time"])
            print(f"\n  Total: {format_duration(total)}")
        else:
            print("  No tracked time today.")
    return 0


def cmd_summary_week(args: argparse.Namespace) -> int:
    now = datetime.now()
    week_start = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    summary = _sessions.get_summary(start_date=week_start)
    total = sum(summary.values())

    if args.json:
        print_json(
            {
                "week_start": week_start.date().isoformat(),
                "activities": summary,
                "total_seconds": total,
            }
        )
    else:
        print(f"=== This Week (from {week_start.date().isoformat()}) ===")
        if summary:
            rows = [
                {"activity": k, "time": format_duration(v)}
                for k, v in sorted(summary.items(), key=lambda kv: kv[1], reverse=True)
            ]
            print_table(rows, columns=["activity", "time"], headers=["Activity", "Time"])
            print(f"\n  Total: {format_duration(total)}")
        else:
            print("  No tracked time this week.")
    return 0


# ---------------------------------------------------------------------------
# Subparser registration
# ---------------------------------------------------------------------------


def register(subparsers: argparse._SubParsersAction) -> None:
    # dashboard (top-level command, no subcommand)
    subparsers.add_parser("dashboard", help="Show active sessions and upcoming tasks")

    # summary group
    summary_parser = subparsers.add_parser("summary", help="Time summaries")
    summary_sub = summary_parser.add_subparsers(dest="summary_action")
    summary_sub.required = True
    summary_sub.add_parser("today", help="Today's time summary")
    summary_sub.add_parser("week", help="This week's time summary")


DISPATCH = {
    "dashboard": cmd_dashboard,
    "summary_today": cmd_summary_today,
    "summary_week": cmd_summary_week,
}
