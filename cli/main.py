"""main.py — Grouper CLI entry point and argument parser."""

from __future__ import annotations

import argparse
import sys

from cli.commands import activity, board, dashboard, event, project, session, task


def _get_version() -> str:
    try:
        from importlib.metadata import version

        return version("grouper")
    except Exception:
        return "unknown"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="grouper-cli",
        description="Grouper — command-line interface for time tracking and task management",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {_get_version()}",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Output results as JSON",
    )

    subparsers = parser.add_subparsers(dest="command")
    subparsers.required = True

    # Register each command group
    session.register(subparsers)
    task.register(subparsers)
    activity.register(subparsers)
    event.register(subparsers)
    project.register(subparsers)
    board.register(subparsers)
    dashboard.register(subparsers)

    return parser


def _dispatch(args: argparse.Namespace) -> int:
    """Route parsed args to the correct command handler."""
    cmd = args.command

    if cmd == "session":
        return session.DISPATCH[args.session_action](args)
    elif cmd == "task":
        return task.DISPATCH[args.task_action](args)
    elif cmd == "activity":
        return activity.DISPATCH[args.activity_action](args)
    elif cmd == "event":
        return event.DISPATCH[args.event_action](args)
    elif cmd == "project":
        return project.DISPATCH[args.project_action](args)
    elif cmd == "board":
        return board.DISPATCH[args.board_action](args)
    elif cmd == "dashboard":
        return dashboard.DISPATCH["dashboard"](args)
    elif cmd == "summary":
        return dashboard.DISPATCH[f"summary_{args.summary_action}"](args)
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    import sqlite3

    parser = build_parser()
    args = parser.parse_args(argv)

    from grouper_core.database.connection import init_database

    init_database()

    try:
        return _dispatch(args)
    except ValueError as exc:
        # Catches bad ISO datetime strings, invalid ints, etc.
        print(f"error: invalid value — {exc}", file=sys.stderr)
        return 1
    except (sqlite3.OperationalError, FileNotFoundError):
        print("error: database not found. Run Grouper at least once first.", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
