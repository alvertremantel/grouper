"""helpers.py -- Shared pywinauto utilities for Grouper E2E tests."""

import sqlite3
import time
from datetime import datetime
from pathlib import Path

from pywinauto.controls.uiawrapper import UIAWrapper

# Timing constants
ANIMATION_WAIT = 0.8  # card slide-in is 500ms; add margin
TIMER_TICK = 1.5  # QTimer fires at 1000ms intervals
REFRESH_WAIT = 0.3  # view refresh after navigation (showEvent)


# ---------------------------------------------------------------------------
# Navigation helpers
# ---------------------------------------------------------------------------


def click_sidebar_button(main_window: UIAWrapper, view_name: str) -> None:
    """Click a sidebar navigation button by matching its text.

    Sidebar buttons have text like "🏠  Dashboard", "⏱  Time Tracker", etc.
    They are checkable QPushButtons, so UIA exposes them as CheckBox controls.
    Uses invoke() rather than click_input() because the UIA Invoke pattern
    reliably triggers Qt signals regardless of window geometry.
    """
    sidebar_buttons = main_window.descendants(control_type="CheckBox")
    for btn in sidebar_buttons:
        try:
            if view_name in btn.window_text():
                btn.invoke()
                time.sleep(REFRESH_WAIT)
                return
        except Exception:
            continue
    raise ValueError(f"Sidebar button for '{view_name}' not found")


# ---------------------------------------------------------------------------
# Element finders
# ---------------------------------------------------------------------------


def find_by_name_substring(parent: UIAWrapper, control_type: str, substring: str) -> UIAWrapper:
    """Find a control by partial name match within a parent."""
    controls = parent.descendants(control_type=control_type)
    for c in controls:
        try:
            if substring in c.window_text():
                return c
        except Exception:
            continue
    raise ValueError(f"No {control_type} containing '{substring}' found")


def find_all_by_name_substring(
    parent: UIAWrapper, control_type: str, substring: str
) -> list[UIAWrapper]:
    """Find all controls matching a partial name within a parent."""
    results: list[UIAWrapper] = []
    controls = parent.descendants(control_type=control_type)
    for c in controls:
        try:
            if substring in c.window_text():
                results.append(c)
        except Exception:
            continue
    return results


# ---------------------------------------------------------------------------
# Wait helpers
# ---------------------------------------------------------------------------


def wait_for_animation(duration: float = ANIMATION_WAIT) -> None:
    """Wait for Qt animations (card slide-in is 250ms)."""
    time.sleep(duration)


def wait_for_element(
    parent: UIAWrapper,
    control_type: str,
    name_substring: str,
    timeout: float = 5.0,
) -> UIAWrapper:
    """Wait until an element with matching text appears."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            return find_by_name_substring(parent, control_type, name_substring)
        except ValueError:
            time.sleep(0.3)
    raise TimeoutError(
        f"Element {control_type} containing '{name_substring}' not found within {timeout}s"
    )


def wait_for_element_gone(
    parent: UIAWrapper,
    control_type: str,
    name_substring: str,
    timeout: float = 5.0,
) -> None:
    """Wait until an element with matching text disappears."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            find_by_name_substring(parent, control_type, name_substring)
            time.sleep(0.3)
        except ValueError:
            return  # Element is gone
    raise TimeoutError(
        f"Element {control_type} containing '{name_substring}' still present after {timeout}s"
    )


def select_combo_item(combo: UIAWrapper, item_text: str) -> None:
    """Select an item in a Qt QComboBox by expanding and clicking the ListItem.

    Qt combo boxes don't expose the UIA SelectionItem pattern properly,
    so we expand, find the ListItem, and click it.
    """
    combo.expand()
    time.sleep(0.3)
    items = combo.descendants(control_type="ListItem")
    for item in items:
        try:
            if item_text in item.window_text():
                item.click_input()
                time.sleep(0.3)
                return
        except Exception:
            continue
    combo.collapse()
    raise ValueError(f"Combo item '{item_text}' not found")


def count_controls(parent: UIAWrapper, control_type: str) -> int:
    """Count all descendants of a given control type."""
    return len(parent.descendants(control_type=control_type))


# ---------------------------------------------------------------------------
# Database seeding helpers
# ---------------------------------------------------------------------------


def seed_activity_via_db(
    data_dir: Path,
    name: str,
    groups: list[str] | None = None,
    is_background: bool = False,
) -> int:
    """Insert an activity into the test database for setup.

    Must be called AFTER the app has started (so the schema exists).
    Returns the activity id.
    """
    db_path = data_dir / "grouper.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")

    now = datetime.now().isoformat()
    cur = conn.execute(
        "INSERT INTO activities (name, is_background, created_at) VALUES (?, ?, ?)",
        (name, 1 if is_background else 0, now),
    )
    aid = cur.lastrowid

    if groups:
        for g in groups:
            # Ensure the group exists in the groups table
            row = conn.execute(
                "SELECT id FROM groups WHERE name = ? COLLATE NOCASE", (g,)
            ).fetchone()
            if row:
                gid = row[0]
            else:
                cur2 = conn.execute("INSERT INTO groups (name) VALUES (?)", (g,))
                gid = cur2.lastrowid
            conn.execute(
                "INSERT INTO activity_groups (activity_id, group_id) VALUES (?, ?)",
                (aid, gid),
            )

    conn.commit()
    conn.close()
    return aid


def seed_project_and_board_via_db(
    data_dir: Path,
    project_name: str,
    board_name: str = "Default Board",
) -> tuple[int, int]:
    """Insert a board and project directly into the test database.

    Returns (board_id, project_id).
    """
    db_path = data_dir / "grouper.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")

    now = datetime.now().isoformat()

    # Get or create board
    row = conn.execute("SELECT id FROM boards WHERE name = ?", (board_name,)).fetchone()
    if row:
        board_id = row[0]
    else:
        cur = conn.execute(
            "INSERT INTO boards (name, created_at) VALUES (?, ?)",
            (board_name, now),
        )
        board_id = cur.lastrowid

    # Create project
    cur = conn.execute(
        "INSERT INTO projects (name, board_id, created_at) VALUES (?, ?, ?)",
        (project_name, board_id, now),
    )
    project_id = cur.lastrowid

    conn.commit()
    conn.close()
    return board_id, project_id
