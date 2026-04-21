"""
app.py — Main application window for Grouper.

Houses the sidebar navigation and an AnimatedViewStack to swap between views
with slide transitions.  Uses a custom title bar (frameless window) so the
appearance matches the application theme rather than leaking the OS accent colour.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import sys
from typing import ClassVar

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QColor, QCursor, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from ._version import __version__
from .config import get_config
from .styles import theme_colors
from .ui.about import AboutView
from .ui.animated_stack import AnimatedViewStack
from .ui.calendar_view import CalendarView
from .ui.dashboard import DashboardView
from .ui.history import HistoryView
from .ui.icons import clear_cache as clear_icon_cache
from .ui.settings import SettingsView
from .ui.sidebar import Sidebar
from .ui.summary import SummaryView
from .ui.sync_view import SyncView
from .ui.task_board import TaskBoardView
from .ui.task_list import TaskListView
from .ui.time_tracker import TimeTrackerView
from .ui.title_bar import TitleBar

# Win32 constants for nativeEvent edge-resize hit-testing
_RESIZE_BORDER = 6  # pixels from edge where resize is active

WM_GETMINMAXINFO = 0x0024
WM_NCCALCSIZE = 0x0083
WM_NCHITTEST = 0x0084
WM_NCMOUSEMOVE = 0x00A0
WM_NCLBUTTONDOWN = 0x00A1
WM_NCLBUTTONUP = 0x00A2
WM_NCLBUTTONDBLCLK = 0x00A3
WM_NCMOUSELEAVE = 0x02A2

HTCLIENT = 1
HTCAPTION = 2
HTMAXBUTTON = 9
HTLEFT = 10
HTRIGHT = 11
HTTOP = 12
HTTOPLEFT = 13
HTTOPRIGHT = 14
HTBOTTOM = 15
HTBOTTOMLEFT = 16
HTBOTTOMRIGHT = 17

MONITOR_DEFAULTTONEAREST = 2

# Win11 Snap Layouts require HTMAXBUTTON; Win10 can't handle it on a
# frameless window (ghost overlay, no action).  Cache the check once.
_WIN11_OR_LATER: bool = sys.platform == "win32" and sys.getwindowsversion().build >= 22000


# -- Win32 ctypes structures ------------------------------------------------


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class MINMAXINFO(ctypes.Structure):
    _fields_ = [
        ("ptReserved", POINT),
        ("ptMaxSize", POINT),
        ("ptMaxPosition", POINT),
        ("ptMinTrackSize", POINT),
        ("ptMaxTrackSize", POINT),
    ]


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.wintypes.DWORD),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", ctypes.wintypes.DWORD),
    ]


class MARGINS(ctypes.Structure):
    _fields_ = [
        ("cxLeftWidth", ctypes.c_int),
        ("cxRightWidth", ctypes.c_int),
        ("cyTopHeight", ctypes.c_int),
        ("cyBottomHeight", ctypes.c_int),
    ]


class _BorderedCentral(QWidget):
    """Central widget that paints the theme-colored window border on top of its surface."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._border_color = theme_colors(get_config().theme).get("window-border", "#7aa2f7")

    def changeEvent(self, event: QEvent) -> None:
        if event.type() == QEvent.Type.StyleChange:
            self._border_color = theme_colors(get_config().theme).get("window-border", "#7aa2f7")
        super().changeEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        if self.window().isMaximized():
            return
        border_width = 1
        painter = QPainter(self)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        pen = QPen(QColor(self._border_color), border_width)
        painter.setPen(pen)
        half = border_width // 2
        painter.drawRect(half, half, self.width() - border_width, self.height() - border_width)
        painter.end()


class MainWindow(QMainWindow):
    """Top-level window with sidebar + stacked views."""

    VIEW_MAP: ClassVar[dict[str, int]] = {
        "Dashboard": 0,
        "Time Tracker": 1,
        "Task Board": 2,
        "Task List": 3,
        "Calendar": 4,
        "History": 5,
        "Summary": 6,
        "Sync": 7,
        "Settings": 8,
        "About": 9,
    }

    _WINDOW_FLAGS = (
        Qt.WindowType.Window | Qt.WindowType.WindowMinMaxButtonsHint  # keeps taskbar behaviour
    )

    def __init__(self):
        super().__init__()
        cfg = get_config()

        self.setWindowTitle("Grouper — Productivity Hub")
        self.resize(cfg.window_width, cfg.window_height)
        self.setMinimumSize(800, 500)

        # Window flags are applied in show() instead of here to avoid Qt
        # creating internal companion windows that flash during construction.
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        self._pending_update_url: str = ""
        self._restoring_from_max: bool = False
        self._build()

    def _build(self):
        central = _BorderedCentral()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(1, 1, 1, 1)
        outer.setSpacing(0)

        # Custom title bar (top)
        self._title_bar = TitleBar()
        outer.addWidget(self._title_bar)

        # Content area (sidebar + stacked views)
        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Sidebar
        self._sidebar = Sidebar()
        self._sidebar.navigation_changed.connect(self._switch_view)
        content_layout.addWidget(self._sidebar)

        # Stacked views — processEvents() between each so the splash
        # spinner stays animated during construction.
        _pe = QApplication.processEvents
        self._stack = AnimatedViewStack()

        self._dashboard = DashboardView()
        self._dashboard.navigate_requested.connect(self._navigate_to_subview)
        self._stack.addWidget(self._dashboard)  # 0
        _pe()

        self._time_tracker = TimeTrackerView()
        self._time_tracker.session_changed.connect(self._on_session_changed)
        self._stack.addWidget(self._time_tracker)  # 1
        _pe()

        self._task_board = TaskBoardView()
        self._stack.addWidget(self._task_board)  # 2
        _pe()

        self._task_list = TaskListView()
        self._stack.addWidget(self._task_list)  # 3
        _pe()

        self._calendar = CalendarView()
        self._stack.addWidget(self._calendar)  # 4
        _pe()

        self._history = HistoryView()
        self._stack.addWidget(self._history)  # 5
        _pe()

        self._summary = SummaryView()
        self._stack.addWidget(self._summary)  # 6
        _pe()

        self._sync = SyncView()
        self._stack.addWidget(self._sync)  # 7
        QApplication.instance().aboutToQuit.connect(self._sync.cleanup)
        _pe()

        self._settings = SettingsView()
        self._stack.addWidget(self._settings)  # 8
        _pe()

        self._about = AboutView()
        self._stack.addWidget(self._about)  # 9

        content_layout.addWidget(self._stack, stretch=1)
        outer.addWidget(content, stretch=1)

        # Status bar
        status = QStatusBar()
        self.setStatusBar(status)
        status.showMessage(f"Grouper v{__version__} — Ready")

    def show(self):
        """Apply window flags just before the first show to avoid
        Qt's internal companion-window flicker during construction."""
        self.setWindowFlags(self._WINDOW_FLAGS)
        super().show()
        if sys.platform == "win32":
            self._apply_dwm_attributes()

    def _apply_dwm_attributes(self) -> None:
        """Configure DWM for custom-chrome window.

        1. Disable rounded corners on Win11 to prevent border clipping.
        2. Extend the DWM frame by 1px to restore the drop shadow that
           WM_NCCALCSIZE returning 0 kills.

        Silently ignored on Win10 (attribute 33 not supported).
        """
        try:
            hwnd = int(self.winId())

            # Disable Win11 rounded corners
            DWMWA_WINDOW_CORNER_PREFERENCE = 33
            preference = ctypes.c_int(1)  # DWMWCP_DONOTROUND
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                DWMWA_WINDOW_CORNER_PREFERENCE,
                ctypes.byref(preference),
                ctypes.sizeof(preference),
            )

            # Restore DWM drop shadow by extending frame 1px into client area
            margins = MARGINS(1, 1, 1, 1)
            ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(
                hwnd,
                ctypes.byref(margins),
            )
        except Exception:
            pass

    # -- navigation ----------------------------------------------------------

    def _switch_view(self, name: str):
        idx = self.VIEW_MAP.get(name, 0)
        self._stack.setCurrentIndex(idx)

    def _navigate_to_subview(self, view_name: str, sub_index: int) -> None:
        """Navigate to a top-level view, then select a sub-view within it."""
        self._sidebar.select(view_name)
        if view_name == "Calendar":
            self._calendar.select_view(sub_index)

    def notify_update_available(self, version: str, url: str) -> None:
        """Called from VersionCheckWorker when a newer release exists."""
        self._pending_update_url = url
        self.statusBar().showMessage(
            f"⬆  Update available: v{version} — open the About page to download",
            0,  # 0 = persistent (no auto-dismiss)
        )

    def _on_session_changed(self):
        """Refresh dashboard when session state changes."""
        self._dashboard.refresh()

    # -- window state tracking -----------------------------------------------

    def changeEvent(self, event: QEvent) -> None:
        """Update the title bar maximise icon when state changes."""
        super().changeEvent(event)
        if hasattr(self, "_title_bar"):
            self._title_bar.update_maximize_icon(self.isMaximized())
        if event.type() == QEvent.Type.StyleChange:
            clear_icon_cache()
            cw = self.centralWidget()
            if cw is not None:
                cw.update()
        elif event.type() == QEvent.Type.WindowStateChange:
            cw = self.centralWidget()
            if cw is not None:
                m = 0 if self.isMaximized() else 1
                if cw.layout() is not None:
                    cw.layout().setContentsMargins(m, m, m, m)
                cw.update()

    # -- Windows native event handling ----------------------------------------

    if sys.platform == "win32":

        def _handle_nccalcsize(self, msg) -> tuple[bool, int] | None:
            """Collapse the non-client area to zero (hides native frame)."""
            if msg.wParam:
                return True, 0
            return None

        def _handle_getminmaxinfo(self, msg) -> tuple[bool, int] | None:
            """Constrain maximised size to monitor work-area (prevents taskbar bleed)."""
            hwnd = int(self.winId())
            hmon = ctypes.windll.user32.MonitorFromWindow(
                hwnd,
                MONITOR_DEFAULTTONEAREST,
            )
            mi = MONITORINFO()
            mi.cbSize = ctypes.sizeof(MONITORINFO)
            ctypes.windll.user32.GetMonitorInfoW(
                hmon,
                ctypes.byref(mi),
            )

            mmi = MINMAXINFO.from_address(msg.lParam)
            work = mi.rcWork
            mon = mi.rcMonitor
            mmi.ptMaxPosition.x = work.left - mon.left
            mmi.ptMaxPosition.y = work.top - mon.top
            mmi.ptMaxSize.x = work.right - work.left
            mmi.ptMaxSize.y = work.bottom - work.top
            return True, 0

        def _handle_nchittest(self, msg) -> tuple[bool, int] | None:
            """Edge-resize, title bar drag, and window-control hit-testing."""
            # Use QCursor.pos() — returns logical coords matching
            # mapToGlobal(), avoiding physical/logical mismatch at
            # >100% display scaling.
            pos = QCursor.pos()
            x, y = pos.x(), pos.y()

            # Map to widget-local coordinates
            geo = self.frameGeometry()
            lx = x - geo.left()
            ly = y - geo.top()
            w = geo.width()
            h = geo.height()

            # Edge / corner resize (skip when maximised)
            if not self.isMaximized():
                on_left = lx < _RESIZE_BORDER
                on_right = lx > w - _RESIZE_BORDER
                on_top = ly < _RESIZE_BORDER
                on_bottom = ly > h - _RESIZE_BORDER

                if on_top and on_left:
                    return True, HTTOPLEFT
                if on_top and on_right:
                    return True, HTTOPRIGHT
                if on_bottom and on_left:
                    return True, HTBOTTOMLEFT
                if on_bottom and on_right:
                    return True, HTBOTTOMRIGHT
                if on_left:
                    return True, HTLEFT
                if on_right:
                    return True, HTRIGHT
                if on_top:
                    return True, HTTOP
                if on_bottom:
                    return True, HTBOTTOM

            # Title bar hit-testing — enables native drag + snap
            if hasattr(self, "_title_bar"):
                tb = self._title_bar
                tb_rect = tb.rect()
                tb_top_left = tb.mapToGlobal(tb_rect.topLeft())
                tb_bottom_right = tb.mapToGlobal(tb_rect.bottomRight())

                if (
                    tb_top_left.x() <= x <= tb_bottom_right.x()
                    and tb_top_left.y() <= y <= tb_bottom_right.y()
                ):
                    # Maximize button — Win11 returns HTMAXBUTTON for
                    # Snap Layouts flyout; Win10 returns HTCLIENT so Qt's
                    # button handles the click (Win10 can't render the
                    # native maximize overlay on a frameless window).
                    max_btn = tb._btn_max
                    btn_tl = max_btn.mapToGlobal(max_btn.rect().topLeft())
                    btn_br = max_btn.mapToGlobal(max_btn.rect().bottomRight())
                    if btn_tl.x() <= x <= btn_br.x() and btn_tl.y() <= y <= btn_br.y():
                        if _WIN11_OR_LATER:
                            return True, HTMAXBUTTON
                        return True, HTCLIENT

                    # Min / close → HTCLIENT so Qt handles click
                    for ctrl_btn in (tb._btn_min, tb._btn_close):
                        btn_tl = ctrl_btn.mapToGlobal(ctrl_btn.rect().topLeft())
                        btn_br = ctrl_btn.mapToGlobal(ctrl_btn.rect().bottomRight())
                        if btn_tl.x() <= x <= btn_br.x() and btn_tl.y() <= y <= btn_br.y():
                            return True, HTCLIENT

                    # Not over any button — draggable caption
                    return True, HTCAPTION
            return None

        def _handle_nclbuttondown(self, msg) -> tuple[bool, int] | None:
            """Restore-then-drag for HTCAPTION; swallow HTMAXBUTTON to
            prevent DefWindowProc's broken tracking loop on zero-size
            NC area."""
            if msg.wParam == HTMAXBUTTON:
                # Swallow — DefWindowProc would enter a modal tracking
                # loop that fails because the NC area is 0px.  The
                # actual toggle happens on WM_NCLBUTTONUP.
                return True, 0

            if msg.wParam == HTCAPTION and self.isMaximized() and not self._restoring_from_max:
                pos = QCursor.pos()
                x, y = pos.x(), pos.y()

                tb_origin = self._title_bar.mapToGlobal(self._title_bar.rect().topLeft())
                cursor_y_in_tb = y - tb_origin.y()

                max_geo = self.frameGeometry()
                ratio = (x - max_geo.left()) / max(max_geo.width(), 1)
                restore_width = self.normalGeometry().width()

                self._restoring_from_max = True
                self.showNormal()
                # processEvents() re-enters the event loop so showNormal()
                # completes before we reposition.  The _restoring_from_max
                # guard prevents re-entry via the re-sent WM_NCLBUTTONDOWN.
                QApplication.processEvents()

                new_x = int(x - restore_width * ratio)
                new_y = y - cursor_y_in_tb - 1
                self.move(new_x, new_y)

                self._restoring_from_max = False

                ctypes.windll.user32.ReleaseCapture()
                hwnd = int(self.winId())
                # lParam packs logical coords — SendMessageW to same HWND
                # stays in-process so no physical conversion needed.
                lp = ((y & 0xFFFF) << 16) | (x & 0xFFFF)
                ctypes.windll.user32.SendMessageW(
                    hwnd,
                    WM_NCLBUTTONDOWN,
                    HTCAPTION,
                    lp,
                )
                return True, 0
            return None

        def _handle_nclbuttonup(self, msg) -> tuple[bool, int] | None:
            """Toggle maximize/restore when the user releases on the
            max button.  Only fires when cursor is still within the
            button rect — pressing and dragging off cancels the action
            (standard button semantics)."""
            if msg.wParam == HTMAXBUTTON:
                if hasattr(self, "_title_bar"):
                    pos = QCursor.pos()
                    x, y = pos.x(), pos.y()
                    max_btn = self._title_bar._btn_max
                    btn_tl = max_btn.mapToGlobal(max_btn.rect().topLeft())
                    btn_br = max_btn.mapToGlobal(max_btn.rect().bottomRight())
                    if btn_tl.x() <= x <= btn_br.x() and btn_tl.y() <= y <= btn_br.y():
                        if self.isMaximized():
                            self.showNormal()
                        else:
                            self.showMaximized()
                return True, 0
            return None

        def _handle_nclbuttondblclk(self, msg) -> tuple[bool, int] | None:
            """Swallow double-click on HTMAXBUTTON — same DefWindowProc
            tracking loop issue as WM_NCLBUTTONDOWN."""
            if msg.wParam == HTMAXBUTTON:
                return True, 0
            return None

        def _handle_ncmousemove(self, msg) -> tuple[bool, int] | None:
            """Track hover state for the maximize button."""
            if hasattr(self, "_title_bar"):
                hovering = msg.wParam == HTMAXBUTTON
                max_btn = self._title_bar._btn_max
                max_btn.setProperty("ncHover", hovering)
                max_btn.style().polish(max_btn)
                return True, 0
            return None

        def _handle_ncmouseleave(self, msg) -> tuple[bool, int] | None:
            """Clear max-button hover on NC mouse leave."""
            if hasattr(self, "_title_bar"):
                max_btn = self._title_bar._btn_max
                max_btn.setProperty("ncHover", False)
                max_btn.style().polish(max_btn)
            return True, 0

        _NC_DISPATCH: dict[int, str] = {
            WM_NCCALCSIZE: "_handle_nccalcsize",
            WM_GETMINMAXINFO: "_handle_getminmaxinfo",
            WM_NCHITTEST: "_handle_nchittest",
            WM_NCLBUTTONDOWN: "_handle_nclbuttondown",
            WM_NCLBUTTONUP: "_handle_nclbuttonup",
            WM_NCLBUTTONDBLCLK: "_handle_nclbuttondblclk",
            WM_NCMOUSEMOVE: "_handle_ncmousemove",
            WM_NCMOUSELEAVE: "_handle_ncmouseleave",
        }

        def nativeEvent(self, event_type, message):
            """Win32 message dispatch for custom-chrome window management."""
            if event_type == b"windows_generic_MSG":
                try:
                    msg = ctypes.wintypes.MSG.from_address(int(message))
                except Exception:
                    return super().nativeEvent(event_type, message)

                handler_name = self._NC_DISPATCH.get(msg.message)
                if handler_name is not None:
                    result = getattr(self, handler_name)(msg)
                    if result is not None:
                        return result

            return super().nativeEvent(event_type, message)
