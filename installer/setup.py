"""
Grouper Setup
=============
Portable-app post-unzip installer.

Run this after unzipping the Grouper release archive to the directory you
want to install into.  It will:
  1. Create a Desktop shortcut to grouper.exe
  2. Create a Start Menu entry

Compiled to setup.exe via Nuitka:
    nuitka --onefile --windows-console-mode=disable \
           --enable-plugin=pyside6 --include-package=win32com \
           --windows-icon-from-ico=../grouper/assets/icon.ico \
            installer/setup.py
"""

from __future__ import annotations

import ctypes
import os
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from installer.dist_meta import (
    load_dist_toml,
)
from installer.elevation import is_elevated, relaunch_elevated
from installer.manifest import (
    InstallManifest,
    read_manifest,
    remove_manifest,
    write_manifest,
)
from installer.path_env import add_to_machine_path, remove_from_machine_path
from installer.registry import register_uninstall, unregister_uninstall

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def _source_root() -> Path:
    """Detect the release directory that contains app/ and setup.exe.

    Nuitka onefile builds extract to a temp directory, so sys.executable
    and __file__ may not point to the real binary location.  We try
    multiple candidates and return the first one where app/grouper.exe
    actually exists.
    """
    candidates: list[Path] = []
    if getattr(sys, "frozen", False) or "__compiled__" in dir():
        candidates.append(Path(sys.argv[0]).resolve().parent)
        candidates.append(Path(sys.executable).resolve().parent)
    candidates.append(Path.cwd())
    candidates.append(Path(__file__).resolve().parent.parent)
    for c in candidates:
        if (c / "app" / "grouper.exe").exists():
            return c
    return candidates[0]


def _desktop() -> Path:
    try:
        from win32com.client import Dispatch

        shell = Dispatch("WScript.Shell")
        return Path(shell.SpecialFolders("Desktop"))
    except Exception:
        return Path.home() / "Desktop"


def _start_menu_programs() -> Path:
    try:
        from win32com.client import Dispatch

        shell = Dispatch("WScript.Shell")
        return Path(shell.SpecialFolders("Programs"))
    except Exception:
        return (
            Path(os.environ.get("APPDATA", ""))
            / "Microsoft"
            / "Windows"
            / "Start Menu"
            / "Programs"
        )


# ---------------------------------------------------------------------------
# Shortcut helpers
# ---------------------------------------------------------------------------


def _create_shortcut(lnk_path: Path, target: Path, work_dir: Path) -> None:
    from win32com.client import Dispatch

    shell = Dispatch("WScript.Shell")
    sc = shell.CreateShortcut(str(lnk_path))
    sc.TargetPath = str(target)
    sc.WorkingDirectory = str(work_dir)
    sc.IconLocation = str(target)
    sc.Save()


def _create_desktop_shortcut(install_dir: Path) -> None:
    app_dir = install_dir / "app"
    _create_desktop_shortcut_dest(app_dir)


def _create_start_menu_shortcut(install_dir: Path) -> None:
    app_dir = install_dir / "app"
    _create_start_menu_shortcut_dest(app_dir)


# ---------------------------------------------------------------------------
# File copy helpers
# ---------------------------------------------------------------------------


def _copy_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, copy_function=shutil.copy2)


def _install_component(src_dir: Path, dst_dir: Path, label: str) -> str | None:
    try:
        _copy_tree(src_dir, dst_dir)
    except OSError as exc:
        return f"{label}: {exc}"
    return None


# ---------------------------------------------------------------------------
# Shortcut helpers with explicit destination
# ---------------------------------------------------------------------------


def _create_desktop_shortcut_dest(app_dir: Path) -> None:
    lnk = _desktop() / "Grouper.lnk"
    _create_shortcut(lnk, app_dir / "grouper.exe", app_dir)


def _create_start_menu_shortcut_dest(app_dir: Path) -> None:
    folder = _start_menu_programs() / "Grouper"
    folder.mkdir(parents=True, exist_ok=True)
    lnk = folder / "Grouper.lnk"
    _create_shortcut(lnk, app_dir / "grouper.exe", app_dir)


def _read_version(source_root: Path) -> str:
    v = source_root / "version.txt"
    if v.exists():
        return v.read_text(encoding="utf-8").strip()
    return "unknown"


# ---------------------------------------------------------------------------
# Setup dialog
# ---------------------------------------------------------------------------

_PAGE_START = 0
_PAGE_INSTALL = 1
_PAGE_COMPLETE = 2
_PAGE_UNINSTALL_CONFIRM = 3
_PAGE_UNINSTALL_COMPLETE = 4

_INSTALLER_DIR_NAME = "Installer"


def _stable_installer_path() -> Path:
    pf = os.environ.get("PROGRAMFILES", r"C:\Program Files")
    return Path(pf) / "Grouper Apps" / _INSTALLER_DIR_NAME / "setup.exe"


def _copy_installer_to_stable_location() -> str | None:
    installer_dest = _stable_installer_path()
    try:
        installer_dest.parent.mkdir(parents=True, exist_ok=True)
        exe_src = Path(sys.argv[0]).resolve()
        if not exe_src.exists():
            exe_src = Path(sys.executable).resolve()
        shutil.copy2(exe_src, installer_dest)
    except OSError as exc:
        return str(exc)
    return None


def _remove_shortcut_safe(path_str: str) -> str | None:
    p = Path(path_str)
    try:
        if p.exists():
            p.unlink()
        parent = p.parent
        if parent.name == "Grouper" and parent.exists() and not any(parent.iterdir()):
            parent.rmdir()
    except OSError as exc:
        return f"Shortcut {path_str}: {exc}"
    return None


def _remove_dir_safe(path_str: str) -> str | None:
    p = Path(path_str)
    try:
        if p.exists():
            shutil.rmtree(p)
    except OSError as exc:
        return f"Directory {path_str}: {exc}"
    return None


def _remove_empty_parent(path_str: str) -> None:
    p = Path(path_str)
    for _ in range(3):
        p = p.parent
        if not p.exists():
            break
        try:
            if not any(p.iterdir()):
                p.rmdir()
            else:
                break
        except OSError:
            break


class SetupDialog(QDialog):
    def __init__(self, *, uninstall_mode: bool = False) -> None:
        super().__init__()
        self.setMinimumWidth(480)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self._uninstall_mode = uninstall_mode
        self._source_root = _source_root()
        try:
            self._variant_info = load_dist_toml(self._source_root)
        except (FileNotFoundError, ValueError) as exc:
            self._variant_info = None
            self._metadata_error = str(exc)
        if self._variant_info:
            self.setWindowTitle(f"Grouper Setup — {self._variant_info.variant}")
        else:
            self.setWindowTitle("Grouper Setup")
        pf = os.environ.get("PROGRAMFILES", r"C:\Program Files")
        self._dest_app: Path = Path(pf) / "Grouper Apps" / "Grouper"
        self._dest_cli: Path | None = None
        self._dest_server: Path | None = None
        if self._variant_info and self._variant_info.has_cli:
            self._dest_cli = Path(pf) / "Grouper Apps" / "Grouper CLI"
        if self._variant_info and self._variant_info.has_server:
            self._dest_server = Path(pf) / "Grouper Apps" / "Grouper Server"
        self._elevated = is_elevated()
        self._existing_manifest = read_manifest()
        self._stack = QStackedWidget(self)
        self._build_start_page()
        self._build_install_page()
        self._build_complete_page()
        self._build_uninstall_confirm_page()
        self._build_uninstall_complete_page()
        self._build_ui()
        if uninstall_mode:
            self._begin_uninstall_flow()

    # ---- page builders ---------------------------------------------------

    def _build_start_page(self) -> None:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("Grouper Setup")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        if self._variant_info is None:
            err_label = QLabel(f"Error: {self._metadata_error}")
            err_label.setStyleSheet("color: #c00; font-size: 12px;")
            err_label.setWordWrap(True)
            layout.addWidget(err_label)
            self._btn_install = QPushButton("Install Grouper")
            self._btn_install.setMinimumHeight(40)
            self._btn_install.setEnabled(False)
            self._btn_install.clicked.connect(self._show_install_page)
            layout.addWidget(self._btn_install)
        else:
            components = []
            if self._variant_info.has_app:
                components.append("Grouper desktop app")
            if self._variant_info.has_cli:
                components.append("CLI tools")
            if self._variant_info.has_server:
                components.append("Sync server")
            component_text = ", ".join(components)
            variant_label = QLabel(f"Package:  {self._variant_info.variant}  ({component_text})")
            variant_label.setStyleSheet("color: #444; font-size: 12px;")
            variant_label.setWordWrap(True)
            layout.addWidget(variant_label)

            source_label = QLabel(f"Source:  {self._source_root}")
            source_label.setStyleSheet("color: #666; font-size: 11px;")
            source_label.setWordWrap(True)
            layout.addWidget(source_label)

            elev_label = QLabel(
                "Running as administrator"
                if self._elevated
                else "Not running as administrator — will prompt for elevation on install"
            )
            elev_label.setStyleSheet(
                "color: #2a7d2a; font-size: 11px;"
                if self._elevated
                else "color: #b85c00; font-size: 11px;"
            )
            elev_label.setWordWrap(True)
            layout.addWidget(elev_label)

            if self._existing_manifest is not None:
                existing_label = QLabel(
                    f"Existing install found: v{self._existing_manifest.version} ({self._existing_manifest.variant})\n"
                    f"Re-installing will overwrite the previous installation."
                )
                existing_label.setStyleSheet("color: #2a7ae2; font-size: 11px;")
                existing_label.setWordWrap(True)
                layout.addWidget(existing_label)

            layout.addSpacing(16)

            self._btn_install = QPushButton("Install Grouper")
            self._btn_install.setMinimumHeight(40)
            self._btn_install.clicked.connect(self._show_install_page)
            layout.addWidget(self._btn_install)

        self._btn_uninstall = QPushButton("Uninstall Grouper")
        self._btn_uninstall.setMinimumHeight(40)
        self._btn_uninstall.clicked.connect(self._begin_uninstall_flow)
        self._btn_uninstall.setEnabled(self._existing_manifest is not None)
        self._btn_uninstall.setToolTip(
            "No existing installation found"
            if self._existing_manifest is None
            else ""
        )
        layout.addWidget(self._btn_uninstall)

        layout.addStretch()
        self._start_page = page

    def _build_install_page(self) -> None:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        dest_box = QGroupBox("Install Destinations")
        dest_layout = QVBoxLayout(dest_box)

        if not self._elevated:
            note = QLabel("Installing to Program Files requires administrator elevation.")
            note.setStyleSheet("color: #b85c00; font-size: 11px;")
            dest_layout.addWidget(note)

        self._le_dest_app = self._make_dest_row(dest_box, "Grouper:", str(self._dest_app))
        dest_layout.addWidget(self._le_dest_app.parentWidget() or self._le_dest_app)

        self._le_dest_cli: QLineEdit | None = None
        if self._variant_info and self._variant_info.has_cli:
            self._le_dest_cli = self._make_dest_row(dest_box, "Grouper CLI:", str(self._dest_cli))
            dest_layout.addWidget(self._le_dest_cli.parentWidget() or self._le_dest_cli)

        self._le_dest_server: QLineEdit | None = None
        if self._variant_info and self._variant_info.has_server:
            self._le_dest_server = self._make_dest_row(dest_box, "Grouper Server:", str(self._dest_server))
            dest_layout.addWidget(self._le_dest_server.parentWidget() or self._le_dest_server)

        layout.addWidget(dest_box)

        shortcuts_box = QGroupBox("Shortcuts")
        shortcuts_layout = QVBoxLayout(shortcuts_box)
        self._chk_desktop = QCheckBox("Create Desktop shortcut")
        self._chk_desktop.setChecked(True)
        self._chk_start = QCheckBox("Add to Start Menu")
        self._chk_start.setChecked(True)
        shortcuts_layout.addWidget(self._chk_desktop)
        shortcuts_layout.addWidget(self._chk_start)
        layout.addWidget(shortcuts_box)

        if self._variant_info and (
            self._variant_info.has_cli or self._variant_info.has_server
        ):
            path_box = QGroupBox("System PATH")
            path_layout = QVBoxLayout(path_box)
            self._chk_path_cli: QCheckBox | None = None
            if self._variant_info.has_cli:
                self._chk_path_cli = QCheckBox("Add Grouper CLI to system PATH")
                self._chk_path_cli.setChecked(True)
                path_layout.addWidget(self._chk_path_cli)
            self._chk_path_server: QCheckBox | None = None
            if self._variant_info.has_server:
                self._chk_path_server = QCheckBox("Add Grouper Server to system PATH")
                self._chk_path_server.setChecked(True)
                path_layout.addWidget(self._chk_path_server)
            path_note = QLabel(
                "Adds directories to the system Path. Already-open terminals must be reopened."
            )
            path_note.setStyleSheet("color: #666; font-size: 11px;")
            path_note.setWordWrap(True)
            path_layout.addWidget(path_note)
            layout.addWidget(path_box)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.RestoreDefaults
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Install")
        buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).setText("Back")
        buttons.accepted.connect(self._run_install)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(
            self._show_start_page
        )
        layout.addWidget(buttons)

        self._install_page = page

    def _build_complete_page(self) -> None:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("Installation Complete")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        self._summary_label = QLabel("")
        self._summary_label.setWordWrap(True)
        self._summary_label.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._summary_label)

        layout.addStretch()

        btn_close = QPushButton("Close")
        btn_close.setMinimumHeight(36)
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

        self._complete_page = page

    def _build_uninstall_confirm_page(self) -> None:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("Uninstall Grouper")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        self._uninstall_summary = QLabel("")
        self._uninstall_summary.setWordWrap(True)
        self._uninstall_summary.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._uninstall_summary)

        data_note = QLabel(
            "Your personal data and settings will NOT be removed.\n"
            "They remain in your user profile and can be deleted manually."
        )
        data_note.setStyleSheet("color: #2a7d2a; font-size: 11px;")
        data_note.setWordWrap(True)
        layout.addWidget(data_note)

        layout.addStretch()

        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.No
        )
        btn_box.button(QDialogButtonBox.StandardButton.Yes).setText("Uninstall")
        btn_box.button(QDialogButtonBox.StandardButton.No).setText("Cancel")
        btn_box.accepted.connect(self._run_uninstall)
        btn_box.rejected.connect(self._show_start_page)
        layout.addWidget(btn_box)

        self._uninstall_confirm_page = page

    def _build_uninstall_complete_page(self) -> None:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("Uninstall Complete")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        self._uninstall_result_label = QLabel("")
        self._uninstall_result_label.setWordWrap(True)
        self._uninstall_result_label.setStyleSheet("font-size: 12px;")
        layout.addWidget(self._uninstall_result_label)

        layout.addStretch()

        btn_close = QPushButton("Close")
        btn_close.setMinimumHeight(36)
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

        self._uninstall_complete_page = page

    def _make_dest_row(self, parent: QWidget, label_text: str, initial_path: str) -> QLineEdit:
        row = QWidget(parent)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)

        label = QLabel(label_text)
        label.setMinimumWidth(100)
        row_layout.addWidget(label)

        le = QLineEdit(initial_path)
        row_layout.addWidget(le)

        btn = QPushButton("Browse...")
        btn.setFixedWidth(80)
        btn.clicked.connect(lambda: self._browse_dest(le))
        row_layout.addWidget(btn)

        return le

    def _browse_dest(self, le: QLineEdit) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select Install Directory", le.text())
        if path:
            le.setText(path)

    # ---- top-level layout ------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self._stack.addWidget(self._start_page)
        self._stack.addWidget(self._install_page)
        self._stack.addWidget(self._complete_page)
        self._stack.addWidget(self._uninstall_confirm_page)
        self._stack.addWidget(self._uninstall_complete_page)
        root.addWidget(self._stack)

    # ---- navigation ------------------------------------------------------

    def _show_start_page(self) -> None:
        self._stack.setCurrentIndex(_PAGE_START)

    def _show_install_page(self) -> None:
        self._stack.setCurrentIndex(_PAGE_INSTALL)

    def _begin_uninstall_flow(self) -> None:
        if self._existing_manifest is None:
            QMessageBox.warning(
                self,
                "No Installation Found",
                "No Grouper installation was found on this system.",
            )
            return

        if not self._elevated:
            reply = QMessageBox.question(
                self,
                "Elevation Required",
                "Uninstalling Grouper requires administrator privileges.\n\n"
                "Relaunch setup.exe as administrator?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                try:
                    relaunch_elevated(["--uninstall"])
                except OSError as exc:
                    QMessageBox.critical(self, "Elevation Failed", str(exc))
            return

        self._populate_uninstall_summary()
        self._stack.setCurrentIndex(_PAGE_UNINSTALL_CONFIRM)

    def _populate_uninstall_summary(self) -> None:
        m = self._existing_manifest
        assert m is not None
        lines = [
            f"Version: {m.version}  ({m.variant})",
            "",
            "Components to remove:",
        ]
        for label, dest in m.destinations.items():
            exists = Path(dest).exists()
            marker = "" if exists else "  (already removed)"
            lines.append(f"  \u2022 {label}: {dest}{marker}")
        if m.path_entries:
            lines.append("")
            lines.append("PATH entries to remove:")
            for entry in m.path_entries:
                lines.append(f"  \u2022 {entry}")
        if m.shortcuts:
            lines.append("")
            lines.append("Shortcuts to remove:")
            for sc in m.shortcuts:
                exists = Path(sc).exists()
                marker = "" if exists else "  (already removed)"
                lines.append(f"  \u2022 {sc}{marker}")
        self._uninstall_summary.setText("\n".join(lines))

    def _run_uninstall(self) -> None:
        m = self._existing_manifest
        if m is None:
            self._stack.setCurrentIndex(_PAGE_START)
            return

        successes: list[str] = []
        errors: list[str] = []

        for sc in m.shortcuts:
            err = _remove_shortcut_safe(sc)
            if err:
                errors.append(err)
            else:
                successes.append(f"Removed shortcut: {sc}")

        for entry in m.path_entries:
            try:
                removed = remove_from_machine_path(entry)
            except PermissionError:
                errors.append(f"PATH {entry}: permission denied")
            except Exception as exc:
                errors.append(f"PATH {entry}: {exc}")
            else:
                if removed:
                    successes.append(f"Removed from PATH: {entry}")
                else:
                    successes.append(f"PATH entry already absent: {entry}")

        for label, dest in m.destinations.items():
            err = _remove_dir_safe(dest)
            if err:
                errors.append(err)
            else:
                successes.append(f"Removed {label}: {dest}")
                _remove_empty_parent(dest)

        if m.installer_path:
            installer_dir = Path(m.installer_path).parent
            running_exe = Path(sys.argv[0]).resolve()
            running_from_installer = (
                running_exe.exists()
                and running_exe.parent.resolve() == installer_dir.resolve()
            )
            if running_from_installer:
                try:
                    _MOVEFILE_DELAY_UNTIL_REBOOT = 4
                    for child in installer_dir.iterdir():
                        ctypes.windll.kernel32.MoveFileExW(
                            str(child), None, _MOVEFILE_DELAY_UNTIL_REBOOT
                        )
                    ctypes.windll.kernel32.MoveFileExW(
                        str(installer_dir), None, _MOVEFILE_DELAY_UNTIL_REBOOT
                    )
                    successes.append("Installer directory scheduled for deletion on reboot")
                except Exception as exc:
                    errors.append(f"Installer cleanup scheduling: {exc}")
            else:
                err = _remove_dir_safe(str(installer_dir))
                if err:
                    errors.append(err)
                else:
                    successes.append("Removed installer copy")
                    _remove_empty_parent(str(installer_dir))

        dir_errors = [e for e in errors if e.startswith("Directory")]
        if dir_errors:
            errors.append(
                "Some directories could not be removed. "
                "The install record has been preserved so you can re-run uninstall later."
            )
        else:
            try:
                unregister_uninstall()
            except Exception as exc:
                errors.append(f"Registry cleanup: {exc}")
            else:
                successes.append("Removed from Add/Remove Programs")

            try:
                remove_manifest()
            except Exception as exc:
                errors.append(f"Manifest cleanup: {exc}")
            else:
                successes.append("Removed install manifest")

        lines: list[str] = []
        if successes:
            lines.append("Removed:")
            for s in successes:
                lines.append(f"  \u2713  {s}")
        if errors:
            lines.append("")
            lines.append("Errors:")
            for e in errors:
                lines.append(f"  \u2717  {e}")
        lines.append("")
        lines.append("Your personal data and settings have been preserved.")

        self._uninstall_result_label.setText("\n".join(lines))
        self._stack.setCurrentIndex(_PAGE_UNINSTALL_COMPLETE)

    # ---- install action --------------------------------------------------

    def _run_install(self) -> None:
        if not self._elevated:
            reply = QMessageBox.question(
                self,
                "Elevation Required",
                "Installing to Program Files and updating system PATH requires "
                "administrator privileges.\n\n"
                "Relaunch setup.exe as administrator?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                try:
                    relaunch_elevated()
                except OSError as exc:
                    QMessageBox.critical(self, "Elevation Failed", str(exc))
                return

        if self._variant_info is None:
            QMessageBox.critical(self, "Cannot install", self._metadata_error)
            return

        errors: list[str] = []
        successes: list[str] = []

        src = self._source_root

        err = _install_component(src / "app", Path(self._le_dest_app.text()), "App")
        if err:
            errors.append(err)
        else:
            successes.append(f"App -> {self._le_dest_app.text()}")

        if self._variant_info.has_cli and self._le_dest_cli is not None:
            err = _install_component(src / "cli", Path(self._le_dest_cli.text()), "CLI")
            if err:
                errors.append(err)
            else:
                successes.append(f"CLI -> {self._le_dest_cli.text()}")

        if self._variant_info.has_server and self._le_dest_server is not None:
            err = _install_component(src / "server", Path(self._le_dest_server.text()), "Server")
            if err:
                errors.append(err)
            else:
                successes.append(f"Server -> {self._le_dest_server.text()}")

        app_dest = Path(self._le_dest_app.text())
        if self._chk_desktop.isChecked():
            try:
                _create_desktop_shortcut_dest(app_dest)
            except Exception as exc:
                errors.append(f"Desktop shortcut: {exc}")
            else:
                successes.append("Desktop shortcut")

        if self._chk_start.isChecked():
            try:
                _create_start_menu_shortcut_dest(app_dest)
            except Exception as exc:
                errors.append(f"Start Menu shortcut: {exc}")
            else:
                successes.append("Start Menu entry")

        path_changes: list[str] = []
        path_entries: list[str] = []

        if (
            self._variant_info.has_cli
            and self._chk_path_cli is not None
            and self._chk_path_cli.isChecked()
            and self._le_dest_cli is not None
        ):
            cli_dir = str(Path(self._le_dest_cli.text()))
            try:
                changed = add_to_machine_path(cli_dir)
            except PermissionError:
                errors.append("CLI PATH: permission denied — run installer as administrator")
            except Exception as exc:
                errors.append(f"CLI PATH: {exc}")
            else:
                if changed:
                    path_changes.append(f"CLI directory added to PATH: {cli_dir}")
                    path_entries.append(cli_dir)

        if (
            self._variant_info.has_server
            and self._chk_path_server is not None
            and self._chk_path_server.isChecked()
            and self._le_dest_server is not None
        ):
            server_dir = str(Path(self._le_dest_server.text()))
            try:
                changed = add_to_machine_path(server_dir)
            except PermissionError:
                errors.append("Server PATH: permission denied — run installer as administrator")
            except Exception as exc:
                errors.append(f"Server PATH: {exc}")
            else:
                if changed:
                    path_changes.append(f"Server directory added to PATH: {server_dir}")
                    path_entries.append(server_dir)

        successes.extend(path_changes)

        dest_map: dict[str, Path] = {"app": Path(self._le_dest_app.text())}
        if self._variant_info.has_cli and self._le_dest_cli is not None:
            dest_map["cli"] = Path(self._le_dest_cli.text())
        if self._variant_info.has_server and self._le_dest_server is not None:
            dest_map["server"] = Path(self._le_dest_server.text())

        shortcut_paths: list[str] = []
        if self._chk_desktop.isChecked():
            shortcut_paths.append(str(_desktop() / "Grouper.lnk"))
        if self._chk_start.isChecked():
            shortcut_paths.append(str(_start_menu_programs() / "Grouper" / "Grouper.lnk"))

        installer_err = _copy_installer_to_stable_location()
        installer_path = str(_stable_installer_path()) if installer_err is None else ""
        if installer_err:
            errors.append(f"Installer copy: {installer_err}")
        else:
            successes.append("Installer registered for uninstall")

        manifest = InstallManifest(
            version=_read_version(self._source_root),
            variant=self._variant_info.variant,
            install_time=datetime.now(UTC).isoformat(),
            destinations={k: str(v) for k, v in dest_map.items()},
            path_entries=path_entries,
            shortcuts=shortcut_paths,
            installer_path=installer_path,
        )
        try:
            write_manifest(manifest)
        except PermissionError as exc:
            errors.append(f"Install manifest: {exc}")
        else:
            successes.append("Install manifest written")

        try:
            register_uninstall(manifest)
        except PermissionError as exc:
            errors.append(f"Registry: {exc}")
        else:
            successes.append("Registered in Add/Remove Programs")

        lines: list[str] = []
        if successes:
            lines.append("Installed:")
            for s in successes:
                lines.append(f"  \u2713  {s}")
        if path_changes:
            lines.append("")
            lines.append("PATH updated \u2014 reopen any open terminals for changes to take effect.")
        if errors:
            lines.append("")
            lines.append("Errors:")
            for e in errors:
                lines.append(f"  \u2717  {e}")

        self._summary_label.setText("\n".join(lines))
        self._stack.setCurrentIndex(_PAGE_COMPLETE)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    uninstall_mode = "--uninstall" in sys.argv
    app = QApplication(sys.argv)
    app.setApplicationName("Grouper Setup")
    dlg = SetupDialog(uninstall_mode=uninstall_mode)
    dlg.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
