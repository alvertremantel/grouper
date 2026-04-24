# Plan: Fix Activity and Group Rename Persistence

## Goal
Address the requested changes from the review `@.agents\reviews\review-activity-rename-persistence.md` regarding activity and group rename UI persistence and state.

## Current Understanding
1. In `grouper/ui/activity_config.py` `_ActivityDetailEditor._rename_activity` (line 623), if the user provides an empty name, the rename is correctly aborted, but the `QLineEdit` visually retains the empty string. It must be reverted to the original activity name.
2. In `grouper/ui/activity_config.py` `_GroupSection._build` (line 281), the inline group rename input relies on `returnPressed`. This causes a stuck-input bug if the user clicks away. It should be changed to use `editingFinished` to ensure the rename is committed (or aborted, closing the input) on focus loss.
3. Tests in `tests/widget/test_activity_config.py` need updates to verify these visual state corrections.

## Steps

### Step 1: Update `_ActivityDetailEditor._rename_activity`
- **File:** `grouper/ui/activity_config.py`
- **Action:** Modify `_rename_activity` (around line 623) to revert the input text if the new name is empty or identical to the current name.
- **Change:**
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
- **Verification:** Run `tests/widget/test_activity_config.py` after implementing the test update in Step 3.

### Step 2: Update `_GroupSection` to use `editingFinished`
- **File:** `grouper/ui/activity_config.py`
- **Action:** Modify `_GroupSection._build` (around line 281) to connect the `editingFinished` signal instead of `returnPressed`.
- **Change:**
  ```python
          self._name_input = QLineEdit(self._group.name)
          self._name_input.setObjectName("transparentInput")
          self._name_input.editingFinished.connect(self._commit_rename)
          self._name_input.hide()
  ```
- **Verification:** The inline group renaming should commit on focus loss and close the `QLineEdit` properly. 

### Step 3: Update and Add Tests
- **File:** `tests/widget/test_activity_config.py`
- **Action:**
  1. Add an assertion to `test_empty_rename_does_not_emit` to verify that `editor._name_input.text() == "Real Name"`.
  2. Add tests for `_GroupSection` `editingFinished` behavior (both valid rename and empty/invalid rename) asserting the `QLineEdit` gets hidden and the original label is restored. For example: `test_group_section_editing_finished_persists_rename`, `test_group_section_empty_rename_aborts`.
- **Verification:** Run `uv run pytest tests/widget/test_activity_config.py` and ensure all tests pass.

### Step 4: Verification and Context Updates
- **Action:** 
  1. Run the test suite using `uv run pytest`.
  2. Verify code quality using `uv run ruff check .`.
  3. Update `STATUS.md` to reflect that the bugs in activity rename and group rename persistence have been resolved.
  4. Optionally run manual verification if needed, but widget tests should suffice.
