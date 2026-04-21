"""
link_chips.py — Reusable link chip row widget for task cards and task list rows.
"""

import logging
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from ..database.task_links import get_links_for_task
from ..models import TaskLink
from .widgets import clear_layout

logger = logging.getLogger(__name__)

_MAX_CHIPS = 3
_LABEL_MAX_CHARS = 22


def _chip_label(link: TaskLink) -> str:
    """Return display text for a link chip: prefer label, else truncated URL."""
    icon = "🗂 " if link.link_type == "file" else "🔗 "
    text = link.label if link.label else link.url
    if len(text) > _LABEL_MAX_CHARS:
        text = text[: _LABEL_MAX_CHARS - 1] + "…"
    return icon + text


_ALLOWED_URL_SCHEMES = {"http", "https", "mailto"}


def _open_link(link: TaskLink) -> None:
    """Open the link using the OS default handler."""
    if link.link_type == "file":
        url = QUrl.fromLocalFile(str(Path(link.url).expanduser()))
    else:
        url = QUrl(link.url)
        if url.scheme().lower() not in _ALLOWED_URL_SCHEMES:
            logger.warning("Blocked URL with disallowed scheme: %s", url.scheme())
            return
    QDesktopServices.openUrl(url)


class LinkChipsRow(QWidget):
    """Horizontal row of clickable link chips. Hides itself when there are no links."""

    def __init__(self, task_id: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._task_id = task_id
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)
        self._populate()

    def set_task_id(self, task_id: int, links: list[TaskLink] | None = None) -> None:
        """Reassign task_id and reload chips. Enables pooled reuse.

        If *links* is provided, uses them directly instead of querying the DB.
        """
        self._task_id = task_id
        clear_layout(self._layout)
        self._populate(links)

    def refresh(self, task_id: int | None = None) -> None:
        """Reload links from DB and rebuild the chip row."""
        if task_id is not None:
            self._task_id = task_id
        # Clear existing widgets
        clear_layout(self._layout)
        self._populate()

    def _populate(self, links: list[TaskLink] | None = None) -> None:
        if links is None:
            links = get_links_for_task(self._task_id)
        if not links:
            self.hide()
            return

        visible = links[:_MAX_CHIPS]
        overflow = len(links) - _MAX_CHIPS

        for link in visible:
            btn = QPushButton(_chip_label(link))
            btn.setObjectName("linkChip")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(link.url)
            btn.setFlat(True)
            # Capture link in closure
            btn.clicked.connect(lambda checked=False, lnk=link: _open_link(lnk))
            self._layout.addWidget(btn)

        if overflow > 0:
            more = QLabel(f"+{overflow} more")
            more.setObjectName("smallMuted")
            self._layout.addWidget(more)

        self._layout.addStretch()
        self.show()
