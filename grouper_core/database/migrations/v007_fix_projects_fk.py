"""v007_fix_projects_fk.py — Rebuild projects table with ON DELETE CASCADE."""

import sqlite3

VERSION = 7
DESCRIPTION = "Fix projects FK constraint (add ON DELETE CASCADE)"


def upgrade(conn: sqlite3.Connection) -> None:
    # SQLite requires a full table-rebuild to change FK definitions.
    # Migration v2 added board_id without CASCADE; fresh installs are fine
    # (initial schema has it), but upgraded databases need the rebuild.
    #
    # The migration runner manages transaction boundaries (it calls
    # conn.commit() after a successful upgrade).  We must NOT issue
    # explicit BEGIN/COMMIT/ROLLBACK here -- doing so conflicts with
    # the runner's own transaction and can cause "cannot start a
    # transaction within a transaction" on some SQLite configurations.
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("""
            CREATE TABLE projects_new (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                board_id    INTEGER NOT NULL DEFAULT 1,
                name        TEXT NOT NULL UNIQUE,
                description TEXT,
                is_archived INTEGER DEFAULT 0,
                created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                archived_at TEXT,
                FOREIGN KEY (board_id) REFERENCES boards(id) ON DELETE CASCADE
            )
        """)
        conn.execute("""
            INSERT INTO projects_new
            SELECT id, COALESCE(board_id, 1), name, description,
                   is_archived, created_at, archived_at
            FROM projects
        """)
        conn.execute("DROP TABLE projects")
        conn.execute("ALTER TABLE projects_new RENAME TO projects")
        # Verify no FK violations were introduced by the rebuild
        violations = conn.execute("PRAGMA foreign_key_check(projects)").fetchall()
        if violations:
            raise RuntimeError(f"FK violations after projects rebuild: {violations}")
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
