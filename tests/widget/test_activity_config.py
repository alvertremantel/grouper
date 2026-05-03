"""Tests for activity_config widget — rename persistence on focus loss."""

from desktop.database.activities import create_activity, get_activity_by_id
from desktop.ui.time.activity_config import _ActivityDetailEditor
from PySide6.QtWidgets import QApplication


class TestActivityRenameOnEditingFinished:
    def test_editing_finished_persists_rename(self, qapp: QApplication) -> None:
        activity = create_activity("Original Name")
        assert activity.id is not None
        editor = _ActivityDetailEditor()
        editor.load(activity)
        editor.show()
        qapp.processEvents()

        editor._name_input.setText("Renamed Activity")
        editor._name_input.editingFinished.emit()

        refreshed = get_activity_by_id(activity.id)
        assert refreshed is not None
        assert refreshed.name == "Renamed Activity"

    def test_editing_finished_emits_data_changed(self, qapp: QApplication) -> None:
        activity = create_activity("Original")
        editor = _ActivityDetailEditor()

        signals: list[bool] = []
        editor.data_changed.connect(lambda: signals.append(True))

        editor.load(activity)
        editor.show()
        qapp.processEvents()

        editor._name_input.setText("Changed")
        editor._name_input.editingFinished.emit()

        assert signals, "data_changed should have been emitted"

    def test_noop_rename_does_not_emit(self, qapp: QApplication) -> None:
        activity = create_activity("Same Name")
        editor = _ActivityDetailEditor()

        signals: list[bool] = []
        editor.data_changed.connect(lambda: signals.append(True))

        editor.load(activity)
        editor.show()
        qapp.processEvents()

        editor._name_input.setText("Same Name")
        editor._name_input.editingFinished.emit()

        assert not signals, "data_changed should not fire for no-op rename"

    def test_empty_rename_does_not_emit(self, qapp: QApplication) -> None:
        activity = create_activity("Real Name")
        assert activity.id is not None
        editor = _ActivityDetailEditor()

        signals: list[bool] = []
        editor.data_changed.connect(lambda: signals.append(True))

        editor.load(activity)
        editor.show()
        qapp.processEvents()

        editor._name_input.setText("  ")
        editor._name_input.editingFinished.emit()

        assert not signals, "data_changed should not fire for blank rename"

        refreshed = get_activity_by_id(activity.id)
        assert refreshed is not None
        assert refreshed.name == "Real Name"
        assert editor._name_input.text() == "Real Name"


class TestGroupSectionRename:
    def test_group_section_editing_finished_persists_rename(self, qapp: QApplication) -> None:
        from desktop.database.activities import create_group, list_all_groups
        create_group("Original Group")
        group = next(g for g in list_all_groups() if g.name == "Original Group")

        from desktop.ui.time.activity_config import _GroupSection
        section = _GroupSection(group)
        section.show()
        qapp.processEvents()

        section._start_rename()
        assert not section._name_label.isVisible()
        assert section._name_input.isVisible()

        section._name_input.setText("Renamed Group")
        section._name_input.editingFinished.emit()

        assert not section._name_input.isVisible()
        assert section._name_label.isVisible()
        assert section._name_label.text() == "Renamed Group"

        refreshed = next(g for g in list_all_groups() if g.id == group.id)
        assert refreshed.name == "Renamed Group"

    def test_group_section_empty_rename_aborts(self, qapp: QApplication) -> None:
        from desktop.database.activities import create_group, list_all_groups
        create_group("Stable Group")
        group = next(g for g in list_all_groups() if g.name == "Stable Group")

        from desktop.ui.time.activity_config import _GroupSection
        section = _GroupSection(group)
        section.show()
        qapp.processEvents()

        section._start_rename()
        section._name_input.setText("   ")
        section._name_input.editingFinished.emit()

        assert not section._name_input.isVisible()
        assert section._name_label.isVisible()
        assert section._name_label.text() == "Stable Group"

        refreshed = next(g for g in list_all_groups() if g.id == group.id)
        assert refreshed.name == "Stable Group"
