"""Tests for dashboard layout: schedule anchoring, divider placement, height caps."""

from desktop.ui.time.time_grid import FADE_HEIGHT, HOUR_HEIGHT
from desktop.ui.views.dashboard import DashboardView

# Tall vertical screen simulation
VERTICAL_WIDTH = 900
VERTICAL_HEIGHT = 1800


def _make_dashboard(
    qapp, width: int = VERTICAL_WIDTH, height: int = VERTICAL_HEIGHT
) -> DashboardView:
    """Create a DashboardView, resize it, and process events so layout computes."""
    dv = DashboardView()
    dv.resize(width, height)
    dv.show()
    qapp.processEvents()
    qapp.processEvents()  # double-pump to ensure nested layouts settle
    return dv


def _widget_bottom(widget) -> int:
    """Return the global y-coordinate of a widget's bottom edge."""
    return widget.mapToGlobal(widget.rect().bottomLeft()).y()


def _widget_top(widget) -> int:
    """Return the global y-coordinate of a widget's top edge."""
    return widget.mapToGlobal(widget.rect().topLeft()).y()


class TestScheduleAnchoring:
    """The schedule section must sit at the top of the right column, not float down."""

    def test_schedule_top_aligns_near_taskbox_top(self, qapp):
        """Schedule and taskbox headers should start at roughly the same y-position."""
        dv = _make_dashboard(qapp)
        try:
            schedule_top = _widget_top(dv._schedule)
            taskbox_top = _widget_top(dv._taskbox_header)
            # They're in the same row, so tops should be within 50px of each other
            assert abs(schedule_top - taskbox_top) < 50, (
                f"Schedule top ({schedule_top}) should be near taskbox top ({taskbox_top}), "
                f"delta={abs(schedule_top - taskbox_top)}px — schedule is not anchored"
            )
        finally:
            dv.close()

    def test_schedule_does_not_float_to_middle(self, qapp):
        """On a tall screen, the schedule must NOT be pushed to the vertical center."""
        dv = _make_dashboard(qapp)
        try:
            schedule_top = _widget_top(dv._schedule)
            dashboard_top = _widget_top(dv)
            dashboard_height = dv.height()
            # Schedule should be in the top third of the dashboard, not the middle
            offset_from_top = schedule_top - dashboard_top
            assert offset_from_top < dashboard_height * 0.35, (
                f"Schedule starts at {offset_from_top}px from dashboard top "
                f"(dashboard height={dashboard_height}) — it's floating to the middle"
            )
        finally:
            dv.close()


class TestScheduleHeight:
    """The schedule section must be capped at ~75% of the full 24-hour grid."""

    def test_schedule_height_is_capped(self, qapp):
        """Schedule section height should not exceed the 75% cap + overhead."""
        dv = _make_dashboard(qapp)
        try:
            full_grid = HOUR_HEIGHT * 24 + FADE_HEIGHT * 2
            max_expected = int(full_grid * 0.75) + 100
            actual = dv._schedule.height()
            assert actual <= max_expected + 5, (
                f"Schedule height {actual}px exceeds cap {max_expected}px"
            )
        finally:
            dv.close()

    def test_schedule_height_is_reasonable(self, qapp):
        """Schedule should not be collapsed to a tiny size."""
        dv = _make_dashboard(qapp)
        try:
            actual = dv._schedule.height()
            # Should be at least 300px (not squished by layout)
            assert actual >= 300, (
                f"Schedule height {actual}px is too small — layout is squishing it"
            )
        finally:
            dv.close()


class TestDividerPlacement:
    """The second divider must sit directly below the two-column section."""

    def _find_dividers(self, dv: DashboardView) -> list:
        """Find all QFrame dividers in self._layout."""
        from PySide6.QtWidgets import QFrame

        dividers = []
        for i in range(dv._layout.count()):
            item = dv._layout.itemAt(i)
            w = item.widget() if item else None
            if isinstance(w, QFrame) and w.frameShape() == QFrame.Shape.HLine:
                dividers.append(w)
        return dividers

    def test_second_divider_exists(self, qapp):
        """There should be two horizontal dividers in the dashboard layout."""
        dv = _make_dashboard(qapp)
        try:
            dividers = self._find_dividers(dv)
            assert len(dividers) == 2, f"Expected 2 dividers, found {len(dividers)}"
        finally:
            dv.close()

    def test_second_divider_is_below_schedule(self, qapp):
        """The second divider should be just below the schedule section."""
        dv = _make_dashboard(qapp)
        try:
            dividers = self._find_dividers(dv)
            assert len(dividers) >= 2, "Need at least 2 dividers"
            divider2_top = _widget_top(dividers[1])
            schedule_bottom = _widget_bottom(dv._schedule)
            # Divider should be within 100px below the schedule bottom
            gap = divider2_top - schedule_bottom
            assert gap < 100, (
                f"Second divider is {gap}px below schedule bottom — "
                f"should be snug (divider_top={divider2_top}, schedule_bottom={schedule_bottom})"
            )
        finally:
            dv.close()

    def test_second_divider_not_at_screen_bottom(self, qapp):
        """The second divider must NOT be pushed to the bottom of the viewport."""
        dv = _make_dashboard(qapp)
        try:
            dividers = self._find_dividers(dv)
            assert len(dividers) >= 2, "Need at least 2 dividers"
            divider2_top = _widget_top(dividers[1])
            dashboard_top = _widget_top(dv)
            dashboard_height = dv.height()
            offset = divider2_top - dashboard_top
            # Divider should be in the top 75% of the dashboard, not the bottom
            assert offset < dashboard_height * 0.75, (
                f"Second divider at {offset}px from top (dashboard height={dashboard_height}) — "
                f"it's at the bottom of the screen"
            )
        finally:
            dv.close()
