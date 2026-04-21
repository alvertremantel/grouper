"""Tests for uninstall helper functions in grouper_install/setup.py."""

from __future__ import annotations

from pathlib import Path

import pytest
from grouper_install.setup import (
    _copy_installer_to_stable_location,
    _remove_dir_safe,
    _remove_empty_parent,
    _remove_shortcut_safe,
    _stable_installer_path,
)


class TestStableInstallerPath:
    def test_returns_path_under_program_files(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PROGRAMFILES", "C:\\Program Files")
        result = _stable_installer_path()
        assert result == Path("C:/Program Files/Grouper Apps/Installer/setup.exe")


class TestCopyInstallerToStableLocation:
    def test_copies_executable(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PROGRAMFILES", str(tmp_path / "PF"))
        monkeypatch.setattr("sys.argv", [str(tmp_path / "mysetup.exe")])
        (tmp_path / "mysetup.exe").write_bytes(b"fake exe content")

        result = _copy_installer_to_stable_location()
        assert result is None
        dest = tmp_path / "PF" / "Grouper Apps" / "Installer" / "setup.exe"
        assert dest.exists()
        assert dest.read_bytes() == b"fake exe content"

    def test_returns_error_on_failure(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PROGRAMFILES", str(tmp_path / "PF"))
        monkeypatch.setattr("sys.argv", [str(tmp_path / "nonexistent.exe")])
        monkeypatch.setattr("sys.executable", str(tmp_path / "also_nonexistent.exe"))

        result = _copy_installer_to_stable_location()
        assert result is not None


class TestRemoveShortcutSafe:
    def test_removes_existing_shortcut(self, tmp_path: Path) -> None:
        lnk = tmp_path / "Grouper.lnk"
        lnk.write_text("shortcut")
        result = _remove_shortcut_safe(str(lnk))
        assert result is None
        assert not lnk.exists()

    def test_noop_when_missing(self, tmp_path: Path) -> None:
        lnk = tmp_path / "missing.lnk"
        result = _remove_shortcut_safe(str(lnk))
        assert result is None

    def test_removes_empty_grouper_parent(self, tmp_path: Path) -> None:
        grouper_dir = tmp_path / "Grouper"
        grouper_dir.mkdir()
        lnk = grouper_dir / "Grouper.lnk"
        lnk.write_text("shortcut")

        result = _remove_shortcut_safe(str(lnk))
        assert result is None
        assert not grouper_dir.exists()

    def test_keeps_nonempty_grouper_parent(self, tmp_path: Path) -> None:
        grouper_dir = tmp_path / "Grouper"
        grouper_dir.mkdir()
        lnk = grouper_dir / "Grouper.lnk"
        lnk.write_text("shortcut")
        (grouper_dir / "other.txt").write_text("keep me")

        result = _remove_shortcut_safe(str(lnk))
        assert result is None
        assert not lnk.exists()
        assert grouper_dir.exists()

    def test_reports_os_error(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        lnk = tmp_path / "locked.lnk"
        lnk.write_text("shortcut")

        import os
        original_unlink = os.unlink

        def _raise(path, *args, **kwargs) -> None:
            if str(path) == str(lnk):
                raise OSError("locked")
            original_unlink(path, *args, **kwargs)

        monkeypatch.setattr("os.unlink", _raise)
        result = _remove_shortcut_safe(str(lnk))
        assert result is not None
        assert "locked" in result


class TestRemoveDirSafe:
    def test_removes_existing_dir(self, tmp_path: Path) -> None:
        d = tmp_path / "target"
        d.mkdir()
        (d / "file.txt").write_text("content")

        result = _remove_dir_safe(str(d))
        assert result is None
        assert not d.exists()

    def test_noop_when_missing(self, tmp_path: Path) -> None:
        result = _remove_dir_safe(str(tmp_path / "nonexistent"))
        assert result is None

    def test_reports_os_error(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        d = tmp_path / "locked"
        d.mkdir()

        def _raise(*args, **kwargs) -> None:
            raise OSError("access denied")

        monkeypatch.setattr("shutil.rmtree", _raise)
        result = _remove_dir_safe(str(d))
        assert result is not None
        assert "access denied" in result


class TestRemoveEmptyParent:
    def test_removes_empty_grandparent(self, tmp_path: Path) -> None:
        nested = tmp_path / "a" / "b" / "c"
        nested.mkdir(parents=True)
        nested.rmdir()
        _remove_empty_parent(str(nested))
        assert not (tmp_path / "a").exists()

    def test_removes_empty_parents_recursively(self, tmp_path: Path) -> None:
        nested = tmp_path / "a" / "b" / "c"
        nested.mkdir(parents=True)
        _remove_empty_parent(str(nested))
        assert (tmp_path / "a").exists()

    def test_stops_at_nonempty_parent(self, tmp_path: Path) -> None:
        nested = tmp_path / "a" / "b" / "c"
        nested.mkdir(parents=True)
        (tmp_path / "a" / "keeper.txt").write_text("keep")

        _remove_empty_parent(str(nested))
        assert (tmp_path / "a").exists()

    def test_stops_at_missing_parent(self, tmp_path: Path) -> None:
        _remove_empty_parent(str(tmp_path / "nonexistent" / "path"))
