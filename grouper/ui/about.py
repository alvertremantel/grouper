"""
about.py — About page for Grouper.

Static, scrollable view with five cards:
  1. Version info
  2. Links (GitHub, Releases, Contact)
  3. Shoutouts
  4. System info + clipboard copy
  5. Features & details (collapsible, starts collapsed)
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import PySide6
from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QClipboard, QDesktopServices, QShowEvent
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from ..version_check import VersionCheckWorker

from .._urls import CONTACT_URL, GITHUB_RELEASES_URL, GITHUB_REPO_URL, THREADS_HANDLE
from .._version import __version__
from ..config import get_config
from ..database.connection import get_data_directory
from ..styles import theme_colors
from .icons import get_icon

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _card() -> QFrame:
    """Return a styled card frame."""
    frame = QFrame()
    frame.setObjectName("card")
    return frame


def _label(text: str, object_name: str = "", word_wrap: bool = True) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(word_wrap)
    if object_name:
        lbl.setObjectName(object_name)
    return lbl


def _make_link_row(icon_name: str, label_text: str, url: str) -> QWidget:
    """One row: SVG icon · label · open-URL button."""
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)

    stroke = theme_colors(get_config().theme)["icon_stroke"]
    icon_lbl = QLabel()
    icon_lbl.setPixmap(get_icon(icon_name, stroke, size=16).pixmap(16, 16))
    icon_lbl.setFixedSize(16, 16)
    layout.addWidget(icon_lbl)
    lbl = _label(label_text)
    layout.addWidget(lbl, stretch=1)

    btn = QPushButton("Open ↗")
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(url)))
    layout.addWidget(btn)

    return row


# ---------------------------------------------------------------------------
# AboutView
# ---------------------------------------------------------------------------


class AboutView(QWidget):
    """Static, scrollable About page."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._vc_worker: VersionCheckWorker | None = None
        self._update_url: str = ""
        self._build()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Scroll area wraps everything
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

        # Page heading
        heading = _label("About Grouper", "heading")
        heading.setProperty("heading", True)
        layout.addWidget(heading)

        layout.addWidget(self._version_card())
        layout.addWidget(self._links_card())
        layout.addWidget(self._shoutouts_card())
        layout.addWidget(self._sysinfo_card())
        layout.addWidget(self._collapsible_readme_card())

        layout.addStretch()

        scroll.setWidget(container)
        outer.addWidget(scroll)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if self._vc_worker is not None and self._vc_worker.isRunning():
            return
        self._run_version_check()

    # -- Version check -------------------------------------------------------

    def _run_version_check(self) -> None:
        from ..version_check import VersionCheckWorker

        self._update_status.setText("Checking for updates…")
        self._download_btn.setVisible(False)
        worker = VersionCheckWorker()
        self._vc_worker = worker
        worker.update_available.connect(self._on_update_available)
        worker.up_to_date.connect(self._on_up_to_date)
        worker.check_failed.connect(self._on_check_failed)
        worker.start()

    def _on_update_available(self, version: str, url: str) -> None:
        self._update_url = url
        self._update_status.setText(f"⬆  Update available: v{version}")
        self._download_btn.setText(f"Download v{version}")
        self._download_btn.setVisible(True)

    def _on_download_clicked(self) -> None:
        if self._update_url:
            QDesktopServices.openUrl(QUrl(self._update_url))

    def _on_up_to_date(self) -> None:
        self._update_status.setText("✓  You're on the latest version")

    def _on_check_failed(self) -> None:
        self._update_status.setText("Could not check for updates")

    # -- Cards ---------------------------------------------------------------

    def _version_card(self) -> QFrame:
        card = _card()
        outer = QHBoxLayout(card)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(16)

        # Left column — app icon
        app = QApplication.instance()
        if app is not None:
            icon_lbl = QLabel()
            icon_lbl.setPixmap(app.windowIcon().pixmap(QSize(288, 288)))
            icon_lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
            icon_lbl.setFixedWidth(288)
            icon_lbl.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
            outer.addWidget(icon_lbl)

        # Right column — version info
        lay = QVBoxLayout()
        lay.setSpacing(8)

        title = _label(f"Grouper v{__version__}", "titleLabelLarge")
        lay.addWidget(title)

        sub = _label(
            "A local productivity hub for time tracking and task management.",
            "subheading",
        )
        lay.addWidget(sub)

        lay.addWidget(_label("Built with Python + PySide6.", "mutedLabel"))
        lay.addWidget(_label("All data stored locally in SQLite.", "mutedLabel"))

        self._update_status = _label("Checking for updates…", "mutedLabel")
        lay.addWidget(self._update_status)

        self._download_btn = QPushButton("Open Release Page ↗")
        self._download_btn.setVisible(False)
        self._download_btn.clicked.connect(self._on_download_clicked)
        lay.addWidget(self._download_btn)

        check_btn = QPushButton("Check for Updates")
        check_btn.clicked.connect(self._run_version_check)
        lay.addWidget(check_btn)

        lay.addStretch()
        outer.addLayout(lay)

        return card

    def _links_card(self) -> QFrame:
        card = _card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(8)

        header = _label("Links", "subheading")
        lay.addWidget(header)

        lay.addWidget(_make_link_row("github", "GitHub Repository", GITHUB_REPO_URL))
        lay.addWidget(_make_link_row("download", "Releases / Changelog", GITHUB_RELEASES_URL))
        lay.addWidget(_make_link_row("mail", "Contact / Report a Bug", CONTACT_URL))

        note = _label(
            f"You can also DM {THREADS_HANDLE} on Threads for support.",
            "mutedLabel",
        )
        lay.addWidget(note)

        return card

    def _shoutouts_card(self) -> QFrame:
        card = _card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(8)

        header = _label("Special Thanks", "subheading")
        lay.addWidget(header)

        intro = _label(
            "With gratitude to our early supporters who purchased Grouper on Gumroad before it went open-source:",
            "mutedLabel",
        )
        lay.addWidget(intro)

        for handle in ("@jackgrebin", "@timecode.violation"):
            lbl = _label(handle, "mutedLabel")
            lay.addWidget(lbl)

        return card

    def _collapsible_readme_card(self) -> QFrame:
        card = _card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(12)

        toggle_btn = QPushButton("Features & Details ▸")
        toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        toggle_btn.setFlat(True)
        toggle_btn.setStyleSheet(
            "QPushButton { "
            "  text-align: left; "
            "  font-weight: bold; "
            "  font-size: 14px; "
            "  padding: 4px 0; "
            "  border: none; "
            "  background: transparent; "
            "}"
        )

        content = QWidget()
        content.setVisible(False)
        content_lay = QVBoxLayout(content)
        content_lay.setContentsMargins(0, 0, 0, 0)
        content_lay.setSpacing(12)

        features = [
            "Time Tracker — start/stop/pause sessions, tag them to tasks or activities",
            "Task Board — Kanban-style board with drag-and-drop columns",
            "Task List — flat list view with filtering and sorting",
            "Calendar — visualise sessions and deadlines by day/week/month",
            "History — browse every past session with search and filters",
            "Summary — aggregate stats: daily, weekly, and per-project breakdowns",
            "Dashboard — at-a-glance overview of today's work and upcoming tasks",
        ]
        features_lay = QVBoxLayout()
        features_lay.setSpacing(4)
        features_lay.addWidget(_label("Features", "subheading"))
        for feat in features:
            features_lay.addWidget(_label(f"• {feat}", "mutedLabel"))
        content_lay.addLayout(features_lay)

        content_lay.addWidget(_label("Data Storage", "subheading"))
        content_lay.addWidget(
            _label(
                "All data is stored locally in SQLite. No cloud sync, no accounts, "
                "no telemetry. Your data never leaves your machine.",
                "mutedLabel",
            )
        )

        content_lay.addWidget(_label("Built With", "subheading"))
        built_with = [
            "Python 3.11+",
            "PySide6 — Qt bindings for Python",
            "SQLite — embedded database",
        ]
        for item in built_with:
            content_lay.addWidget(_label(f"• {item}", "mutedLabel"))

        def _toggle() -> None:
            visible = not content.isVisible()
            content.setVisible(visible)
            toggle_btn.setText("Features & Details ▾" if visible else "Features & Details ▸")

        toggle_btn.clicked.connect(_toggle)
        lay.addWidget(toggle_btn)
        lay.addWidget(content)

        return card

    def _sysinfo_card(self) -> QFrame:
        card = _card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(8)

        group = QGroupBox("System Info")
        group_lay = QVBoxLayout(group)
        group_lay.setSpacing(4)

        data_dir = get_data_directory()
        self._sysinfo_lines: list[str] = [
            f"Python:     {sys.version.split()[0]}",
            f"PySide6:    {PySide6.__version__}",
            f"Platform:   {sys.platform}",
            f"Database:   {data_dir / 'grouper.db'}",
            f"Config:     {data_dir / 'config.json'}",
        ]

        for line in self._sysinfo_lines:
            group_lay.addWidget(_label(line, "mutedLabel"))

        copy_btn = QPushButton("Copy to Clipboard")
        copy_btn.clicked.connect(self._copy_sysinfo)
        group_lay.addWidget(copy_btn)

        lay.addWidget(group)
        return card

    def _copy_sysinfo(self) -> None:
        clipboard: QClipboard = QApplication.clipboard()
        clipboard.setText("\n".join(self._sysinfo_lines))
