# Fix: Activity Rename Not Persisting

## Problem

When a user renames an activity in the "Edit Activities" view (timer tab), the new name does not persist into the rest of the application and is not displayed on reload. The rename is effectively lost.

## Root Cause

In `grouper/ui/activity_config.py`, the `_ActivityDetailEditor._rename_activity` method is connected **only** to `QLineEdit.returnPressed` (line 442):

```python
self._name_input.returnPressed.connect(self._rename_activity)
```

`returnPressed` fires **only** when the user presses Enter/Return. There is no connection to `editingFinished`, which also fires when the line edit loses focus (clicking elsewhere, tabbing away, closing the panel).

Consequences:
- User types a new name, clicks another activity → rename lost
- User types a new name, clicks "Back to Time Tracker" → rename lost
- User types a new name, clicks anywhere outside the field → rename lost
- Only pressing Enter actually saves the rename to the database

The database function `rename_activity_by_id` in `grouper_core/database/activities.py:208` works correctly — it just never gets called.

## Fix

Replace the `returnPressed` signal connection with `editingFinished` in `_ActivityDetailEditor._build()`. `editingFinished` fires on both Enter press and focus loss, covering all user workflows.

### Step 1: Change signal connection in `_ActivityDetailEditor._build()`

**File:** `grouper/ui/activity_config.py`
**Location:** Line 442 in `_build()` method of `_ActivityDetailEditor`

**Current:**
```python
self._name_input.returnPressed.connect(self._rename_activity)
```

**New:**
```python
self._name_input.editingFinished.connect(self._rename_activity)
```

That's it. The `_rename_activity` method already guards against no-op renames with `if new_name and new_name != self._activity.name`, so duplicate calls from both Enter and focus-loss are harmless (the second call is a no-op).

### Step 2: Verify with existing tests

Run the full test suite to confirm no regressions:

```bash
uv run pytest tests/ -x -q
uv run ruff check .
```

### Step 3: Add a targeted widget test

**File:** `tests/widget/test_activity_config.py` (new file or append to existing if one exists)

Write a test that:
1. Creates an `ActivityConfigPanel` with a test database
2. Creates an activity and selects it (loading into the detail editor)
3. Changes the name in the `_name_input` field
4. Emits `editingFinished` on the name input (simulating focus loss)
5. Verifies the activity name was updated in the database via `get_activity_by_id`
6. Verifies the `data_changed` signal was emitted

This test should **not** require pressing Enter — it should prove that focus-loss alone triggers the save.

## Risks and Considerations

- **Double-fire on Enter:** When the user presses Enter, Qt fires both `returnPressed` and `editingFinished`. Since we're replacing (not adding) the connection, only `editingFinished` fires, so there's no double-fire.
- **Group browser click timing:** When the user clicks an activity in the group browser, the name input loses focus → `editingFinished` fires → `_rename_activity` → `data_changed` → `_on_detail_changed` → `_rebuild_group_browser()`. This rebuilds the left panel while the user's click target might be destroyed. In practice, Qt processes the focus-out synchronously before the click completes, and `QPushButton.clicked` fires on mouse release. The button widget may be destroyed before release. However, this is already the case for the `returnPressed` path (which also triggers `_rebuild_group_browser` via `data_changed`), and no issues have been reported. If this becomes a problem, a future fix could debounce the rebuild or defer it.
- **Group rename in `_GroupSection`:** The group rename in `_GroupSection` (line 281) also uses `returnPressed`. This has the same bug but is out of scope for this plan — file a follow-up if needed.

## Files Changed

| File | Change |
|------|--------|
| `grouper/ui/activity_config.py` | Change `returnPressed` → `editingFinished` on line 442 |
| `tests/widget/test_activity_config.py` | New test for focus-loss rename persistence (if file doesn't exist, create it) |
