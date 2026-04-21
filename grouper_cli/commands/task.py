"""task.py — CLI commands for task management."""

from __future__ import annotations

import argparse
from datetime import datetime
from typing import Any

import grouper_core.database.projects as _projects
import grouper_core.database.tasks as _tasks
from grouper_core.formatting import filter_upcoming_tasks
from grouper_core.operations import sync_task_prerequisites, sync_task_tags

from grouper_cli.output import print_error, print_json, print_table


def _format_task(t: Any) -> dict[str, Any]:
    return {
        "id": t.id,
        "title": t.title,
        "project_id": t.project_id,
        "priority": t.priority,
        "due_date": t.due_date.isoformat() if t.due_date else "",
        "completed": t.is_completed,
        "starred": t.is_starred,
        "tags": t.tags if t.tags else [],
        "prerequisites": t.prerequisites if t.prerequisites else [],
    }


def _parse_int_list(val: str | None) -> list[int] | None:
    if val is None:
        return None
    return [int(x.strip()) for x in val.split(",") if x.strip()]


def _parse_str_list(val: str | None) -> list[str] | None:
    if val is None:
        return None
    return [x.strip() for x in val.split(",") if x.strip()]


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def cmd_list(args: argparse.Namespace) -> int:
    if args.board_id is not None:
        tasks = _tasks.get_tasks_by_board(args.board_id, include_deleted=False)
    else:
        all_projects = _projects.list_projects()
        tasks = []
        for project in all_projects:
            tasks.extend(_tasks.get_tasks(project.id))  # type: ignore[arg-type]

    if not args.include_completed:
        tasks = [t for t in tasks if not t.is_completed]

    data = [_format_task(t) for t in tasks]
    if args.json:
        print_json(data)
    else:
        print_table(
            data,
            columns=["id", "title", "project_id", "priority", "due_date", "completed"],
            headers=["ID", "Title", "Project", "Priority", "Due Date", "Done"],
        )
    return 0


def cmd_upcoming(args: argparse.Namespace) -> int:
    tasks = _tasks.get_tasks_with_due_dates()
    upcoming = filter_upcoming_tasks(tasks, days=args.days)

    data = [_format_task(t) for t in upcoming]
    if args.json:
        print_json(data)
    else:
        print_table(
            data,
            columns=["id", "title", "due_date", "priority"],
            headers=["ID", "Title", "Due Date", "Priority"],
        )
    return 0


def cmd_create(args: argparse.Namespace) -> int:
    parsed_due: datetime | None = None
    if args.due_date:
        parsed_due = datetime.fromisoformat(args.due_date)

    tags = _parse_str_list(args.tags)
    prerequisites = _parse_int_list(args.prerequisites)

    task = _tasks.create_task_with_relations(
        project_id=args.project_id,
        title=args.title,
        priority=args.priority,
        due_date=parsed_due,
        tags=tags,
        prerequisites=prerequisites,
    )
    data = _format_task(task)
    if args.json:
        print_json(data)
    else:
        print(f"Created task {data['id']}: {data['title']}")
    return 0


def cmd_complete(args: argparse.Namespace) -> int:
    blockers = _tasks.complete_task(args.task_id)
    if blockers:
        blocker_data = [_format_task(b) for b in blockers]
        if args.json:
            print_json(
                {"task_id": args.task_id, "status": "blocked", "unmet_prerequisites": blocker_data}
            )
        else:
            print_error(f"Task {args.task_id} is blocked by unmet prerequisites:")
            for b in blocker_data:
                print(f"  - #{b['id']}: {b['title']}")
        return 1

    if args.json:
        print_json({"task_id": args.task_id, "status": "completed"})
    else:
        print(f"Completed task {args.task_id}")
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    kwargs: dict[str, Any] = {}
    if args.title is not None:
        kwargs["title"] = args.title
    if args.priority is not None:
        kwargs["priority"] = args.priority
    if args.due_date is not None:
        kwargs["due_date"] = datetime.fromisoformat(args.due_date) if args.due_date else None

    _tasks.update_task(args.task_id, **kwargs)

    if args.tags is not None:
        tag_list = _parse_str_list(args.tags) or []
        sync_task_tags(args.task_id, tag_list)
        kwargs["tags"] = tag_list

    if args.prerequisites is not None:
        prereq_list = _parse_int_list(args.prerequisites) or []
        sync_task_prerequisites(args.task_id, prereq_list)
        kwargs["prerequisites"] = prereq_list

    if args.json:
        print_json({"task_id": args.task_id, "updated": kwargs})
    else:
        if kwargs:
            fields = ", ".join(kwargs.keys())
            print(f"Updated task {args.task_id}: {fields}")
        else:
            print(f"No changes specified for task {args.task_id}")
    return 0


# ---------------------------------------------------------------------------
# Subparser registration
# ---------------------------------------------------------------------------


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("task", help="Task management")
    sub = parser.add_subparsers(dest="task_action")
    sub.required = True

    # task list
    p = sub.add_parser("list", help="List tasks")
    p.add_argument("--board-id", type=int, default=None, help="Filter by board ID")
    p.add_argument("--include-completed", action="store_true", help="Include completed tasks")

    # task upcoming
    p = sub.add_parser("upcoming", help="Tasks due within N days")
    p.add_argument("--days", type=int, default=7, help="Look-ahead days (default: 7)")

    # task create
    p = sub.add_parser("create", help="Create a new task")
    p.add_argument("title", help="Task title")
    p.add_argument("--project-id", type=int, required=True, help="Project ID")
    p.add_argument("--priority", type=int, default=0, help="Priority (0=none, 1=high)")
    p.add_argument("--due-date", type=str, default=None, help="Due date (ISO format)")
    p.add_argument("--tags", type=str, default=None, help="Comma-separated tag names")
    p.add_argument("--prerequisites", type=str, default=None, help="Comma-separated task IDs")

    # task complete
    p = sub.add_parser("complete", help="Mark a task as completed")
    p.add_argument("task_id", type=int, help="Task ID to complete")

    # task update
    p = sub.add_parser("update", help="Update a task")
    p.add_argument("task_id", type=int, help="Task ID to update")
    p.add_argument("--title", type=str, default=None, help="New title")
    p.add_argument("--priority", type=int, default=None, help="New priority")
    p.add_argument(
        "--due-date", type=str, default=None, help="New due date (ISO), or empty to clear"
    )
    p.add_argument("--tags", type=str, default=None, help="Replace tags (comma-separated)")
    p.add_argument(
        "--prerequisites",
        type=str,
        default=None,
        help="Replace prerequisites (comma-separated IDs)",
    )


DISPATCH = {
    "list": cmd_list,
    "upcoming": cmd_upcoming,
    "create": cmd_create,
    "complete": cmd_complete,
    "update": cmd_update,
}
