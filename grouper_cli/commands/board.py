"""board.py — CLI commands for board listing."""

from __future__ import annotations

import argparse
from typing import Any

import grouper_core.database.boards as _boards

from grouper_cli.output import print_json, print_table


def _format_board(b: Any) -> dict[str, Any]:
    return {
        "id": b.id,
        "name": b.name,
    }


def cmd_list(args: argparse.Namespace) -> int:
    boards = _boards.list_boards()
    data = [_format_board(b) for b in boards]
    if args.json:
        print_json(data)
    else:
        print_table(data, columns=["id", "name"], headers=["ID", "Name"])
    return 0


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("board", help="Board management")
    sub = parser.add_subparsers(dest="board_action")
    sub.required = True

    sub.add_parser("list", help="List all boards")


DISPATCH = {
    "list": cmd_list,
}
