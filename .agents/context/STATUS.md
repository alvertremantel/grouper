# GROUPER STATUS

## Current State

- App, CLI, server, and Windows installer all working. Four release variants: `core`, `core_cli`, `core_server`, `core_cli_server`.
- Installer: machine-wide install, elevation, PATH, manifest, ARP, upgrade detection, uninstall.
- Dialogs: no top-level translucency, `WA_StyledBackground` on container/title/content, dialog surface tokens per theme, `#card`-scoped QSS prevents bleed-through. See `.agents/context/qt-pitfalls.md`.
- Tests: widget tests (no pywinauto). Root autouse fixture sandboxes DB + config paths; no test writes to `~/.grouper/`. DB init only inside `main()`, not at import time.

## Recent Changes

- **Animation tuning**: shortened full-page slide, session-card, task-card expand/collapse, splash spinner, and activity-week pulse intervals to reduce repaint/layout pressure. `task_board.py` nullability issues fixed while touching animation code.
- **Summary bars**: recompute `MiniBarTrend` colors on `QEvent.PaletteChange` for theme switches.
- **Activity renames**: `editingFinished` signal (not `returnPressed`) for both `_ActivityDetailEditor` and `_GroupSection`; empty renames revert UI. Covered by `test_activity_config.py`.
- **Test isolation**: conftest patches `grouper_core.config`, re-exported `grouper.config`, and `ConfigManager._instance` **before** calling `_init_paths()` so `_save_data_directory()` always writes to the temp dir. `db_path.txt` routed through `APP_DIR`. Regression tests in `test_test_isolation.py` and `test_sync_entrypoint_import.py`.
- **Dialog QSS**: consolidated `#card` selectors into base rules; `EditTaskDialog` warns on missing prereq `id`.

## Active Work

- No active blockers. If animations still feel laggy, next step is snapshot-based page transitions or disabling sidebar page-slide animations for heavy views.
- Dialog translucency and blocky list-item styling must remain disabled.

## Verification

- Animation targeted checks clean: `ruff check` and `ty check` on touched UI files; widget tests `test_animated_stack.py`, `test_activity_week.py`, `test_main_window.py`, `test_task_board_drag.py`, and `test_dashboard_layout.py` passed (`62 passed`).
- Previous broad baseline: `ruff check .` clean; `pytest` 530/531 with one pre-existing `win32com` import failure.
