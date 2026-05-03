"""
main.py — Entry point for Grouper.

Usage:
    uv run grouper
"""

import sys
import warnings
from pathlib import Path

if __package__ in {None, ""}:
    # Support ``python desktop/main.py`` from a source checkout. The public
    # entry points still import ``desktop.main:main`` normally.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import (
    QEasingCurve,
    QParallelAnimationGroup,
    QPropertyAnimation,
    QTimer,
)
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from desktop._win_startup import suppress_flicker
from desktop.app import MainWindow
from desktop.config import get_config
from desktop.database.connection import init_database
from desktop.styles import load_theme
from desktop.web_server import start_web_server


def main() -> None:
    # PySide6 issues RuntimeWarning (not RuntimeError) when .disconnect() is called
    # on a signal with no connected slots.  This is intentional in widget-pool code
    # where we disconnect before reconnect; suppress only from PySide6 internals.
    warnings.filterwarnings(
        "ignore",
        message="Failed to disconnect",
        category=RuntimeWarning,
        module="PySide6",
    )

    cfg = get_config()

    # Initialise database
    init_database()

    # Start HTML readouts server (daemon thread — exits with the process)
    start_web_server(cfg.web_port)

    app = QApplication(sys.argv)
    runtime_refs: dict[str, object] = {}
    app.setApplicationName("Grouper")
    app.setOrganizationName("Grouper")

    # Set a nice default font
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    # Apply theme
    load_theme(app, cfg.theme)

    # Set app icon (used by taskbar, title bar, About page)
    icon_path = Path(__file__).parent / "assets" / "icon.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    # Show splash screen immediately, before expensive MainWindow construction
    from desktop.ui.shared.splash import SplashScreen

    splash = SplashScreen(theme=cfg.theme)
    splash.show()
    splash.start_spinner()
    app.processEvents()  # force the splash to paint

    def _finish_startup() -> None:
        try:
            # Suppress small companion-window flicker during frameless construction
            unhook = suppress_flicker()

            window = MainWindow()
            runtime_refs["main_window"] = window

            # Hook no longer needed once the main window is constructed
            unhook()

            splash.stop_spinner()

            if cfg.animations_enabled:
                # Fade the splash out while fading the main window in
                window.setWindowOpacity(0.0)
                window.show()
                window.raise_()
                window.activateWindow()

                fade_in = QPropertyAnimation(window, b"windowOpacity")
                fade_in.setDuration(400)
                fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)
                fade_in.setStartValue(0.0)
                fade_in.setEndValue(1.0)

                fade_out = QPropertyAnimation(splash, b"windowOpacity")
                fade_out.setDuration(400)
                fade_out.setEasingCurve(QEasingCurve.Type.OutCubic)
                fade_out.setStartValue(1.0)
                fade_out.setEndValue(0.0)

                group = QParallelAnimationGroup(app)
                group.addAnimation(fade_in)
                group.addAnimation(fade_out)
                group.finished.connect(splash.close)
                group.finished.connect(group.deleteLater)
                group.start()
                runtime_refs["splash_anim"] = group
            else:
                splash.close()
                window.show()
                window.raise_()
                window.activateWindow()

            # Background version check — runs after the window is on screen
            from desktop.version_check import VersionCheckWorker as _VCW

            _vc_worker = _VCW()
            _vc_worker.update_available.connect(window.notify_update_available)
            _vc_worker.start()
            # Keep reference alive so GC doesn't collect the running thread
            runtime_refs["vc_worker"] = _vc_worker

        except Exception as e:
            import traceback

            traceback.print_exc()
            splash.close()
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.critical(None, "Grouper — Startup Error", str(e))
            sys.exit(1)

    QTimer.singleShot(50, _finish_startup)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
