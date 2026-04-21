"""Tests for grouper_install/elevation.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from grouper_install.elevation import is_elevated, relaunch_elevated


class TestIsElevated:
    def test_returns_bool(self) -> None:
        result = is_elevated()
        assert isinstance(result, bool)

    def test_calls_windows_api_returns_true(self) -> None:
        mock_shell32 = MagicMock()
        mock_shell32.IsUserAnAdmin.return_value = 1
        with patch("grouper_install.elevation.ctypes.windll.shell32", mock_shell32):
            assert is_elevated() is True

    def test_calls_windows_api_returns_false(self) -> None:
        mock_shell32 = MagicMock()
        mock_shell32.IsUserAnAdmin.return_value = 0
        with patch("grouper_install.elevation.ctypes.windll.shell32", mock_shell32):
            assert is_elevated() is False

    def test_returns_false_on_attribute_error(self) -> None:
        mock_windll = MagicMock()
        del mock_windll.shell32
        with patch("grouper_install.elevation.ctypes.windll", mock_windll):
            assert is_elevated() is False


class TestRelaunchElevated:
    def test_exits_on_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_shell32 = MagicMock()
        mock_shell32.ShellExecuteW.return_value = 42
        exited = []

        def fake_exit(code: int) -> None:
            exited.append(code)
            raise SystemExit(code)

        with (
            patch("grouper_install.elevation.ctypes.windll.shell32", mock_shell32),
            patch("grouper_install.elevation.sys.argv", ["test.exe", "--flag"]),
            patch("grouper_install.elevation.sys.exit", fake_exit),
            pytest.raises(SystemExit),
        ):
            relaunch_elevated()

        assert exited == [0]
        mock_shell32.ShellExecuteW.assert_called_once()

    def test_raises_on_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_shell32 = MagicMock()
        mock_shell32.ShellExecuteW.return_value = 0

        with (
            patch("grouper_install.elevation.ctypes.windll.shell32", mock_shell32),
            patch("grouper_install.elevation.sys.argv", ["test.exe"]),
            pytest.raises(OSError, match="Failed to relaunch elevated"),
        ):
            relaunch_elevated()
