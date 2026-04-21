"""Test that ElidedLabel and _TaskboxCard actually elide text when constrained."""

from grouper.models import Project
from grouper.ui.dashboard import _TaskboxCard
from grouper.ui.widgets import ElidedLabel
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget


def test_elided_label_standalone(qapp: QApplication) -> None:
    """ElidedLabel should elide when resized narrower than its text."""
    lbl = ElidedLabel()
    lbl.setFullText("This is a very long project name that should definitely get truncated")
    lbl.show()

    # Force a wide size first — text should be full
    lbl.setFixedWidth(800)
    qapp.processEvents()
    wide_text = lbl.text()

    # Force a narrow size — text should be truncated
    lbl.setFixedWidth(80)
    qapp.processEvents()
    narrow_text = lbl.text()

    lbl.close()

    assert narrow_text.endswith(" . . ."), f"Expected ellipsis, got: {narrow_text!r}"
    assert len(narrow_text) < len(wide_text), "Narrow text should be shorter"


def test_taskbox_card_in_constrained_parent(qapp: QApplication) -> None:
    """_TaskboxCard inside a fixed-width parent — labels should elide."""
    projects = [
        Project(id=i, board_id=1, name=f"Very Long Project Name Number {i} That Should Truncate")
        for i in range(3)
    ]

    parent = QWidget()
    layout = QVBoxLayout(parent)
    card = _TaskboxCard()
    layout.addWidget(card)

    # Give parent a generous width first
    parent.resize(800, 400)
    parent.show()
    card.populate(projects, [])
    qapp.processEvents()

    # Now constrain to narrow
    parent.resize(200, 400)
    qapp.processEvents()

    narrow_texts = []
    for i in range(card._proj_layout.count()):
        w = card._proj_layout.itemAt(i).widget()
        if w and hasattr(w, "text"):
            narrow_texts.append(w.text())

    parent.close()

    assert any(". . ." in t for t in narrow_texts), (
        f"Expected at least one label to elide, got: {narrow_texts}"
    )
