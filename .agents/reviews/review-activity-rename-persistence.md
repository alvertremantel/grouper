# Review: Fix activity rename not persisting on focus loss

**Date:** Thu Apr 23 2026
**Scope:** `grouper/ui/activity_config.py`, `tests/widget/test_activity_config.py`, and context updates (105 lines diff)
**Test results:** PASS (via `uv run pytest tests/widget/test_activity_config.py` and manually constructed test cases)

---

## Summary

The change correctly addresses the reported bug by substituting `returnPressed` with `editingFinished`, ensuring activity renames persist when the field loses focus. The logic is sound and the new tests correctly verify the behavior. However, the implementation leaves the UI in a broken visual state if the user provides an empty name, and the identical issue in `_GroupSection` remains unfixed despite being explicitly noted. The change requires modification before approval.

## Critical Issues

Issues that must be fixed before the change is acceptable.

#### 1. Blank names break visual state
- **Location:** `grouper/ui/activity_config.py:623` (`_rename_activity`)
- **Problem:** If a user deletes the text to make it blank and clicks away, the database is correctly protected against the invalid name (the save is skipped). However, the line edit text is never reverted. The UI continues to show a blank name, giving the false impression that the name was cleared, until the next UI reload.
- **Fix:** Add an `else` block to revert the text back to the actual activity name if the rename is skipped.

```python
    def _rename_activity(self) -> None:
        if self._activity is None:
            return
        new_name = self._name_input.text().strip()
        if new_name and new_name != self._activity.name:
            rename_activity_by_id(self._activity.id, new_name)  # type: ignore[arg-type]
            self._activity.name = new_name
            self.data_changed.emit()
        else:
            self._name_input.setText(self._activity.name)
        self._name_input.clearFocus()
```

#### 2. `_GroupSection` focus-loss persistence bug is identical and unresolved
- **Location:** `grouper/ui/activity_config.py:281` (`_GroupSection._build`)
- **Problem:** The author noted this in `STATUS.md` and explicitly bypassed it. However, the bug in `_GroupSection` is actually more severe: because it relies *only* on `returnPressed`, if a user double-clicks to rename a group and then clicks away, the `QLineEdit` becomes permanently stuck open since `_commit_rename` is never called to hide it.
- **Fix:** Replace `returnPressed` with `editingFinished` for `_GroupSection` as well, solving both the persistence issue and the stuck-input bug.

```python
        self._name_input = QLineEdit(self._group.name)
        self._name_input.setObjectName("transparentInput")
        self._name_input.editingFinished.connect(self._commit_rename)
        self._name_input.hide()
```

## Suggestions

Improvements that should be strongly considered but are not blocking.

#### 1. Update `test_empty_rename_does_not_emit` to assert visual state
- **Location:** `tests/widget/test_activity_config.py:68`
- **Problem:** The test verifies that `data_changed` does not fire, but it should also verify that the UI corrects itself.
- **Fix:** Add `assert editor._name_input.text() == "Real Name"` at the end of the test.

## Observations

Notes that are informational — not problems, but worth recording.

#### 1. Double-execution safety
- **Location:** `grouper/ui/activity_config.py:623`
- **Note:** `editingFinished` is naturally fired twice on an Enter press followed by an immediate focus loss. The guard `if new_name and new_name != self._activity.name` successfully prevents duplicate database calls or signal emissions.

## Test Coverage

- **Existing tests:** Pass.
- **Missing tests:** A test asserting that invalid renames result in the `QLineEdit` text being reverted.
- **Weakened tests:** None.

## Checklist

- [x] Correctness — reviewed
- [x] Code quality (DRY/YAGNI) — reviewed
- [x] Extensibility — reviewed
- [x] Security — reviewed
- [x] Stability — reviewed
- [x] Resource utilization — reviewed
- [x] Tests — run and reviewed

## Verdict

**REQUEST CHANGES**

The primary bug was correctly identified and solved, but the implementation lacks proper UI cleanup on invalid inputs. Additionally, an identical and more severe instantiation of the exact same bug within the same file was explicitly skipped; it should be fixed in this pass to avoid technical debt and degraded UX.