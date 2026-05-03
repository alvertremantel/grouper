"""activity.py — CLI commands for activity management."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from typing import Any

import grouper_core.database.activities as _activities
import grouper_core.database.sessions as _sessions

from cli.output import format_duration, print_json, print_table


def _format_activity(a: Any) -> dict[str, Any]:
    return {
        "id": a.id,
        "name": a.name,
        "description": a.description or "",
        "background": a.is_background,
        "archived": a.is_archived,
        "groups": [g.name if hasattr(g, "name") else str(g) for g in (a.groups or [])],
        "tags": [t.name if hasattr(t, "name") else str(t) for t in (a.tags or [])],
    }


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def cmd_list(args: argparse.Namespace) -> int:
    is_bg = None if args.include_background else False
    activities = _activities.list_activities(is_background=is_bg)
    data = [_format_activity(a) for a in activities]
    if args.json:
        print_json(data)
    else:
        print_table(
            data, columns=["id", "name", "background"], headers=["ID", "Name", "Background"]
        )
    return 0


def cmd_time(args: argparse.Namespace) -> int:
    start = datetime.now() - timedelta(days=args.days)
    summary = _sessions.get_summary(start_date=start)
    total_seconds = summary.get(args.name, 0)
    data = {
        "activity_name": args.name,
        "days": args.days,
        "total_seconds": total_seconds,
        "total_formatted": format_duration(total_seconds),
    }
    if args.json:
        print_json(data)
    else:
        print(f"{data['activity_name']}: {data['total_formatted']} over last {data['days']} day(s)")
    return 0


# ---------------------------------------------------------------------------
# Subparser registration
# ---------------------------------------------------------------------------


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("activity", help="Activity management")
    sub = parser.add_subparsers(dest="activity_action")
    sub.required = True

    # activity list
    p = sub.add_parser("list", help="List activities")
    p.add_argument(
        "--no-background",
        dest="include_background",
        action="store_false",
        default=True,
        help="Exclude background activities",
    )

    # activity time
    p = sub.add_parser("time", help="Total tracked time for an activity")
    p.add_argument("name", help="Activity name")
    p.add_argument("--days", type=int, default=30, help="Lookback days (default: 30)")


DISPATCH = {
    "list": cmd_list,
    "time": cmd_time,
}
