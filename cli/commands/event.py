"""event.py — CLI commands for calendar events."""

from __future__ import annotations

import argparse
from datetime import datetime
from typing import Any

import grouper_core.database.calendars as _calendars
import grouper_core.database.events as _events

from cli.output import print_error, print_json, print_table


def _format_event(e: Any) -> dict[str, Any]:
    return {
        "id": e.id,
        "title": e.title,
        "calendar_id": e.calendar_id,
        "start": e.start_dt.isoformat() if e.start_dt else "",
        "end": e.end_dt.isoformat() if e.end_dt else "",
        "all_day": e.all_day,
        "location": e.location or "",
        "description": e.description or "",
    }


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def cmd_list(args: argparse.Namespace) -> int:
    start = datetime.fromisoformat(args.start)
    end = datetime.fromisoformat(args.end)
    events = _events.list_events_for_range(start, end)
    data = [_format_event(e) for e in events]
    if args.json:
        print_json(data)
    else:
        print_table(
            data,
            columns=["id", "title", "start", "end", "all_day", "location"],
            headers=["ID", "Title", "Start", "End", "All Day", "Location"],
        )
    return 0


def cmd_create(args: argparse.Namespace) -> int:
    cal_id = (
        args.calendar_id if args.calendar_id is not None else _calendars.get_default_calendar_id()
    )
    event = _events.create_event(
        calendar_id=cal_id,
        title=args.title,
        start_dt=datetime.fromisoformat(args.start),
        end_dt=datetime.fromisoformat(args.end),
    )
    data = _format_event(event)
    if args.json:
        print_json(data)
    else:
        print(f"Created event {data['id']}: {data['title']} ({data['start']} - {data['end']})")
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    existing = _events.get_event(args.event_id)
    if existing is None:
        print_error(f"Event {args.event_id} not found")
        return 1

    kwargs: dict[str, Any] = {}
    if args.title is not None:
        kwargs["title"] = args.title
    if args.description is not None:
        kwargs["description"] = args.description
    if args.location is not None:
        kwargs["location"] = args.location
    if args.start is not None:
        kwargs["start_dt"] = datetime.fromisoformat(args.start)
    if args.end is not None:
        kwargs["end_dt"] = datetime.fromisoformat(args.end)
    if args.all_day is not None:
        kwargs["all_day"] = args.all_day

    _events.update_event(args.event_id, **kwargs)

    if args.json:
        serialized = {
            k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in kwargs.items()
        }
        print_json({"event_id": args.event_id, "updated": serialized})
    else:
        if kwargs:
            fields = ", ".join(kwargs.keys())
            print(f"Updated event {args.event_id}: {fields}")
        else:
            print(f"No changes specified for event {args.event_id}")
    return 0


def cmd_delete(args: argparse.Namespace) -> int:
    existing = _events.get_event(args.event_id)
    if existing is None:
        print_error(f"Event {args.event_id} not found")
        return 1

    _events.delete_event(args.event_id)
    if args.json:
        print_json({"event_id": args.event_id, "status": "deleted"})
    else:
        print(f"Deleted event {args.event_id}")
    return 0


# ---------------------------------------------------------------------------
# Subparser registration
# ---------------------------------------------------------------------------


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("event", help="Calendar events")
    sub = parser.add_subparsers(dest="event_action")
    sub.required = True

    # event list
    p = sub.add_parser("list", help="List events in a date range")
    p.add_argument("--start", required=True, help="Start date (ISO format)")
    p.add_argument("--end", required=True, help="End date (ISO format)")

    # event create
    p = sub.add_parser("create", help="Create a calendar event")
    p.add_argument("title", help="Event title")
    p.add_argument("--start", required=True, help="Start datetime (ISO format)")
    p.add_argument("--end", required=True, help="End datetime (ISO format)")
    p.add_argument(
        "--calendar-id", type=int, default=None, help="Calendar ID (uses default if omitted)"
    )

    # event update
    p = sub.add_parser("update", help="Update a calendar event")
    p.add_argument("event_id", type=int, help="Event ID to update")
    p.add_argument("--title", type=str, default=None)
    p.add_argument("--description", type=str, default=None)
    p.add_argument("--location", type=str, default=None)
    p.add_argument("--start", type=str, default=None, help="New start datetime (ISO)")
    p.add_argument("--end", type=str, default=None, help="New end datetime (ISO)")
    p.add_argument("--all-day", action=argparse.BooleanOptionalAction, default=None)

    # event delete
    p = sub.add_parser("delete", help="Delete a calendar event")
    p.add_argument("event_id", type=int, help="Event ID to delete")


DISPATCH = {
    "list": cmd_list,
    "create": cmd_create,
    "update": cmd_update,
    "delete": cmd_delete,
}
