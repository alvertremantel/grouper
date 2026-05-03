"""
settings.py — Settings view for Grouper.
"""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QStandardItem
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...config import ConfigManager, get_config
from ...database.connection import backup_database, get_data_directory, get_notifier
from ...styles import THEME_GROUPS, load_theme
from ..shared.widgets import ThemedSpinBox


class SettingsView(QWidget):
    """Application settings panel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()
        self._dirty: bool = False
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(50)
        self._refresh_timer.timeout.connect(self._load_values)
        get_notifier().data_changed.connect(
            self._on_data_changed, Qt.ConnectionType.QueuedConnection
        )
        self._load_values()  # Initial load

    def _on_data_changed(self) -> None:
        if self.isVisible():
            if not self._refresh_timer.isActive():
                self._refresh_timer.start()
        else:
            self._dirty = True

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._dirty:
            self._dirty = False
            self._load_values()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(20)

        heading = QLabel("Settings")
        heading.setProperty("heading", True)
        outer.addWidget(heading)

        # -- Appearance group ------------------------------------------------
        appear = QGroupBox("Appearance")
        appear_lay = QFormLayout(appear)

        self._theme_combo = QComboBox()
        for group_label, themes in THEME_GROUPS:
            # Non-selectable group header
            self._theme_combo.addItem(f"— {group_label} —")
            header_idx = self._theme_combo.count() - 1
            header_item: QStandardItem = self._theme_combo.model().item(header_idx)
            header_item.setEnabled(False)
            # Theme items
            for t in themes:
                self._theme_combo.addItem(f"  {t.capitalize()}", t)
        self._theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        appear_lay.addRow("Theme:", self._theme_combo)

        self._animations_cb = QCheckBox("Enable animations")
        self._animations_cb.stateChanged.connect(self._on_animations_changed)
        appear_lay.addRow(self._animations_cb)

        outer.addWidget(appear)

        # -- Board group -----------------------------------------------------
        board = QGroupBox("Task Board")
        board_lay = QFormLayout(board)

        self._priority_spin = ThemedSpinBox()
        self._priority_spin.setRange(1, 5)
        self._priority_spin.valueChanged.connect(self._on_priority_changed)
        board_lay.addRow("Default priority:", self._priority_spin)

        outer.addWidget(board)

        # -- Time Tracker group ----------------------------------------------
        tracker = QGroupBox("Time Tracker")
        tracker_lay = QFormLayout(tracker)

        self._bg_notes_cb = QCheckBox("Enable notes for background activities")
        self._bg_notes_cb.stateChanged.connect(self._on_bg_notes_changed)
        tracker_lay.addRow(self._bg_notes_cb)

        outer.addWidget(tracker)

        # -- Data group ------------------------------------------------------
        data = QGroupBox("Data")
        data_lay = QFormLayout(data)

        self._data_dir_label = QLabel()
        self._data_dir_label.setObjectName("mutedLabel")
        data_lay.addRow("Database location:", self._data_dir_label)

        btn_row = QHBoxLayout()
        backup_btn = QPushButton("Create Backup")
        backup_btn.clicked.connect(self._backup)
        btn_row.addWidget(backup_btn)
        btn_row.addStretch()
        data_lay.addRow("", btn_row)

        outer.addWidget(data)
        outer.addStretch()

    # -- load / save ---------------------------------------------------------

    def _load_values(self) -> None:
        cfg = get_config()

        idx = self._theme_combo.findData(cfg.theme)
        if idx >= 0:
            self._theme_combo.blockSignals(True)
            self._theme_combo.setCurrentIndex(idx)
            self._theme_combo.blockSignals(False)

        self._priority_spin.blockSignals(True)
        self._priority_spin.setValue(cfg.default_priority)
        self._priority_spin.blockSignals(False)

        self._data_dir_label.setText(str(get_data_directory()))

        self._bg_notes_cb.blockSignals(True)
        self._bg_notes_cb.setChecked(cfg.bg_notes_enabled)
        self._bg_notes_cb.blockSignals(False)

        self._animations_cb.blockSignals(True)
        self._animations_cb.setChecked(cfg.animations_enabled)
        self._animations_cb.blockSignals(False)

    # -- handlers ------------------------------------------------------------

    def _on_theme_changed(self):
        theme = self._theme_combo.currentData()
        if theme:
            ConfigManager().update(theme=theme)
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
            if app:
                load_theme(app, theme)

    def _on_priority_changed(self, val):
        ConfigManager().update(default_priority=val)

    def _on_bg_notes_changed(self, state):
        ConfigManager().update(bg_notes_enabled=bool(state))

    def _on_animations_changed(self, state: int) -> None:
        ConfigManager().update(animations_enabled=bool(state))

    def _backup(self):
        if backup_database():
            self._data_dir_label.setText(f"{get_data_directory()}  ✓ Backup created")
