"""
test_task_links.py — Unit tests for the task_links CRUD module.

Uses an isolated temp database via the root conftest's ``isolated_db``
fixture (autouse) so no real data is touched.
"""

import sqlite3
from pathlib import Path


def _seed_task(data_dir: Path) -> int:
    """Insert a minimal board → project → task chain and return task id."""
    db_path = data_dir / "grouper.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        "INSERT OR IGNORE INTO boards (id, name, created_at) VALUES (1, 'B', datetime('now'))"
    )
    conn.execute(
        "INSERT OR IGNORE INTO projects (id, board_id, name, created_at) VALUES (1, 1, 'P', datetime('now'))"
    )
    cur = conn.execute(
        "INSERT INTO tasks (project_id, title, created_at) VALUES (1, 'Test task', datetime('now'))"
    )
    task_id = cur.lastrowid
    conn.commit()
    conn.close()
    return task_id


# ---------------------------------------------------------------------------
# detect_link_type
# ---------------------------------------------------------------------------


class TestDetectLinkType:
    def _fn(self):
        from desktop.database.task_links import detect_link_type

        return detect_link_type

    def test_http_url(self):
        assert self._fn()("http://example.com") == "url"

    def test_https_url(self):
        assert self._fn()("https://jira.example.com/browse/PROJ-123") == "url"

    def test_file_uri(self):
        assert self._fn()("file:///C:/Users/notes.txt") == "file"

    def test_windows_path(self):
        assert self._fn()(r"C:\Users\cole\notes.txt") == "file"

    def test_unix_absolute_path(self):
        assert self._fn()("/home/cole/notes.txt") == "file"

    def test_tilde_path(self):
        assert self._fn()("~/documents/spec.md") == "file"

    def test_unc_path(self):
        assert self._fn()(r"\\server\share\file.txt") == "file"

    def test_unc_path_forward_slash(self):
        # Forward-slash path also detected as file (starts with "/")
        assert self._fn()("//server/share") == "file"

    def test_bare_string_defaults_url(self):
        assert self._fn()("example.com") == "url"


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


class TestAddLink:
    def test_add_url_link(self, isolated_db):
        task_id = _seed_task(isolated_db)
        from desktop.database.task_links import add_link

        link = add_link(task_id, "https://example.com", label="Example")
        assert link.id is not None
        assert link.task_id == task_id
        assert link.url == "https://example.com"
        assert link.label == "Example"
        assert link.link_type == "url"

    def test_add_file_link_auto_detects_type(self, isolated_db):
        task_id = _seed_task(isolated_db)
        from desktop.database.task_links import add_link

        link = add_link(task_id, r"C:\notes.txt")
        assert link.link_type == "file"

    def test_blank_label_stored_as_none(self, isolated_db):
        task_id = _seed_task(isolated_db)
        from desktop.database.task_links import add_link

        link = add_link(task_id, "https://example.com", label="   ")
        assert link.label is None

    def test_url_is_stripped(self, isolated_db):
        task_id = _seed_task(isolated_db)
        from desktop.database.task_links import add_link

        link = add_link(task_id, "  https://example.com  ")
        assert link.url == "https://example.com"


class TestGetLinksForTask:
    def test_empty_when_no_links(self, isolated_db):
        task_id = _seed_task(isolated_db)
        from desktop.database.task_links import get_links_for_task

        assert get_links_for_task(task_id) == []

    def test_returns_added_links(self, isolated_db):
        task_id = _seed_task(isolated_db)
        from desktop.database.task_links import add_link, get_links_for_task

        add_link(task_id, "https://a.com", label="A")
        add_link(task_id, "https://b.com", label="B")
        links = get_links_for_task(task_id)
        assert len(links) == 2
        assert {lnk.url for lnk in links} == {"https://a.com", "https://b.com"}

    def test_does_not_return_other_task_links(self, isolated_db):
        db_path = isolated_db / "grouper.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            "INSERT OR IGNORE INTO boards (id, name, created_at) VALUES (1, 'B', datetime('now'))"
        )
        conn.execute(
            "INSERT OR IGNORE INTO projects (id, board_id, name, created_at) VALUES (1, 1, 'P', datetime('now'))"
        )
        cur1 = conn.execute(
            "INSERT INTO tasks (project_id, title, created_at) VALUES (1, 'T1', datetime('now'))"
        )
        cur2 = conn.execute(
            "INSERT INTO tasks (project_id, title, created_at) VALUES (1, 'T2', datetime('now'))"
        )
        t1, t2 = cur1.lastrowid, cur2.lastrowid
        conn.commit()
        conn.close()

        from desktop.database.task_links import add_link, get_links_for_task

        add_link(t1, "https://t1.com")
        add_link(t2, "https://t2.com")
        result = get_links_for_task(t1)
        assert len(result) == 1
        assert result[0].url == "https://t1.com"


class TestDeleteLink:
    def test_delete_removes_link(self, isolated_db):
        task_id = _seed_task(isolated_db)
        from desktop.database.task_links import add_link, delete_link, get_links_for_task

        link = add_link(task_id, "https://example.com")
        delete_link(link.id)
        assert get_links_for_task(task_id) == []

    def test_delete_nonexistent_is_noop(self, isolated_db):
        _seed_task(isolated_db)
        from desktop.database.task_links import delete_link

        delete_link(99999)  # should not raise


class TestUpdateLink:
    def test_update_url(self, isolated_db):
        task_id = _seed_task(isolated_db)
        from desktop.database.task_links import add_link, get_links_for_task, update_link

        link = add_link(task_id, "https://old.com")
        update_link(link.id, url="https://new.com")
        updated = get_links_for_task(task_id)[0]
        assert updated.url == "https://new.com"
        assert updated.link_type == "url"

    def test_update_label(self, isolated_db):
        task_id = _seed_task(isolated_db)
        from desktop.database.task_links import add_link, get_links_for_task, update_link

        link = add_link(task_id, "https://example.com", label="Old")
        update_link(link.id, label="New Label")
        updated = get_links_for_task(task_id)[0]
        assert updated.label == "New Label"

    def test_update_nothing_is_noop(self, isolated_db):
        task_id = _seed_task(isolated_db)
        from desktop.database.task_links import add_link, get_links_for_task, update_link

        link = add_link(task_id, "https://example.com", label="Stay")
        update_link(link.id)
        result = get_links_for_task(task_id)[0]
        assert result.label == "Stay"
