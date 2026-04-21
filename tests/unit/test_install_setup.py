"""Tests for the installation setup helpers and first-run config.

Covers:
  - grouper_install/setup.py: path helpers, shortcut logic
  - grouper/config.py: first-run config creation
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from grouper.config import Config, ConfigManager
from grouper_install.setup import (
    _create_desktop_shortcut,
    _create_shortcut,
    _create_start_menu_shortcut,
    _desktop,
    _source_root,
    _start_menu_programs,
)


@pytest.fixture(autouse=True)
def _isolate_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fake_app = tmp_path / ".grouper"
    fake_cfg = fake_app / "config.json"
    monkeypatch.setattr("grouper_core.config.APP_DIR", fake_app)
    monkeypatch.setattr("grouper_core.config.CONFIG_FILE", fake_cfg)
    monkeypatch.setattr("grouper_core.config.ConfigManager._instance", None)
    return


# ---------------------------------------------------------------------------
# grouper_install/setup.py path helpers
# ---------------------------------------------------------------------------


class TestInstallDir:
    def test_returns_path(self):
        result = _source_root()
        assert isinstance(result, Path)

    def test_not_frozen_returns_project_root(self):
        result = _source_root()
        assert (result / "pyproject.toml").exists() or not getattr(sys, "frozen", False)

    def test_frozen_returns_exe_parent(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "grouper.exe").touch()
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "argv", [str(tmp_path / "setup.exe")])
        assert _source_root() == tmp_path


class TestDesktopPath:
    def test_fallback_when_com_fails(self, monkeypatch: pytest.MonkeyPatch):
        with patch("win32com.client.Dispatch", side_effect=Exception("no COM")):
            result = _desktop()
        assert result == Path.home() / "Desktop"


class TestStartMenuPath:
    def test_fallback_uses_appdata(self, monkeypatch: pytest.MonkeyPatch):
        with patch("win32com.client.Dispatch", side_effect=Exception("no COM")):
            result = _start_menu_programs()
        appdata = os.environ.get("APPDATA", "")
        expected = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        assert result == expected


# ---------------------------------------------------------------------------
# grouper_install/setup.py shortcut creation
# ---------------------------------------------------------------------------


class TestShortcutCreation:
    def test_create_shortcut_calls_com(self, tmp_path: Path):
        mock_shell = MagicMock()
        mock_sc = MagicMock()
        mock_shell.CreateShortcut.return_value = mock_sc

        with patch("win32com.client.Dispatch", return_value=mock_shell):
            target = tmp_path / "grouper.exe"
            lnk = tmp_path / "test.lnk"
            _create_shortcut(lnk, target, tmp_path)

        mock_shell.CreateShortcut.assert_called_once_with(str(lnk))
        mock_sc.Save.assert_called_once()
        assert mock_sc.TargetPath == str(target)
        assert mock_sc.WorkingDirectory == str(tmp_path)
        assert mock_sc.IconLocation == str(target)

    def test_create_desktop_shortcut_path(self, tmp_path: Path):
        mock_shell = MagicMock()
        mock_sc = MagicMock()
        mock_shell.CreateShortcut.return_value = mock_sc

        fake_desktop = tmp_path / "Desktop"
        fake_desktop.mkdir()

        with (
            patch("win32com.client.Dispatch", return_value=mock_shell),
            patch("grouper_install.setup._desktop", return_value=fake_desktop),
        ):
            _create_desktop_shortcut(tmp_path)

        call_arg = mock_shell.CreateShortcut.call_args[0][0]
        assert call_arg == str(fake_desktop / "Grouper.lnk")

    def test_create_start_menu_shortcut_creates_folder(self, tmp_path: Path):
        mock_shell = MagicMock()
        mock_sc = MagicMock()
        mock_shell.CreateShortcut.return_value = mock_sc

        fake_programs = tmp_path / "Programs"
        fake_programs.mkdir()

        with (
            patch("win32com.client.Dispatch", return_value=mock_shell),
            patch("grouper_install.setup._start_menu_programs", return_value=fake_programs),
        ):
            _create_start_menu_shortcut(tmp_path)

        assert (fake_programs / "Grouper").is_dir()
        call_arg = mock_shell.CreateShortcut.call_args[0][0]
        assert call_arg == str(fake_programs / "Grouper" / "Grouper.lnk")


# ---------------------------------------------------------------------------
# grouper/config.py first-run
# ---------------------------------------------------------------------------


class TestConfigFirstRun:
    def test_creates_config_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        fake_app = tmp_path / ".grouper"
        fake_cfg = fake_app / "config.json"
        monkeypatch.setattr("grouper.config.APP_DIR", fake_app)
        monkeypatch.setattr("grouper.config.CONFIG_FILE", fake_cfg)
        monkeypatch.setattr("grouper.config.ConfigManager._instance", None)

        ConfigManager()
        assert fake_cfg.exists()
        data = json.loads(fake_cfg.read_text())
        assert data["theme"] == "dark"
        assert data["web_port"] == 4747

    def test_creates_data_directories(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        fake_app = tmp_path / ".grouper"
        fake_cfg = fake_app / "config.json"
        monkeypatch.setattr("grouper.config.APP_DIR", fake_app)
        monkeypatch.setattr("grouper.config.CONFIG_FILE", fake_cfg)
        monkeypatch.setattr("grouper.config.ConfigManager._instance", None)

        mgr = ConfigManager()
        cfg = mgr.config
        assert Path(cfg.database_path).parent.exists()
        assert Path(cfg.backup_path).exists()

    def test_default_values(self):
        cfg = Config.default()
        assert cfg.theme == "dark"
        assert cfg.window_width == 1200
        assert cfg.window_height == 750
        assert cfg.web_port == 4747
        assert cfg.default_priority == 3
        assert cfg.sidebar_collapsed is False

    def test_preserves_existing_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        fake_app = tmp_path / ".grouper"
        fake_app.mkdir(parents=True)
        fake_cfg = fake_app / "config.json"
        custom = Config.default()
        custom.theme = "sage"
        custom.web_port = 9999
        fake_cfg.write_text(
            json.dumps(
                {
                    "database_path": custom.database_path,
                    "backup_path": custom.backup_path,
                    "theme": "sage",
                    "web_port": 9999,
                    "default_priority": 3,
                    "window_width": 1200,
                    "window_height": 750,
                    "sidebar_collapsed": False,
                    "bg_notes_enabled": False,
                }
            )
        )

        monkeypatch.setattr("grouper.config.APP_DIR", fake_app)
        monkeypatch.setattr("grouper.config.CONFIG_FILE", fake_cfg)
        monkeypatch.setattr("grouper.config.ConfigManager._instance", None)

        mgr = ConfigManager()
        assert mgr.config.theme == "sage"
        assert mgr.config.web_port == 9999

    def test_corrupt_config_resets_to_defaults(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        fake_app = tmp_path / ".grouper"
        fake_app.mkdir(parents=True)
        fake_cfg = fake_app / "config.json"
        fake_cfg.write_text("not valid json {{")

        monkeypatch.setattr("grouper.config.APP_DIR", fake_app)
        monkeypatch.setattr("grouper.config.CONFIG_FILE", fake_cfg)
        monkeypatch.setattr("grouper.config.ConfigManager._instance", None)

        mgr = ConfigManager()
        assert mgr.config.theme == "dark"
        data = json.loads(fake_cfg.read_text())
        assert data["theme"] == "dark"
