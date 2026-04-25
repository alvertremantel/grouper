# Review: Dialog contrast fix, theme token expansion, and E2E-to-widget test migration

**Date:** 2026-04-23
**Scope:** `fix/dialogs` vs `latest` — 24 files, ~1,800 insertions, ~660 deletions
**Test results:** `tests/widget/` targeted suite: 77/77 passed; `ruff check .` passed; `ty check` shows only pre-existing diagnostics unrelated to this change.

---

## Summary

This branch removes top-level frameless-dialog translucency (the root cause of black-theme dialog blending), introduces explicit dialog-surface theme tokens, restores painted dialog surfaces via `WA_StyledBackground`, and replaces fragile E2E tests with faster, deterministic widget tests. The approach is well-justified by the project’s own `.agents/context/qt-pitfalls.md` postmortem. All new widget tests pass and the linter is clean. **APPROVE with minor suggestions.**

---

## Critical Issues

None.

---

## Suggestions

#### 1. `EditTaskDialog` silently skips prerequisite chips when `pt.id` is `None`
- **Location:** `grouper/ui/dialogs.py:680`
- **Problem:** The defensive `if pt.id is None: continue` prevents a crash but gives the user no indication that a prerequisite task is missing its id. If this condition is reachable, it may indicate a data-integrity issue that should be visible.
- **Fix:** Either assert that `pt.id` is non-None (if the DB layer guarantees it), or log a warning so the failure mode is observable during development:
  ```python
  if pt.id is None:
      import logging
      logging.getLogger(__name__).warning(
          "Prerequisite task %r has no id; skipping chip", pt.title
      )
      continue
  ```

#### 2. Screen-pixel tests can flake under occlusion or unusual display geometry
- **Location:** `tests/widget/test_transparency.py` (multiple methods)
- **Problem:** Tests such as `test_dialog_content_is_opaque_on_screen` and `test_parented_dialog_border_differs_from_host_card` sample actual screen pixels via `QScreen.grabWindow(0, ...)`. If another window overlaps the test widget, or if the display scale/geometry places the dialog partially off-screen, the sampled color will be wrong and the test will fail non-deterministically.
- **Fix:** Add a guard at the top of the module or in a fixture that asserts the test window is fully on-screen and active. As a lightweight mitigation, the existing `move(0, 0)` and `move(100, 100)` calls are reasonable; document the assumption:
  ```python
  def _assert_on_screen(widget: QWidget) -> None:
      screen = widget.screen()
      assert screen is not None
      assert screen.geometry().contains(widget.frameGeometry()), (
          "Test widget must be fully on-screen for pixel sampling"
      )
  ```
  Call this inside `themed_dialog` and the `AddGroupDialog` tests before sampling.

#### 3. `main_window` fixture may miss config patches in views that import config independently
- **Location:** `tests/widget/conftest.py:34-38`
- **Problem:** The fixture patches `grouper.app.get_config`, `grouper.app.theme_colors`, `grouper.ui.sidebar.get_config`, and `grouper.ui.animated_stack.get_config`. If `MainWindow` or any view it instantiates imports `get_config` from another module (e.g., `grouper.ui.views.get_config`), the real config will be used, which may touch the user database.
- **Fix:** Patch at the source module (`grouper_core.config.get_config`) or add a fallback that patches the most common additional import paths. Since the tests currently pass, this is only a future-maintenance concern.

#### 4. QSS duplication under `#card` increases maintenance burden
- **Location:** `grouper/styles/_base.qss:196-229`
- **Problem:** The `#card #dialogFrame`, `#card #dialogTitleBar`, `#card #dialogContent`, and list selectors duplicate the top-level dialog selectors almost exactly. If a border-radius or padding changes in the future, both blocks must be updated.
- **Fix:** Consider using Qt stylesheet grouping to reduce duplication, e.g.:
  ```qss
  #dialogFrame, #card #dialogFrame {
      background-color: {{dialog-bg}};
      border: 1px solid {{dialog-border}};
      border-radius: 10px;
  }
  ```
  The current explicit duplication is defensible for specificity debugging, but a comment explaining why the two blocks must stay in sync would help future editors.

---

## Observations

#### 1. Removal of E2E tests is clean but narrows the real-app validation surface
- **Location:** `tests/e2e/` (deleted), `pyproject.toml`
- **Note:** The E2E suite (pywinauto-based) and its dependencies (`pywinauto`, `psutil`, `mss`) are fully removed. The new widget tests cover construction, navigation, and theme loading, but they do not exercise the full subprocess lifecycle (UAC, PATH updates, actual window manager interactions). This is an intentional trade-off for speed and reliability, but the project should monitor whether any regressions slip through that only appear in a real Windows desktop session.

#### 2. `WA_StyledBackground` is the correct replacement for `WA_TranslucentBackground`
- **Location:** `grouper/ui/dialogs.py:78, 95, 100`
- **Note:** The removal of `WA_TranslucentBackground` and the addition of `WA_StyledBackground` on the container, title bar, and content widgets aligns exactly with the Qt pitfall documentation. The screen-pixel tests confirm that on-screen alpha is 255 for all themes.

#### 3. Dialog surface tokens are consistent with existing palette conventions
- **Location:** `grouper_core/colors.py:652-704`
- **Note:** `_DIALOG_SURFACE_TOKENS` is merged into `_THEME_PALETTE` at module load time. The black theme intentionally maps dialog surfaces back to standard black-theme values (`dialog-bg` == `bg-primary`, `dialog-title-bg` == `bg-secondary`, `dialog-border` == `border`), which satisfies the explicit regression test `test_black_dialog_uses_standard_black_theme_surfaces`.

#### 4. `test_theme_switch_preserves_window_visibility` is a good regression for a subtle Qt crash
- **Location:** `tests/widget/test_theme_load.py:37-46`
- **Note:** Reloading a stylesheet while a window is visible can trigger repainting edge cases in PySide6. This test directly exercises that path.

---

## Test Coverage

- **Existing tests:** All 77 targeted widget tests pass. `ruff check .` is clean. `ty check` reports only pre-existing diagnostics unrelated to this change.
- **Missing tests:** None critical. A future test could verify that `FramelessDialog` subclasses that add custom content still get opaque surfaces, but the existing parametrized construction test (`TestDialogSubclasses`) already touches every subclass.
- **Weakened tests:** The E2E tests are removed, which technically reduces coverage of real Windows shell interactions, but the removed tests were themselves flaky and slow. The replacement widget tests are more deterministic.

---

## Checklist

- [x] Correctness — reviewed
- [x] Code quality (DRY/YAGNI) — reviewed
- [x] Extensibility — reviewed
- [x] Security — reviewed (no new input surfaces)
- [x] Stability — reviewed
- [x] Resource utilization — reviewed
- [x] Tests — run and reviewed

## Verdict

**APPROVE**

The branch correctly addresses the dialog contrast bug by removing the problematic `WA_TranslucentBackground` attribute, adding explicit dialog surface tokens for every theme, and parenting-dialog-specific QSS selectors to prevent card-background transparency bleed-through. The expanded widget test suite replaces the removed E2E coverage with faster, deterministic assertions that match the actual user-visible rendering path. All linters and targeted tests pass. The four suggestions above are minor and non-blocking.
