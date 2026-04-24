# Handoff: Black Theme Dialog Border Contrast

## Goal

Finish the black-theme `AddGroupDialog` visual fix. The draft fix restores standard black dialog theming and removes the bad blocky list rows from `example-2.png`, but the live view still has a remaining issue: borders around the parent card/dialog card area can read black or insufficiently distinct.

## Current Status

- Branch: `fix/dialogs`
- Latest relevant commit: `558f9e2 fix dialog surface theming`
- Draft fix is committed.
- Top-level frameless dialog translucency remains disabled; do not reintroduce `WA_TranslucentBackground` for these dialogs.
- Black dialog tokens now intentionally map to standard black theme surfaces:
  - `dialog-bg`: `#0a0a0a`
  - `dialog-content-bg`: `#0a0a0a`
  - `dialog-title-bg`: `#141414`
  - `dialog-border`: `#2a2a2a`
- Dialog list rows no longer use the solid oversized `dialog-bg` item override that caused the rough `example-2.png` look.
- Dialog-scoped selectors now protect parented dialogs from `#card QWidget { background-color: transparent; }` bleed-through.

## Files Changed

- `.agents/context/STATUS.md`: records draft fix and remaining border issue.
- `.agents/context/NOTES.md`: records black-theme dialog decisions and parent-card selector pitfall.
- `.agents/context/MAP.md`: adds theme validation test location.
- `grouper/ui/dialogs.py`: frameless dialogs no longer use top-level translucency; key internal surfaces use `WA_StyledBackground`.
- `grouper/styles/_base.qss`: dialog token usage, standard list surface rules inside dialogs, and parent-card dialog specificity overrides.
- `grouper_core/colors.py`: adds `dialog-*` tokens for all themes, with black restored to standard black surfaces.
- `tests/widget/test_dialogs.py`: frameless dialog construction and translucency regression coverage.
- `tests/widget/test_theme_load.py`: QSS/theme loading coverage.
- `tests/widget/test_theme_validation.py`: dialog token coverage and unresolved-token checks.
- `tests/widget/test_transparency.py`: live screen-sampled dialog opacity/contrast regressions including parented `AddGroupDialog` checks.
- `tests/widget/conftest.py`: adds `main_window` fixture needed by theme-load tests.

## Remaining Issue

The black-theme dialog is no longer using the bad `example-2.png` row styling, but the live screenshot still needs border refinement. Specifically, the parent card/dialog card perimeter can appear black or too low contrast against surrounding black-theme surfaces.

This should be addressed as a separate visual pass. Avoid solving it by making the whole dialog gray or by bringing back solid block list rows.

## Important Decisions

- Standard black theme surfaces are required for `AddGroupDialog`; do not make black dialog body/list rows visibly gray just to pass contrast checks.
- The correct regression target is the live parented dialog hierarchy, not only `widget.grab()` snapshots.
- `#card QWidget { background-color: transparent; }` can override dialog descendants when dialogs are parented inside activity editor cards. Use sufficiently specific dialog selectors when needed.
- Top-level dialog translucency produced misleading offscreen results and should remain disabled.

## Immediate Next Steps

1. Open the app in black theme and reproduce `AddGroupDialog` from the activity editor.
2. Compare the current live result against `example-2.png` and any newer screenshot (`example-3.png` is present but uncommitted).
3. Focus only on the card/dialog border area that still reads black or insufficiently distinct.
4. Prefer a minimal QSS/token adjustment to `dialog-border`, parent-card border specificity, or targeted dialog frame/card selectors.
5. Do not alter the standard black dialog body/list surfaces unless the user explicitly changes the requirement.
6. Add or adjust a focused widget test only if it can reliably sample the affected border area in the exact parented dialog flow.

## Verification To Run

```bash
uv run pytest tests/widget/test_transparency.py tests/widget/test_theme_validation.py tests/widget/test_theme_load.py tests/widget/test_dialogs.py
uv run ruff check .
```

Full `uv run pytest` was attempted and reached 99% with all printed tests passing but hit tool timeout; the final transparency cases were run separately and passed.

## Worktree Notes

After commit `558f9e2`, unrelated pre-existing worktree changes remain unstaged/untracked, including e2e test removals, `pyproject.toml`, `uv.lock`, some `.agents/plans/*`, screenshots, and unrelated widget tests. Do not revert or include those unless the next task explicitly calls for them.
