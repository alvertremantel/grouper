"""
boards.py — Board CRUD operations.

Boards are high-level containers that own projects.
"""

from __future__ import annotations

import logging
import sqlite3

from ..models import Board
from .connection import get_connection

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Create / Read
# ---------------------------------------------------------------------------


def create_board(name: str) -> Board:
    """Create a new board.

    Raises:
        sqlite3.IntegrityError: if the name already exists.
    """
    with get_connection() as conn:
        cur = conn.execute("INSERT INTO boards (name) VALUES (?)", (name,))
        conn.commit()
        bid = cur.lastrowid

    return Board(
        id=bid,
        name=name,
    )


def get_board(name: str) -> Board | None:
    """Fetch a board by name (case-sensitive)."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, name, created_at FROM boards WHERE name = ?",
            (name,),
        ).fetchone()
    if row is None:
        return None
    return Board.from_row(row)


def get_board_by_id(board_id: int) -> Board | None:
    """Fetch a board by id."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, name, created_at FROM boards WHERE id = ?",
            (board_id,),
        ).fetchone()
    if row is None:
        return None
    return Board.from_row(row)


def get_or_create_default_board() -> Board:
    """Get the default board, creating it if none exists."""
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO boards (name) VALUES (?)",
            ("Default Board",),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, name, created_at FROM boards WHERE name = ?",
            ("Default Board",),
        ).fetchone()
    return Board.from_row(row)


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


def list_boards() -> list[Board]:
    """Return all boards."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, name, created_at FROM boards ORDER BY name COLLATE NOCASE"
        ).fetchall()

    return [Board.from_row(row) for row in rows]


# ---------------------------------------------------------------------------
# Update / Delete
# ---------------------------------------------------------------------------


def rename_board(board_id: int, new_name: str) -> bool:
    """Rename a board. Returns True if successful, False on IntegrityError."""
    try:
        with get_connection() as conn:
            conn.execute("UPDATE boards SET name = ? WHERE id = ?", (new_name, board_id))
            conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def delete_board(board_id: int) -> bool:
    """Delete a board. Cascades to projects in the DB schema.
    Refuses to delete the default board.
    """
    default = get_or_create_default_board()
    if board_id == default.id:
        logger.warning("Refused to delete default board (id=%d)", board_id)
        return False

    with get_connection() as conn:
        conn.execute("DELETE FROM boards WHERE id = ?", (board_id,))
        conn.commit()
    return True
