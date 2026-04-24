# Fix plan: Black-theme Add Group dialog appears transparent

## Goal

Fix the time tracker "Edit Activities" -> "+ Add Group" dialog so it is clearly visible on the `black` theme, confirm that the fix is safe for other themes, and add regression coverage.

## Current understanding

### User-visible bug

- In the time tracker, opening `Edit Activities`, selecting an activity, and clicking `+ Add Group` opens `AddGroupDialog`.
- On the `black` theme the dialog appears transparent / visually disappears into the underlying editor.

### Confirmed code path

- `grouper/ui/time_tracker.py`
  - `TimeTrackerView._edit_activities()` opens the full-width `ActivityConfigPanel`.
- `grouper/ui/activity_config.py`
  - `_ActivityDetailEditor._add_group()` constructs `AddGroupDialog(all_groups, self._activity.groups, self)` and runs `dlg.exec()`.
- `grouper/ui/dialogs.py`
  - `AddGroupDialog` inherits `FramelessDialog`.
  - `FramelessDialog` always sets:
    - `Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog`
    - `Qt.WidgetAttribute.WA_TranslucentBackground`
  - The dialog shell is a `QFrame` named `dialogFrame` with child `dialogContent`.
- `grouper/styles/_base.qss`
  - Global `QWidget` background uses `{{bg-primary}}`.
  - `#dialogFrame` background also uses `{{bg-primary}}`.
  - `#dialogContent` background also uses `{{bg-primary}}`.
  - `#dialogTitleBar` uses `{{bg-secondary}}`.
- `grouper_core/colors.py`
  - `black` theme uses very compressed shell colors:
    - `bg-primary = #0a0a0a`
    - `bg-secondary = #141414`
    - `border = #2a2a2a`

### Cause confirmed from investigation

- This is not true alpha transparency inside the dialog widget itself.
  - Offscreen `dlg.grab()` renders opaque pixels (`alpha=255`) for `dark`, `light`, `black`, and the other shipped themes.
  - Native screen capture also showed opaque black-theme dialog pixels.
- The bug is a visual contrast failure in the shared frameless dialog treatment:
  - the page background and dialog content both use `bg-primary`, so the dialog body has no surface separation from the parent UI;
  - the only remaining delineation is the title bar and thin border;
  - the `black` palette makes `bg-primary`, `bg-secondary`, and `border` too similar, so the shell reads as transparent against the activity editor.
- `WA_TranslucentBackground` is part of the shared dialog base and may make this class of issue more noticeable, but the direct root cause in the current code is that the dialog surface is styled with the same base color token as the page behind it.

### Other-theme assessment

- The structural issue exists in all themes because `QWidget`, `#dialogFrame`, and `#dialogContent` all resolve to the same `bg-primary` token.
- The problem is most visible on `black` because that palette has the weakest dialog-shell separation.
- `oxygen` is the closest secondary-risk theme because its shell contrast is also low.
- `dark`, `light`, `sage`, `sodium`, `argon`, and `cathode` still render opaque and are more visually distinguishable, so they are not currently presenting the same user-visible severity.

## Constraints

- Keep the fix minimal and centralized. `AddGroupDialog` should not get a one-off styling hack if the real issue is in the shared dialog shell.
- Do not regress other dialogs that inherit `FramelessDialog` (`CreateActivityDialog`, `CreateProjectDialog`, `StopSessionDialog`, `ConfirmDialog`, etc.).
- Preserve the existing frameless-dialog interaction model unless verification shows a compositor issue that requires deeper changes.
- Keep theme behavior explicit in palette/QSS rather than ad hoc per-dialog `setStyleSheet()` calls.

## Intended approach

Make the shared frameless dialog shell visually distinct from ordinary page widgets, with theme-controlled dialog surface tokens rather than reusing the app-wide `bg-primary` page background. Then add widget-level rendering regression tests that would fail if the dialog body again collapses into the host page on low-contrast themes.

## Implementation steps

### Phase 1: Add regression coverage first

1. Create a new widget test file, preferably `tests/widget/test_dialog_rendering.py`.
2. Add a helper that:
   - ensures a `QApplication` exists via the existing widget-test fixture;
   - calls `grouper.styles.load_theme(app, theme_name)`;
   - creates a plain host `QWidget` using the app stylesheet;
   - creates and shows `AddGroupDialog` on top of that host;
   - processes events and captures rendered pixels with `dlg.grab().toImage()`.
3. Add a regression test for `black` that proves the dialog shell is visually distinct from the host page.
   - Sample a pixel from the dialog content area.
   - Sample a pixel from a plain host widget area rendered with the same theme.
   - Assert the two colors are not equal after the fix.
   - Keep the sample points away from borders/text so the test is stable.
4. Add a broader safety test over representative themes, at minimum `dark`, `light`, `black`, and `oxygen`.
   - Assert dialog content pixels are opaque.
   - Assert the dialog shell remains visually distinct from the page background in every covered theme.
5. If the rendering test is flaky, fall back to asserting the effective palette/style outcome at the `dialogFrame`/`dialogContent` widgets, but prefer pixel-based coverage because this bug is visual.

Verification for Phase 1:

- Run `uv run pytest tests/widget/test_dialog_rendering.py` and confirm the new black-theme regression fails before the styling fix, then passes after it.

### Phase 2: Introduce dialog-specific theme tokens

1. Update `grouper_core/colors.py` to add dedicated dialog surface tokens for every theme.
   - Add tokens such as:
     - `dialog-bg`
     - `dialog-content-bg`
     - `dialog-title-bg`
     - `dialog-border`
   - Use explicit values for each theme rather than aliasing implicitly in QSS.
2. Choose values so dialogs read as elevated surfaces.
   - For `black`, make the dialog body materially lighter than `bg-primary` while staying consistent with the palette.
   - Make `dialog-border` stronger than the current page border if needed.
   - Keep title-bar contrast consistent with the body.
3. Audit all themes so the new dialog tokens are sensible and do not over-brighten light themes or crush dark themes.

Verification for Phase 2:

- Run `uv run pytest tests/widget/test_theme_validation.py`.
- If that file does not validate the new tokens, extend it or add a nearby test that asserts every theme provides the full dialog token set.

### Phase 3: Re-style the shared frameless dialog shell

1. Update `grouper/styles/_base.qss` so dialog shell widgets use the new dialog tokens.
   - Change `#dialogFrame` to use `{{dialog-bg}}` and `{{dialog-border}}`.
   - Change `#dialogContent` to use `{{dialog-content-bg}}`.
   - Change `#dialogTitleBar` to use `{{dialog-title-bg}}`.
2. Keep the styling change shared and centralized.
   - Do not special-case `AddGroupDialog` unless a follow-up issue is discovered.
3. Re-check whether the current border radius, border width, and shadow are enough once the dialog body is no longer identical to the page.
   - If still too subtle on `black`, strengthen the border or increase shadow contrast in QSS or in `FramelessDialog`'s `QGraphicsDropShadowEffect`.
4. Avoid introducing theme-specific `setStyleSheet()` calls in `grouper/ui/dialogs.py`.

Verification for Phase 3:

- Re-run `uv run pytest tests/widget/test_dialog_rendering.py`.
- Manually launch the app and verify the exact user flow on `black`:
  1. `uv run grouper`
  2. switch to `Black` theme
  3. open `Time Tracker`
  4. click `Edit Activities`
  5. select an activity
  6. click `+ Add Group`
  7. confirm the dialog reads as a distinct, opaque modal surface

### Phase 4: Validate other frameless dialogs and theme safety

1. Manually spot-check at least these dialogs because they share `FramelessDialog`:
   - `CreateActivityDialog`
   - `StopSessionDialog`
   - `ConfirmDialog`
2. Verify the same dialogs on at least these themes:
   - `black`
   - `dark`
   - `light`
   - `oxygen`
3. Confirm there is no regression in input readability, border visibility, or title-bar contrast.

Verification for Phase 4:

- Run the most relevant widget suite after the styling change:
  - `uv run pytest tests/widget`

### Phase 5: Final quality checks and project context updates

1. Run repository checks required for modified files:
   - `uv run ruff check .`
   - `uv run ty check`
2. If any unrelated lint/type issue is surfaced by the touched files or test additions, fix it before considering the work complete.
3. Update project context docs after the fix is verified:
   - `A:\nudev\grouper\.agents\context\STATUS.md`
   - `A:\nudev\grouper\.agents\context\NOTES.md`
   - record the dialog-contrast fix and the new test coverage.

## Risks and decisions

- Risk: changing shared dialog tokens affects every frameless dialog.
  - Mitigation: keep the change surface-specific, verify the shared dialogs listed above, and add rendering tests.
- Risk: if the real issue later proves to be a Windows layered-window compositor quirk, color-only changes may improve perception without eliminating the underlying platform fragility.
  - Mitigation: after the shared styling fix, manually confirm native behavior on Windows before closing the issue. Only if a transparency artifact remains should a second pass evaluate `WA_TranslucentBackground` / shadow implementation in `FramelessDialog`.
- Decision: do not patch only `AddGroupDialog`.
  - Reason: the bug is produced by the shared `FramelessDialog` + global dialog QSS treatment.

## Expected end state

- The `+ Add Group` dialog in the time tracker activity editor is clearly visible on the `black` theme.
- The dialog is still opaque and visually correct on representative other themes.
- Shared frameless dialogs have explicit elevated-surface styling instead of blending into page backgrounds.
- Widget regression coverage protects against this exact visual failure recurring.
