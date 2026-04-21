"""test_title_bar_unit.py -- Unit tests for title bar and custom-chrome window logic.

Tests the Win32 nativeEvent handling (WM_NCCALCSIZE, WM_NCHITTEST,
WM_GETMINMAXINFO, WM_NCMOUSEMOVE/LEAVE), DWM attribute calls, and
platform-guarded drag handlers without launching the full app.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import sys
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtWidgets import QApplication

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def main_window():
    """Create a MainWindow without showing it."""
    # Isolate config so it doesn't touch the real DB
    with (
        patch("grouper.app.get_config") as mock_cfg,
        patch("grouper.app.theme_colors", return_value={"border": "#7aa2f7"}),
    ):
        cfg = MagicMock()
        cfg.theme = "dark"
        cfg.window_width = 1000
        cfg.window_height = 600
        mock_cfg.return_value = cfg

        from grouper.app import MainWindow

        win = MainWindow()
        yield win
        win.close()
        win.deleteLater()


@pytest.fixture
def title_bar():
    """Create a standalone TitleBar widget."""
    from grouper.ui.title_bar import TitleBar

    tb = TitleBar()
    yield tb
    tb.deleteLater()


@pytest.fixture
def dialog_title_bar():
    """Create a standalone DialogTitleBar widget."""
    from grouper.ui.title_bar import DialogTitleBar

    dtb = DialogTitleBar("Test Dialog")
    yield dtb
    dtb.deleteLater()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_msg(message: int, wparam: int = 0, lparam: int = 0) -> ctypes.wintypes.MSG:
    """Build a fake MSG struct for nativeEvent testing."""
    msg = ctypes.wintypes.MSG()
    msg.message = message
    msg.wParam = wparam
    msg.lParam = lparam
    return msg


# ---------------------------------------------------------------------------
# WM_NCCALCSIZE tests
# ---------------------------------------------------------------------------


class TestWmNccalcsize:
    """WM_NCCALCSIZE handler eliminates the invisible non-client area."""

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    def test_returns_zero_when_wparam_set(self, main_window):
        """When wParam=1, should return (True, 0) regardless of maximized state."""
        from grouper.app import WM_NCCALCSIZE

        msg = _make_msg(WM_NCCALCSIZE, wparam=1, lparam=0)
        msg_addr = ctypes.addressof(msg)

        result = main_window.nativeEvent(b"windows_generic_MSG", msg_addr)

        assert result[0] is True, "Should indicate message was handled"
        assert result[1] == 0, "Should return 0 (no non-client area)"

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    def test_defers_when_wparam_zero(self, main_window):
        """When wParam=0, should defer to super().nativeEvent()."""
        from grouper.app import WM_NCCALCSIZE

        msg = _make_msg(WM_NCCALCSIZE, wparam=0, lparam=0)
        msg_addr = ctypes.addressof(msg)

        with patch.object(
            type(main_window).__mro__[1], "nativeEvent", return_value=(False, 0)
        ) as mock_super:
            _result = main_window.nativeEvent(b"windows_generic_MSG", msg_addr)
            mock_super.assert_called_once()


# ---------------------------------------------------------------------------
# WM_GETMINMAXINFO tests
# ---------------------------------------------------------------------------


class TestWmGetminmaxinfo:
    """WM_GETMINMAXINFO constrains maximised size to the monitor work area."""

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    def test_constrains_to_work_area(self, main_window, qapp: QApplication):
        """Should set ptMaxSize and ptMaxPosition from the monitor work area."""
        from grouper.app import MINMAXINFO, WM_GETMINMAXINFO

        # Create a MINMAXINFO struct in memory
        mmi = MINMAXINFO()
        mmi_addr = ctypes.addressof(mmi)

        msg = _make_msg(WM_GETMINMAXINFO, lparam=mmi_addr)
        msg_addr = ctypes.addressof(msg)

        main_window.show()
        qapp.processEvents()

        result = main_window.nativeEvent(b"windows_generic_MSG", msg_addr)

        assert result == (True, 0)
        # ptMaxSize should be positive (work area dimensions)
        assert mmi.ptMaxSize.x > 0, "ptMaxSize.x should be positive"
        assert mmi.ptMaxSize.y > 0, "ptMaxSize.y should be positive"


# ---------------------------------------------------------------------------
# WM_NCHITTEST tests
# ---------------------------------------------------------------------------


class TestWmNchittest:
    """WM_NCHITTEST returns correct hit-test codes for different regions."""

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    def test_edge_returns_resize_codes(self, main_window):
        """Cursor at the top-left corner should return HTTOPLEFT."""
        from grouper.app import HTTOPLEFT, WM_NCHITTEST

        main_window.setGeometry(100, 100, 800, 600)

        # Cursor at (101, 101) — 1px from top-left corner, within 6px border
        msg = _make_msg(WM_NCHITTEST)
        msg_addr = ctypes.addressof(msg)

        with (
            patch.object(type(main_window), "isMaximized", return_value=False),
            patch.object(
                type(main_window), "frameGeometry", return_value=QRect(100, 100, 800, 600)
            ),
            patch("grouper.app.QCursor") as mock_cursor,
        ):
            mock_cursor.pos.return_value = QPoint(101, 101)
            result = main_window.nativeEvent(b"windows_generic_MSG", msg_addr)

        assert result == (True, HTTOPLEFT)

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    def test_skips_resize_when_maximized(self, main_window, qapp: QApplication):
        """Edge positions should not return resize codes when maximized."""
        from grouper.app import HTTOPLEFT, WM_NCHITTEST

        main_window.setGeometry(100, 100, 800, 600)
        main_window.show()
        qapp.processEvents()

        msg = _make_msg(WM_NCHITTEST)
        msg_addr = ctypes.addressof(msg)

        with (
            patch.object(type(main_window), "isMaximized", return_value=True),
            patch.object(
                type(main_window), "frameGeometry", return_value=QRect(100, 100, 800, 600)
            ),
            patch("grouper.app.QCursor") as mock_cursor,
        ):
            mock_cursor.pos.return_value = QPoint(101, 101)
            result = main_window.nativeEvent(b"windows_generic_MSG", msg_addr)

        # Should NOT be a resize code
        if result[0] is True:
            assert result[1] != HTTOPLEFT

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    def test_title_bar_returns_htcaption(self, main_window, qapp: QApplication):
        """Cursor over the title bar (not on a button) should return HTCAPTION."""
        from grouper.app import HTCAPTION, WM_NCHITTEST

        main_window.setGeometry(100, 100, 800, 600)
        main_window.show()
        qapp.processEvents()

        tb = main_window._title_bar
        tb_center = tb.mapToGlobal(QPoint(tb.width() // 3, tb.height() // 2))

        msg = _make_msg(WM_NCHITTEST)
        msg_addr = ctypes.addressof(msg)

        with (
            patch.object(type(main_window), "isMaximized", return_value=False),
            patch("grouper.app.QCursor") as mock_cursor,
        ):
            mock_cursor.pos.return_value = tb_center
            result = main_window.nativeEvent(b"windows_generic_MSG", msg_addr)

        assert result == (True, HTCAPTION), f"Expected HTCAPTION, got {result}"

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    def test_max_button_hit_test(self, main_window, qapp: QApplication):
        """Cursor over the maximize button returns HTMAXBUTTON on Win11+
        (enables Snap Layouts flyout) or HTCLIENT on Win10 (Qt handles click).
        """
        from grouper.app import (
            _WIN11_OR_LATER,
            HTCLIENT,
            HTMAXBUTTON,
            WM_NCHITTEST,
        )

        main_window.setGeometry(100, 100, 800, 600)
        main_window.show()
        qapp.processEvents()

        btn = main_window._title_bar._btn_max
        btn_center = btn.mapToGlobal(QPoint(btn.width() // 2, btn.height() // 2))

        msg = _make_msg(WM_NCHITTEST)
        msg_addr = ctypes.addressof(msg)

        with (
            patch.object(type(main_window), "isMaximized", return_value=False),
            patch("grouper.app.QCursor") as mock_cursor,
        ):
            mock_cursor.pos.return_value = btn_center
            result = main_window.nativeEvent(b"windows_generic_MSG", msg_addr)

        expected = HTMAXBUTTON if _WIN11_OR_LATER else HTCLIENT
        assert result == (True, expected), f"Expected {expected}, got {result}"

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    @patch("grouper.app._WIN11_OR_LATER", True)
    def test_max_button_returns_htmaxbutton_on_win11(self, main_window, qapp: QApplication):
        """On Win11+, maximize button returns HTMAXBUTTON for Snap Layouts."""
        from grouper.app import HTMAXBUTTON, WM_NCHITTEST

        main_window.setGeometry(100, 100, 800, 600)
        main_window.show()
        qapp.processEvents()

        btn = main_window._title_bar._btn_max
        btn_center = btn.mapToGlobal(QPoint(btn.width() // 2, btn.height() // 2))

        msg = _make_msg(WM_NCHITTEST)
        msg_addr = ctypes.addressof(msg)

        with (
            patch.object(type(main_window), "isMaximized", return_value=False),
            patch("grouper.app.QCursor") as mock_cursor,
        ):
            mock_cursor.pos.return_value = btn_center
            result = main_window.nativeEvent(b"windows_generic_MSG", msg_addr)

        assert result == (True, HTMAXBUTTON)

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    @patch("grouper.app._WIN11_OR_LATER", False)
    def test_max_button_returns_htclient_on_win10(self, main_window, qapp: QApplication):
        """On Win10, maximize button returns HTCLIENT so Qt handles the click."""
        from grouper.app import HTCLIENT, WM_NCHITTEST

        main_window.setGeometry(100, 100, 800, 600)
        main_window.show()
        qapp.processEvents()

        btn = main_window._title_bar._btn_max
        btn_center = btn.mapToGlobal(QPoint(btn.width() // 2, btn.height() // 2))

        msg = _make_msg(WM_NCHITTEST)
        msg_addr = ctypes.addressof(msg)

        with (
            patch.object(type(main_window), "isMaximized", return_value=False),
            patch("grouper.app.QCursor") as mock_cursor,
        ):
            mock_cursor.pos.return_value = btn_center
            result = main_window.nativeEvent(b"windows_generic_MSG", msg_addr)

        assert result == (True, HTCLIENT)

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    def test_close_button_returns_htclient(self, main_window, qapp: QApplication):
        """Cursor over the close button should return HTCLIENT (Qt handles click)."""
        from grouper.app import HTCLIENT, WM_NCHITTEST

        main_window.setGeometry(100, 100, 800, 600)
        main_window.show()
        qapp.processEvents()

        btn = main_window._title_bar._btn_close
        btn_center = btn.mapToGlobal(QPoint(btn.width() // 2, btn.height() // 2))

        msg = _make_msg(WM_NCHITTEST)
        msg_addr = ctypes.addressof(msg)

        with (
            patch.object(type(main_window), "isMaximized", return_value=False),
            patch("grouper.app.QCursor") as mock_cursor,
        ):
            mock_cursor.pos.return_value = btn_center
            result = main_window.nativeEvent(b"windows_generic_MSG", msg_addr)

        assert result == (True, HTCLIENT), f"Expected HTCLIENT, got {result}"

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    def test_min_button_returns_htclient(self, main_window, qapp: QApplication):
        """Cursor over the minimize button should return HTCLIENT."""
        from grouper.app import HTCLIENT, WM_NCHITTEST

        main_window.setGeometry(100, 100, 800, 600)
        main_window.show()
        qapp.processEvents()

        btn = main_window._title_bar._btn_min
        btn_center = btn.mapToGlobal(QPoint(btn.width() // 2, btn.height() // 2))

        msg = _make_msg(WM_NCHITTEST)
        msg_addr = ctypes.addressof(msg)

        with (
            patch.object(type(main_window), "isMaximized", return_value=False),
            patch("grouper.app.QCursor") as mock_cursor,
        ):
            mock_cursor.pos.return_value = btn_center
            result = main_window.nativeEvent(b"windows_generic_MSG", msg_addr)

        assert result == (True, HTCLIENT), f"Expected HTCLIENT, got {result}"


# ---------------------------------------------------------------------------
# NC mouse hover tests
# ---------------------------------------------------------------------------


class TestNcMouseHover:
    """WM_NCMOUSEMOVE / WM_NCMOUSELEAVE track maximize button hover state."""

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    def test_ncmousemove_sets_hover_property(self, main_window):
        """WM_NCMOUSEMOVE with wParam=HTMAXBUTTON should set ncHover=True."""
        from grouper.app import HTMAXBUTTON, WM_NCMOUSEMOVE

        msg = _make_msg(WM_NCMOUSEMOVE, wparam=HTMAXBUTTON)
        msg_addr = ctypes.addressof(msg)

        result = main_window.nativeEvent(b"windows_generic_MSG", msg_addr)

        assert result == (True, 0)
        assert main_window._title_bar._btn_max.property("ncHover") is True

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    def test_ncmousemove_clears_hover_for_other_regions(self, main_window):
        """WM_NCMOUSEMOVE with wParam != HTMAXBUTTON should set ncHover=False."""
        from grouper.app import HTCAPTION, WM_NCMOUSEMOVE

        # First set hover on
        main_window._title_bar._btn_max.setProperty("ncHover", True)

        msg = _make_msg(WM_NCMOUSEMOVE, wparam=HTCAPTION)
        msg_addr = ctypes.addressof(msg)

        result = main_window.nativeEvent(b"windows_generic_MSG", msg_addr)

        assert result == (True, 0)
        assert main_window._title_bar._btn_max.property("ncHover") is False

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    def test_ncmouseleave_clears_hover(self, main_window):
        """WM_NCMOUSELEAVE should clear the ncHover property."""
        from grouper.app import WM_NCMOUSELEAVE

        # Set hover on first
        main_window._title_bar._btn_max.setProperty("ncHover", True)

        msg = _make_msg(WM_NCMOUSELEAVE)
        msg_addr = ctypes.addressof(msg)

        result = main_window.nativeEvent(b"windows_generic_MSG", msg_addr)

        assert result == (True, 0)
        assert main_window._title_bar._btn_max.property("ncHover") is False


# ---------------------------------------------------------------------------
# DWM attribute tests
# ---------------------------------------------------------------------------


class TestDwmAttributes:
    """DWM attributes are configured on show()."""

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    def test_apply_dwm_attributes_called_on_show(self, main_window):
        """show() should call _apply_dwm_attributes on Windows."""
        with patch.object(main_window, "_apply_dwm_attributes") as mock_dwm:
            main_window.show()
            mock_dwm.assert_called_once()

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    def test_apply_dwm_does_not_raise(self, main_window, qapp: QApplication):
        """_apply_dwm_attributes should never raise, even if DWM call fails."""
        main_window.show()
        qapp.processEvents()
        # Should not raise — errors are swallowed
        main_window._apply_dwm_attributes()

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    def test_extends_frame_into_client_area(self, main_window, qapp: QApplication):
        """_apply_dwm_attributes should call DwmExtendFrameIntoClientArea."""
        main_window.show()
        qapp.processEvents()

        with (
            patch("ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea") as mock_ext,
            patch("ctypes.windll.dwmapi.DwmSetWindowAttribute"),
        ):
            main_window._apply_dwm_attributes()
            mock_ext.assert_called_once()


# ---------------------------------------------------------------------------
# Platform-guarded drag handler tests
# ---------------------------------------------------------------------------


class TestTitleBarDragGuards:
    """TitleBar mouse handlers are no-ops on Windows."""

    def test_mouse_press_is_noop_on_win32(self, title_bar):
        """mousePressEvent should early-return on Windows."""
        event = MagicMock()
        event.button.return_value = Qt.MouseButton.LeftButton

        title_bar.mousePressEvent(event)

        if sys.platform == "win32":
            # Should not set _drag_pos
            assert title_bar._drag_pos is None
            # Should not call event.accept()
            event.accept.assert_not_called()

    def test_mouse_move_is_noop_on_win32(self, title_bar):
        """mouseMoveEvent should early-return on Windows."""
        event = MagicMock()
        title_bar.mouseMoveEvent(event)

        if sys.platform == "win32":
            event.accept.assert_not_called()

    def test_double_click_is_noop_on_win32(self, title_bar):
        """mouseDoubleClickEvent should early-return on Windows."""
        event = MagicMock()
        event.button.return_value = Qt.MouseButton.LeftButton

        title_bar.mouseDoubleClickEvent(event)

        if sys.platform == "win32":
            event.accept.assert_not_called()


class TestDialogTitleBarDragGuards:
    """DialogTitleBar mouse handlers are no-ops on Windows."""

    def test_mouse_press_is_noop_on_win32(self, dialog_title_bar):
        """mousePressEvent should early-return on Windows."""
        event = MagicMock()
        event.button.return_value = Qt.MouseButton.LeftButton

        dialog_title_bar.mousePressEvent(event)

        if sys.platform == "win32":
            assert dialog_title_bar._drag_pos is None
            event.accept.assert_not_called()

    def test_mouse_move_is_noop_on_win32(self, dialog_title_bar):
        """mouseMoveEvent should early-return on Windows."""
        event = MagicMock()
        dialog_title_bar.mouseMoveEvent(event)

        if sys.platform == "win32":
            event.accept.assert_not_called()


# ---------------------------------------------------------------------------
# Window state tracking
# ---------------------------------------------------------------------------


class TestWindowStateTracking:
    """changeEvent updates title bar icon and margins correctly."""

    def test_maximize_icon_updates(self, main_window):
        """Title bar max button text should reflect window state."""
        tb = main_window._title_bar
        tb.update_maximize_icon(True)
        assert tb._btn_max.text() == "❐"

        tb.update_maximize_icon(False)
        assert tb._btn_max.text() == "☐"

    def test_title_bar_buttons_exist(self, main_window):
        """Title bar should have min, max, and close buttons."""
        tb = main_window._title_bar
        assert tb._btn_min is not None
        assert tb._btn_max is not None
        assert tb._btn_close is not None

    def test_title_bar_height(self, main_window):
        """Title bar should have fixed height of 43px."""
        assert main_window._title_bar.maximumHeight() == 43


# ---------------------------------------------------------------------------
# Window flags
# ---------------------------------------------------------------------------


class TestWindowFlags:
    """Window flags are set correctly for custom-chrome snap compatibility."""

    def test_no_frameless_hint(self):
        """_WINDOW_FLAGS must NOT include FramelessWindowHint (breaks snap zones)."""
        from grouper.app import MainWindow

        flags = MainWindow._WINDOW_FLAGS
        assert not (flags & Qt.WindowType.FramelessWindowHint), (
            "FramelessWindowHint must not be set — it prevents Windows snap integration"
        )

    def test_includes_required_hints(self):
        """_WINDOW_FLAGS should include Window and WindowMinMaxButtonsHint."""
        from grouper.app import MainWindow

        flags = MainWindow._WINDOW_FLAGS
        assert flags & Qt.WindowType.WindowMinMaxButtonsHint
        assert flags & Qt.WindowType.Window


# ---------------------------------------------------------------------------
# WM_NCLBUTTONDOWN restore-then-drag tests
# ---------------------------------------------------------------------------


class TestWmNclbuttondown:
    """WM_NCLBUTTONDOWN handler restores the window before starting a drag."""

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    def test_restores_when_maximized(self, main_window):
        """Should call showNormal, move, ReleaseCapture, and SendMessageW."""
        from grouper.app import HTCAPTION, WM_NCLBUTTONDOWN

        x, y = 500, 15
        msg = _make_msg(WM_NCLBUTTONDOWN, wparam=HTCAPTION)
        msg_addr = ctypes.addressof(msg)

        tb = main_window._title_bar
        with (
            patch.object(type(main_window), "isMaximized", return_value=True),
            patch.object(type(main_window), "frameGeometry", return_value=QRect(0, 0, 1920, 1040)),
            patch.object(
                type(main_window), "normalGeometry", return_value=QRect(200, 150, 1000, 600)
            ),
            patch.object(tb, "mapToGlobal", return_value=QPoint(0, 0)),
            patch.object(main_window, "showNormal") as mock_show,
            patch.object(main_window, "move") as mock_move,
            patch("grouper.app.QApplication.processEvents"),
            patch("grouper.app.QCursor") as mock_cursor,
            patch("ctypes.windll.user32.ReleaseCapture") as mock_rc,
            patch("ctypes.windll.user32.SendMessageW") as mock_send,
        ):
            mock_cursor.pos.return_value = QPoint(x, y)
            result = main_window.nativeEvent(b"windows_generic_MSG", msg_addr)

        assert result == (True, 0)
        mock_show.assert_called_once()
        mock_move.assert_called_once()
        mock_rc.assert_called_once()
        mock_send.assert_called_once()
        call_args = mock_send.call_args[0]
        assert call_args[1] == WM_NCLBUTTONDOWN
        assert call_args[2] == HTCAPTION

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    def test_passthrough_when_not_maximized(self, main_window):
        """Should not intercept when the window is not maximized."""
        from grouper.app import HTCAPTION, WM_NCLBUTTONDOWN

        msg = _make_msg(WM_NCLBUTTONDOWN, wparam=HTCAPTION)
        msg_addr = ctypes.addressof(msg)

        with (
            patch.object(type(main_window), "isMaximized", return_value=False),
            patch.object(main_window, "showNormal") as mock_show,
            patch.object(type(main_window).__mro__[1], "nativeEvent", return_value=(False, 0)),
        ):
            main_window.nativeEvent(b"windows_generic_MSG", msg_addr)

        mock_show.assert_not_called()

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    def test_passthrough_for_non_caption(self, main_window):
        """Should not intercept WM_NCLBUTTONDOWN for non-caption hits."""
        from grouper.app import HTCLIENT, WM_NCLBUTTONDOWN

        msg = _make_msg(WM_NCLBUTTONDOWN, wparam=HTCLIENT)
        msg_addr = ctypes.addressof(msg)

        with (
            patch.object(type(main_window), "isMaximized", return_value=True),
            patch.object(main_window, "showNormal") as mock_show,
            patch.object(type(main_window).__mro__[1], "nativeEvent", return_value=(False, 0)),
        ):
            main_window.nativeEvent(b"windows_generic_MSG", msg_addr)

        mock_show.assert_not_called()

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    def test_proportional_position(self, main_window):
        """Restored window should position the cursor at the same spot on the title bar."""
        from grouper.app import HTCAPTION, WM_NCLBUTTONDOWN

        x, y = 480, 15
        msg = _make_msg(WM_NCLBUTTONDOWN, wparam=HTCAPTION)
        msg_addr = ctypes.addressof(msg)

        tb = main_window._title_bar
        with (
            patch.object(type(main_window), "isMaximized", return_value=True),
            patch.object(type(main_window), "frameGeometry", return_value=QRect(0, 0, 1920, 1040)),
            patch.object(
                type(main_window), "normalGeometry", return_value=QRect(200, 150, 1000, 600)
            ),
            patch.object(tb, "mapToGlobal", return_value=QPoint(0, 0)),
            patch.object(main_window, "showNormal"),
            patch.object(main_window, "move") as mock_move,
            patch("grouper.app.QApplication.processEvents"),
            patch("grouper.app.QCursor") as mock_cursor,
            patch("ctypes.windll.user32.ReleaseCapture"),
            patch("ctypes.windll.user32.SendMessageW"),
        ):
            mock_cursor.pos.return_value = QPoint(x, y)
            main_window.nativeEvent(b"windows_generic_MSG", msg_addr)

        move_args = mock_move.call_args[0]
        # ratio = 480/1920 = 0.25, new_x = 480 - 1000*0.25 = 230
        assert move_args[0] == 230, f"Expected new_x=230, got {move_args[0]}"
        # cursor_y_in_tb = 15 - 0 = 15, new_y = 15 - 15 - 1 = -1
        assert move_args[1] == -1, f"Expected new_y=-1, got {move_args[1]}"

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    def test_htmaxbutton_swallowed(self, main_window):
        """WM_NCLBUTTONDOWN with HTMAXBUTTON should be swallowed to prevent
        DefWindowProc's broken modal tracking loop on zero-size NC area."""
        from grouper.app import HTMAXBUTTON, WM_NCLBUTTONDOWN

        msg = _make_msg(WM_NCLBUTTONDOWN, wparam=HTMAXBUTTON)
        msg_addr = ctypes.addressof(msg)

        with (
            patch.object(main_window, "showNormal") as mock_normal,
            patch.object(main_window, "showMaximized") as mock_max,
        ):
            result = main_window.nativeEvent(b"windows_generic_MSG", msg_addr)

        assert result == (True, 0), "HTMAXBUTTON should be swallowed"
        mock_normal.assert_not_called()
        mock_max.assert_not_called()


# ---------------------------------------------------------------------------
# WM_NCLBUTTONUP tests
# ---------------------------------------------------------------------------


class TestWmNclbuttonup:
    """WM_NCLBUTTONUP handler toggles maximize/restore on HTMAXBUTTON."""

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    def test_maximizes_when_normal(self, main_window, qapp: QApplication):
        """Should call showMaximized when not maximized and cursor is
        over the maximize button."""
        from grouper.app import HTMAXBUTTON, WM_NCLBUTTONUP

        main_window.show()
        qapp.processEvents()

        btn = main_window._title_bar._btn_max
        btn_center = btn.mapToGlobal(
            QPoint(btn.width() // 2, btn.height() // 2),
        )

        msg = _make_msg(WM_NCLBUTTONUP, wparam=HTMAXBUTTON)
        msg_addr = ctypes.addressof(msg)

        with (
            patch.object(type(main_window), "isMaximized", return_value=False),
            patch("grouper.app.QCursor") as mock_cursor,
            patch.object(main_window, "showMaximized") as mock_max,
        ):
            mock_cursor.pos.return_value = btn_center
            result = main_window.nativeEvent(b"windows_generic_MSG", msg_addr)

        assert result == (True, 0)
        mock_max.assert_called_once()

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    def test_restores_when_maximized(self, main_window, qapp: QApplication):
        """Should call showNormal when maximized and cursor is over
        the maximize button."""
        from grouper.app import HTMAXBUTTON, WM_NCLBUTTONUP

        main_window.show()
        qapp.processEvents()

        btn = main_window._title_bar._btn_max
        btn_center = btn.mapToGlobal(
            QPoint(btn.width() // 2, btn.height() // 2),
        )

        msg = _make_msg(WM_NCLBUTTONUP, wparam=HTMAXBUTTON)
        msg_addr = ctypes.addressof(msg)

        with (
            patch.object(type(main_window), "isMaximized", return_value=True),
            patch("grouper.app.QCursor") as mock_cursor,
            patch.object(main_window, "showNormal") as mock_normal,
        ):
            mock_cursor.pos.return_value = btn_center
            result = main_window.nativeEvent(b"windows_generic_MSG", msg_addr)

        assert result == (True, 0)
        mock_normal.assert_called_once()

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    def test_no_toggle_when_cursor_outside_button(self, main_window, qapp: QApplication):
        """If cursor moves off the button before release, no toggle
        should happen (standard press-then-drag-off cancel)."""
        from grouper.app import HTMAXBUTTON, WM_NCLBUTTONUP

        main_window.show()
        qapp.processEvents()

        msg = _make_msg(WM_NCLBUTTONUP, wparam=HTMAXBUTTON)
        msg_addr = ctypes.addressof(msg)

        with (
            patch("grouper.app.QCursor") as mock_cursor,
            patch.object(main_window, "showMaximized") as mock_max,
            patch.object(main_window, "showNormal") as mock_normal,
        ):
            mock_cursor.pos.return_value = QPoint(0, 0)
            result = main_window.nativeEvent(b"windows_generic_MSG", msg_addr)

        assert result == (True, 0)
        mock_max.assert_not_called()
        mock_normal.assert_not_called()

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    def test_non_htmaxbutton_passes_through(self, main_window):
        """WM_NCLBUTTONUP for non-HTMAXBUTTON should fall through."""
        from grouper.app import HTCAPTION, WM_NCLBUTTONUP

        msg = _make_msg(WM_NCLBUTTONUP, wparam=HTCAPTION)
        msg_addr = ctypes.addressof(msg)

        with patch.object(type(main_window).__mro__[1], "nativeEvent", return_value=(False, 0)):
            result = main_window.nativeEvent(b"windows_generic_MSG", msg_addr)

        assert result == (False, 0)


# ---------------------------------------------------------------------------
# WM_NCLBUTTONDBLCLK tests
# ---------------------------------------------------------------------------


class TestWmNclbuttondblclk:
    """WM_NCLBUTTONDBLCLK handler swallows HTMAXBUTTON double-clicks."""

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    def test_htmaxbutton_swallowed(self, main_window):
        """WM_NCLBUTTONDBLCLK(HTMAXBUTTON) should be swallowed."""
        from grouper.app import HTMAXBUTTON, WM_NCLBUTTONDBLCLK

        msg = _make_msg(WM_NCLBUTTONDBLCLK, wparam=HTMAXBUTTON)
        msg_addr = ctypes.addressof(msg)

        result = main_window.nativeEvent(b"windows_generic_MSG", msg_addr)

        assert result == (True, 0)

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
    def test_non_htmaxbutton_passes_through(self, main_window):
        """WM_NCLBUTTONDBLCLK for non-HTMAXBUTTON should fall through."""
        from grouper.app import HTCAPTION, WM_NCLBUTTONDBLCLK

        msg = _make_msg(WM_NCLBUTTONDBLCLK, wparam=HTCAPTION)
        msg_addr = ctypes.addressof(msg)

        with patch.object(type(main_window).__mro__[1], "nativeEvent", return_value=(False, 0)):
            result = main_window.nativeEvent(b"windows_generic_MSG", msg_addr)

        assert result == (False, 0)
