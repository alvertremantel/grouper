"""Tests for installer/registry.py."""

from __future__ import annotations

import winreg
from unittest.mock import MagicMock, patch

from installer.manifest import InstallManifest
from installer.registry import register_uninstall, unregister_uninstall


def _sample_manifest() -> InstallManifest:
    return InstallManifest(
        version="1.0.0",
        variant="core_cli",
        install_time="2026-04-20T12:00:00Z",
        destinations={"app": "C:/Program Files/Grouper Apps/Grouper"},
        path_entries=["C:/Program Files/Grouper Apps/Grouper CLI"],
        shortcuts=["C:/Users/test/Desktop/Grouper.lnk"],
        installer_path="C:/Program Files/Grouper Apps/Installer/setup.exe",
    )


class TestRegisterUninstall:
    def test_writes_expected_keys(self) -> None:
        mock_key = MagicMock()
        manifest = _sample_manifest()

        with (
            patch("installer.registry.winreg.CreateKeyEx", return_value=mock_key),
            patch("installer.registry.winreg.SetValueEx") as mock_set,
            patch("installer.registry.winreg.CloseKey"),
            patch("installer.registry.Path.exists", return_value=False),
        ):
            register_uninstall(manifest)

        set_calls = mock_set.call_args_list
        values = {c.args[1]: c.args[4] for c in set_calls}
        assert values["DisplayName"] == "Grouper"
        assert values["DisplayVersion"] == "1.0.0"
        assert values["Publisher"] == "Grouper"
        assert values["InstallLocation"] == "C:/Program Files/Grouper Apps/Grouper"

    def test_uninstall_string_uses_installer_path(self) -> None:
        mock_key = MagicMock()
        manifest = _sample_manifest()

        with (
            patch("installer.registry.winreg.CreateKeyEx", return_value=mock_key),
            patch("installer.registry.winreg.SetValueEx") as mock_set,
            patch("installer.registry.winreg.CloseKey"),
            patch("installer.registry.Path.exists", return_value=False),
        ):
            register_uninstall(manifest)

        set_calls = mock_set.call_args_list
        values = {c.args[1]: c.args[4] for c in set_calls}
        assert values["UninstallString"] == '"C:/Program Files/Grouper Apps/Installer/setup.exe" --uninstall'

    def test_uninstall_string_falls_back_to_app_dir(self) -> None:
        mock_key = MagicMock()
        manifest = InstallManifest(
            version="1.0.0",
            variant="core",
            install_time="2026-04-20T12:00:00Z",
            destinations={"app": "C:/Program Files/Grouper Apps/Grouper"},
            path_entries=[],
            shortcuts=[],
            installer_path="",
        )

        with (
            patch("installer.registry.winreg.CreateKeyEx", return_value=mock_key),
            patch("installer.registry.winreg.SetValueEx") as mock_set,
            patch("installer.registry.winreg.CloseKey"),
            patch("installer.registry.Path.exists", return_value=False),
        ):
            register_uninstall(manifest)

        set_calls = mock_set.call_args_list
        values = {c.args[1]: c.args[4] for c in set_calls}
        assert values["UninstallString"] == '"C:\\Program Files\\Grouper Apps\\Grouper\\setup.exe" --uninstall'

    def test_sets_no_modify_and_no_repair(self) -> None:
        mock_key = MagicMock()
        manifest = _sample_manifest()

        with (
            patch("installer.registry.winreg.CreateKeyEx", return_value=mock_key),
            patch("installer.registry.winreg.SetValueEx") as mock_set,
            patch("installer.registry.winreg.CloseKey"),
            patch("installer.registry.Path.exists", return_value=False),
        ):
            register_uninstall(manifest)

        set_calls = mock_set.call_args_list
        values = {c.args[1]: c.args[4] for c in set_calls}
        assert values["NoModify"] == 1
        assert values["NoRepair"] == 1


class TestUnregisterUninstall:
    def test_deletes_key(self) -> None:
        with patch("installer.registry.winreg.DeleteKey") as mock_delete:
            unregister_uninstall()
            mock_delete.assert_called_once_with(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Grouper",
            )
