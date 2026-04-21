"""v019 — Add performance indexes for common query patterns."""

import sqlite3

VERSION = 19
DESCRIPTION = "Add performance indexes for foreign keys and common queries"


def upgrade(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_projects_board ON projects(board_id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_events_calendar_start ON events(calendar_id, start_dt)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_active ON sessions(end_time) WHERE end_time IS NULL"
    )
    conn.commit()
