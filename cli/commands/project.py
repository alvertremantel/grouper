"""project.py — CLI commands for project listing."""

from __future__ import annotations

import argparse
from typing import Any

import grouper_core.database.projects as _projects

from cli.output import print_json, print_table


def _format_project(p: Any) -> dict[str, Any]:
    return {
        "id": p.id,
        "name": p.name,
        "board_id": p.board_id,
        "description": p.description or "",
        "starred": p.is_starred,
        "archived": p.is_archived,
        "tags": [t.name if hasattr(t, "name") else str(t) for t in (p.tags or [])],
    }


def cmd_list(args: argparse.Namespace) -> int:
    projects = _projects.list_projects(board_id=args.board_id)
    data = [_format_project(p) for p in projects]
    if args.json:
        print_json(data)
    else:
        print_table(
            data,
            columns=["id", "name", "board_id", "starred"],
            headers=["ID", "Name", "Board", "Starred"],
        )
    return 0


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("project", help="Project management")
    sub = parser.add_subparsers(dest="project_action")
    sub.required = True

    p = sub.add_parser("list", help="List projects")
    p.add_argument("--board-id", type=int, default=None, help="Filter by board ID")


DISPATCH = {
    "list": cmd_list,
}
