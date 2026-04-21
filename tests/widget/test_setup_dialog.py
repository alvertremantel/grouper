"""Tests for the SetupDialog start-screen flow in grouper_install/setup.py."""

from __future__ import annotations

import json
from collections.abc import Generator
from pathlib import Path

import pytest
from grouper_install.setup import (
    _PAGE_COMPLETE,
    _PAGE_INSTALL,
    _PAGE_START,
    _PAGE_UNINSTALL_COMPLETE,
    _PAGE_UNINSTALL_CONFIRM,
    SetupDialog,
)
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
)


@pytest.fixture
def dialog(qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> Generator[SetupDialog, None, None]:
    monkeypatch.setattr("grouper_install.setup.read_manifest", lambda: None)
    d = SetupDialog()
    yield d
    d.close()


def _click(button: QPushButton) -> None:
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)


class TestStartScreen:
    def test_opens_on_start_page(self, dialog: SetupDialog) -> None:
        assert dialog._stack.currentIndex() == _PAGE_START

    def test_has_install_button(self, dialog: SetupDialog) -> None:
        assert isinstance(dialog._btn_install, QPushButton)
        assert dialog._btn_install.text() == "Install Grouper"

    def test_has_uninstall_button(self, dialog: SetupDialog) -> None:
        assert isinstance(dialog._btn_uninstall, QPushButton)
        assert dialog._btn_uninstall.text() == "Uninstall Grouper"

    def test_install_button_navigates_to_install_page(self, dialog: SetupDialog) -> None:
        dialog._show_install_page()
        assert dialog._stack.currentIndex() == _PAGE_INSTALL

    def test_back_button_returns_to_start_page(self, dialog: SetupDialog) -> None:
        dialog._show_install_page()
        assert dialog._stack.currentIndex() == _PAGE_INSTALL
        button_box = dialog._install_page.findChild(QDialogButtonBox)
        assert button_box is not None
        back = button_box.button(QDialogButtonBox.StandardButton.RestoreDefaults)
        assert back is not None
        assert back.text() == "Back"
        _click(back)
        assert dialog._stack.currentIndex() == _PAGE_START

    def test_shows_variant_name(self, tmp_path: Path, qapp: QApplication) -> None:
        (tmp_path / "dist.toml").write_text('variant = "core_cli"\n')
        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "grouper.exe").touch()
        (tmp_path / "cli").mkdir()
        (tmp_path / "cli" / "grouper-cli.exe").touch()

        with (
            pytest.MonkeyPatch().context() as mp,
        ):
            mp.setattr("grouper_install.setup._source_root", lambda: tmp_path)
            mp.setattr("grouper_install.setup.is_elevated", lambda: False)
            mp.setattr("grouper_install.setup.read_manifest", lambda: None)
            d = SetupDialog()
            try:
                page = d._start_page
                found = False
                for child in page.findChildren(QLabel):
                    if "core_cli" in child.text():
                        found = True
                        break
                assert found, "Variant name 'core_cli' not found on start page"
            finally:
                d.close()


class TestUninstallPlaceholder:
    def test_uninstall_disabled_when_no_manifest(
        self, dialog: SetupDialog
    ) -> None:
        assert dialog._btn_uninstall.isEnabled() is False

    def test_uninstall_enabled_when_manifest_exists(
        self, tmp_path: Path, qapp: QApplication
    ) -> None:
        manifest_data = {
            "manifest_version": "1",
            "version": "1.0.0",
            "variant": "core",
            "install_time": "2026-04-20T12:00:00Z",
            "destinations": {"app": "C:/Program Files/Grouper Apps/Grouper"},
            "path_entries": [],
            "shortcuts": [],
            "installer_path": "",
        }
        manifest_dir = tmp_path / "Grouper"
        manifest_dir.mkdir()
        (manifest_dir / "install-manifest.json").write_text(
            json.dumps(manifest_data), encoding="utf-8"
        )
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr("grouper_install.setup.read_manifest", lambda: type(
                "M", (), {
                    "version": "1.0.0",
                    "variant": "core",
                    "install_time": "2026-04-20T12:00:00Z",
                    "destinations": {"app": "C:/Program Files/Grouper Apps/Grouper"},
                    "path_entries": [],
                    "shortcuts": [],
                    "installer_path": "",
                    "manifest_version": "1",
                }
            )())
            d = SetupDialog()
            try:
                assert d._btn_uninstall.isEnabled() is True
            finally:
                d.close()

    def test_uninstall_shows_warning_when_no_manifest(
        self, dialog: SetupDialog, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        shown: list[str] = []

        def _spy(*args, **kwargs) -> None:
            shown.append(kwargs.get("title", args[1] if len(args) > 1 else ""))

        monkeypatch.setattr(QMessageBox, "warning", _spy)
        dialog._begin_uninstall_flow()
        assert any("No Installation Found" in s for s in shown)


class TestUninstallConfirmPage:
    def test_navigates_to_confirm_page(
        self, tmp_path: Path, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_manifest = type(
            "M", (), {
                "version": "1.0.0",
                "variant": "core",
                "install_time": "2026-04-20T12:00:00Z",
                "destinations": {"app": "C:/Program Files/Grouper Apps/Grouper"},
                "path_entries": ["C:/Program Files/Grouper Apps/Grouper CLI"],
                "shortcuts": ["C:/Users/test/Desktop/Grouper.lnk"],
                "installer_path": "",
                "manifest_version": "1",
            }
        )()
        monkeypatch.setattr("grouper_install.setup.is_elevated", lambda: True)
        monkeypatch.setattr("grouper_install.setup.read_manifest", lambda: fake_manifest)
        d = SetupDialog()
        try:
            _click(d._btn_uninstall)
            assert d._stack.currentIndex() == _PAGE_UNINSTALL_CONFIRM
        finally:
            d.close()

    def test_confirm_page_shows_components(
        self, tmp_path: Path, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_manifest = type(
            "M", (), {
                "version": "1.0.0",
                "variant": "core",
                "install_time": "2026-04-20T12:00:00Z",
                "destinations": {"app": "C:/Program Files/Grouper Apps/Grouper"},
                "path_entries": [],
                "shortcuts": ["C:/Users/test/Desktop/Grouper.lnk"],
                "installer_path": "",
                "manifest_version": "1",
            }
        )()
        monkeypatch.setattr("grouper_install.setup.is_elevated", lambda: True)
        monkeypatch.setattr("grouper_install.setup.read_manifest", lambda: fake_manifest)
        d = SetupDialog()
        try:
            _click(d._btn_uninstall)
            summary_text = d._uninstall_summary.text()
            assert "core" in summary_text
            assert "Grouper" in summary_text
        finally:
            d.close()


class TestUninstallExecution:
    def test_run_uninstall_navigates_to_complete(
        self, tmp_path: Path, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_manifest = type(
            "M", (), {
                "version": "1.0.0",
                "variant": "core",
                "install_time": "2026-04-20T12:00:00Z",
                "destinations": {"app": str(tmp_path / "Grouper")},
                "path_entries": [],
                "shortcuts": [],
                "installer_path": "",
                "manifest_version": "1",
            }
        )()
        monkeypatch.setattr("grouper_install.setup.is_elevated", lambda: True)
        monkeypatch.setattr("grouper_install.setup.read_manifest", lambda: fake_manifest)
        monkeypatch.setattr("grouper_install.setup.unregister_uninstall", lambda: None)
        monkeypatch.setattr("grouper_install.setup.remove_manifest", lambda: None)
        monkeypatch.setattr("grouper_install.setup.remove_from_machine_path", lambda d: True)
        d = SetupDialog()
        try:
            d._run_uninstall()
            assert d._stack.currentIndex() == _PAGE_UNINSTALL_COMPLETE
            result_text = d._uninstall_result_label.text()
            assert "Removed" in result_text
            assert "personal data" in result_text
        finally:
            d.close()

    def test_uninstall_handles_partial_failure(
        self, tmp_path: Path, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_manifest = type(
            "M", (), {
                "version": "1.0.0",
                "variant": "core",
                "install_time": "2026-04-20T12:00:00Z",
                "destinations": {"app": str(tmp_path / "nonexistent")},
                "path_entries": ["C:/missing/path"],
                "shortcuts": ["C:/missing/shortcut.lnk"],
                "installer_path": "",
                "manifest_version": "1",
            }
        )()
        monkeypatch.setattr("grouper_install.setup.is_elevated", lambda: True)
        monkeypatch.setattr("grouper_install.setup.read_manifest", lambda: fake_manifest)
        monkeypatch.setattr("grouper_install.setup.unregister_uninstall", lambda: None)
        monkeypatch.setattr("grouper_install.setup.remove_manifest", lambda: None)
        monkeypatch.setattr("grouper_install.setup.remove_from_machine_path", lambda d: False)
        d = SetupDialog()
        try:
            d._run_uninstall()
            assert d._stack.currentIndex() == _PAGE_UNINSTALL_COMPLETE
        finally:
            d.close()

    def test_uninstall_removes_installer_dir(
        self, tmp_path: Path, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        installer_dir = tmp_path / "Installer"
        installer_dir.mkdir()
        (installer_dir / "setup.exe").write_bytes(b"fake")
        fake_manifest = type(
            "M", (), {
                "version": "1.0.0",
                "variant": "core",
                "install_time": "2026-04-20T12:00:00Z",
                "destinations": {"app": str(tmp_path / "Grouper")},
                "path_entries": [],
                "shortcuts": [],
                "installer_path": str(installer_dir / "setup.exe"),
                "manifest_version": "1",
            }
        )()
        monkeypatch.setattr("grouper_install.setup.is_elevated", lambda: True)
        monkeypatch.setattr("grouper_install.setup.read_manifest", lambda: fake_manifest)
        monkeypatch.setattr("grouper_install.setup.unregister_uninstall", lambda: None)
        monkeypatch.setattr("grouper_install.setup.remove_manifest", lambda: None)
        d = SetupDialog()
        try:
            d._run_uninstall()
            assert d._stack.currentIndex() == _PAGE_UNINSTALL_COMPLETE
            assert not installer_dir.exists()
            result_text = d._uninstall_result_label.text()
            assert "Removed installer copy" in result_text
        finally:
            d.close()


class TestInstallPageContent:
    def test_install_page_has_shortcut_options(self, dialog: SetupDialog) -> None:
        dialog._show_install_page()
        assert dialog._stack.currentIndex() == _PAGE_INSTALL
        assert dialog._chk_desktop.isChecked()
        assert dialog._chk_start.isChecked()


class TestInstallPageDestinations:
    def test_shows_app_destination_always(self, dialog: SetupDialog) -> None:
        dialog._show_install_page()
        assert isinstance(dialog._le_dest_app, QLineEdit)

    def test_shows_cli_destination_for_cli_variant(self, tmp_path: Path, qapp: QApplication) -> None:
        (tmp_path / "dist.toml").write_text('variant = "core_cli"\n')
        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "grouper.exe").touch()
        (tmp_path / "cli").mkdir()
        (tmp_path / "cli" / "grouper-cli.exe").touch()

        with pytest.MonkeyPatch().context() as mp:
            mp.setattr("grouper_install.setup._source_root", lambda: tmp_path)
            mp.setattr("grouper_install.setup.is_elevated", lambda: False)
            mp.setattr("grouper_install.setup.read_manifest", lambda: None)
            d = SetupDialog()
            try:
                d._show_install_page()
                assert d._le_dest_cli is not None
            finally:
                d.close()

    def test_hides_cli_destination_for_core_variant(self, tmp_path: Path, qapp: QApplication) -> None:
        (tmp_path / "dist.toml").write_text('variant = "core"\n')
        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "grouper.exe").touch()

        with pytest.MonkeyPatch().context() as mp:
            mp.setattr("grouper_install.setup._source_root", lambda: tmp_path)
            mp.setattr("grouper_install.setup.is_elevated", lambda: False)
            mp.setattr("grouper_install.setup.read_manifest", lambda: None)
            d = SetupDialog()
            try:
                d._show_install_page()
                assert d._le_dest_cli is None
            finally:
                d.close()

    def test_shows_path_checkboxes_for_cli(self, tmp_path: Path, qapp: QApplication) -> None:
        (tmp_path / "dist.toml").write_text('variant = "core_cli"\n')
        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "grouper.exe").touch()
        (tmp_path / "cli").mkdir()
        (tmp_path / "cli" / "grouper-cli.exe").touch()

        with pytest.MonkeyPatch().context() as mp:
            mp.setattr("grouper_install.setup._source_root", lambda: tmp_path)
            mp.setattr("grouper_install.setup.is_elevated", lambda: False)
            mp.setattr("grouper_install.setup.read_manifest", lambda: None)
            d = SetupDialog()
            try:
                d._show_install_page()
                assert d._chk_path_cli is not None
                assert isinstance(d._chk_path_cli, QCheckBox)
            finally:
                d.close()

    def test_hides_path_section_for_core(self, tmp_path: Path, qapp: QApplication) -> None:
        (tmp_path / "dist.toml").write_text('variant = "core"\n')
        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "grouper.exe").touch()

        with pytest.MonkeyPatch().context() as mp:
            mp.setattr("grouper_install.setup._source_root", lambda: tmp_path)
            mp.setattr("grouper_install.setup.is_elevated", lambda: False)
            mp.setattr("grouper_install.setup.read_manifest", lambda: None)
            d = SetupDialog()
            try:
                d._show_install_page()
                assert not hasattr(d, "_chk_path_cli") or d._chk_path_cli is None
            finally:
                d.close()


class TestCompletePage:
    def test_navigates_to_complete_on_success(self, tmp_path: Path, qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
        (tmp_path / "dist.toml").write_text('variant = "core"\n')
        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "grouper.exe").touch()
        (tmp_path / "version.txt").write_text("1.0.0")

        with pytest.MonkeyPatch().context() as mp:
            mp.setattr("grouper_install.setup._source_root", lambda: tmp_path)
            mp.setattr("grouper_install.setup.is_elevated", lambda: True)
            mp.setattr("grouper_install.setup.read_manifest", lambda: None)
            mp.setattr("grouper_install.setup._copy_tree", lambda src, dst: None)
            mp.setattr("grouper_install.setup._create_desktop_shortcut_dest", lambda app_dir: None)
            mp.setattr("grouper_install.setup._create_start_menu_shortcut_dest", lambda app_dir: None)
            mp.setattr("grouper_install.setup.add_to_machine_path", lambda d: False)
            mp.setattr("grouper_install.setup.write_manifest", lambda m: None)
            mp.setattr("grouper_install.setup.register_uninstall", lambda m: None)
            mp.setattr("grouper_install.setup._copy_installer_to_stable_location", lambda: None)
            mp.setattr("grouper_install.setup._desktop", lambda: tmp_path)
            mp.setattr("grouper_install.setup._start_menu_programs", lambda: tmp_path)

            d = SetupDialog()
            try:
                d._show_install_page()
                d._le_dest_app.setText(str(tmp_path / "install"))
                d._run_install()
                assert d._stack.currentIndex() == _PAGE_COMPLETE
            finally:
                d.close()
