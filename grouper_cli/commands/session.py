"""session.py — CLI commands for time-tracking sessions."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta

import grouper_core.database.sessions as _sessions
from grouper_core.formatting import format_session as _format_session

from grouper_cli.output import format_duration, print_error, print_json, print_table

# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def cmd_active(args: argparse.Namespace) -> int:
    sessions = _sessions.get_active_sessions()
    data = [_format_session(s) for s in sessions]
    if args.json:
        print_json(data)
    else:
        print_table(
            data,
            columns=["id", "activity", "start", "duration_formatted", "paused"],
            headers=["ID", "Activity", "Started", "Duration", "Paused"],
        )
    return 0


def cmd_summary(args: argparse.Namespace) -> int:
    start = datetime.now() - timedelta(days=args.days)
    summary = _sessions.get_summary(start_date=start)
    if args.json:
        print_json(summary)
    else:
        if not summary:
            print(f"No tracked time in the last {args.days} day(s).")
            return 0
        rows = []
        for activity, secs in sorted(summary.items(), key=lambda kv: kv[1], reverse=True):
            rows.append(
                {
                    "activity": activity,
                    "time": format_duration(secs),
                    "seconds": secs,
                }
            )
        print_table(rows, columns=["activity", "time"], headers=["Activity", "Total Time"])
    return 0


def cmd_history(args: argparse.Namespace) -> int:
    sessions = _sessions.get_sessions(
        activity_name=args.activity,
        limit=args.limit,
    )
    data = [_format_session(s) for s in sessions]
    if args.json:
        print_json(data)
    else:
        print_table(
            data,
            columns=["id", "activity", "start", "end", "duration_formatted"],
            headers=["ID", "Activity", "Start", "End", "Duration"],
        )
    return 0


def cmd_start(args: argparse.Namespace) -> int:
    session = _sessions.start_session(args.activity)
    data = _format_session(session)
    if args.json:
        print_json(data)
    else:
        print(f"Started session {data['id']} for '{data['activity']}' at {data['start']}")
    return 0


def cmd_pause(args: argparse.Namespace) -> int:
    session = _sessions.pause_session(args.session_id)
    if session is None:
        print_error(f"Session {args.session_id} not found or already paused.")
        return 1
    data = _format_session(session)
    if args.json:
        print_json(data)
    else:
        print(f"Paused session {data['id']} ({data['activity']})")
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    session = _sessions.resume_session(args.session_id)
    if session is None:
        print_error(f"Session {args.session_id} not found or not paused.")
        return 1
    data = _format_session(session)
    if args.json:
        print_json(data)
    else:
        print(f"Resumed session {data['id']} ({data['activity']})")
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    stopped = _sessions.stop_session(activity_name=args.activity)
    data = [_format_session(s) for s in stopped]
    if args.json:
        print_json(data)
    else:
        if not data:
            print(
                "No active sessions to stop."
                if not args.activity
                else f"No active session for '{args.activity}'."
            )
        else:
            for d in data:
                print(f"Stopped session {d['id']} ({d['activity']}) — {d['duration_formatted']}")
    return 0


# ---------------------------------------------------------------------------
# Subparser registration
# ---------------------------------------------------------------------------


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register the 'session' command group."""
    session_parser = subparsers.add_parser("session", help="Time-tracking sessions")
    session_sub = session_parser.add_subparsers(dest="session_action")
    session_sub.required = True

    # session active
    session_sub.add_parser("active", help="Show active (running) sessions")

    # session summary
    p = session_sub.add_parser("summary", help="Time per activity over N days")
    p.add_argument("--days", type=int, default=7, help="Lookback window (default: 7)")

    # session history
    p = session_sub.add_parser("history", help="Recent completed sessions")
    p.add_argument("--activity", type=str, default=None, help="Filter by activity name")
    p.add_argument("--limit", type=int, default=20, help="Max results (default: 20)")

    # session start
    p = session_sub.add_parser("start", help="Start a time-tracking session")
    p.add_argument("activity", help="Activity name")

    # session pause
    p = session_sub.add_parser("pause", help="Pause an active session")
    p.add_argument("session_id", type=int, help="Session ID to pause")

    # session resume
    p = session_sub.add_parser("resume", help="Resume a paused session")
    p.add_argument("session_id", type=int, help="Session ID to resume")

    # session stop
    p = session_sub.add_parser("stop", help="Stop a running session")
    p.add_argument(
        "activity", nargs="?", default=None, help="Activity name (stops most recent if omitted)"
    )


DISPATCH = {
    "active": cmd_active,
    "summary": cmd_summary,
    "history": cmd_history,
    "start": cmd_start,
    "pause": cmd_pause,
    "resume": cmd_resume,
    "stop": cmd_stop,
}
