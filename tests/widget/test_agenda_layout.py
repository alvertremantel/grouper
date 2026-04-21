"""Tests for agenda view layout: content fills full height, anchored to top."""

from grouper.ui.agenda_view import AgendaView

TALL_WIDTH = 900
TALL_HEIGHT = 1800
NORMAL_HEIGHT = 750


def _make_agenda(qapp, width: int = TALL_WIDTH, height: int = TALL_HEIGHT) -> AgendaView:
    av = AgendaView()
    av.resize(width, height)
    av.show()
    qapp.processEvents()
    qapp.processEvents()
    return av


class TestAgendaAnchoring:
    def test_grid_anchored_to_top(self, qapp) -> None:
        """TimeGrid should start at y=0, not float to center."""
        av = _make_agenda(qapp)
        try:
            grid_y = av._grid.mapTo(av, av._grid.rect().topLeft()).y()
            assert grid_y == 0
        finally:
            av.close()

    def test_taskbox_anchored_to_top(self, qapp) -> None:
        """Taskbox should start at y=0, not float to center."""
        av = _make_agenda(qapp)
        try:
            tb_y = av._taskbox.mapTo(av, av._taskbox.rect().topLeft()).y()
            assert tb_y == 0
        finally:
            av.close()

    def test_grid_fills_full_height(self, qapp) -> None:
        """TimeGrid should stretch to fill the full available height."""
        av = _make_agenda(qapp)
        try:
            assert av._grid.height() == av.height()
        finally:
            av.close()

    def test_taskbox_fills_full_height(self, qapp) -> None:
        """Taskbox should stretch to fill the full available height."""
        av = _make_agenda(qapp)
        try:
            assert av._taskbox.height() == av.height()
        finally:
            av.close()

    def test_no_gap_at_bottom(self, qapp) -> None:
        """No empty space between grid bottom and AgendaView bottom."""
        av = _make_agenda(qapp)
        try:
            grid_bottom = av._grid.mapTo(av, av._grid.rect().bottomRight()).y()
            assert grid_bottom >= av.height() - 1  # within 1px
        finally:
            av.close()
