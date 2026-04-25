# Repo Map

## Top Level

- `grouper_core/`: shared models, config, and database logic
- `grouper/`: desktop GUI
- `grouper_cli/`: CLI entrypoints and commands
- `grouper_server/`: sync server and web dashboard
- `grouper_install/`: Windows installer and release-bundle metadata
- `tests/`: unit, widget, CLI, integration, and e2e coverage
- `scripts/`: build and release batch scripts
- `userdocs/`: user-facing docs

## Key Entry Points

- `grouper/main.py`: desktop startup
- `grouper/app.py`: main window
- `grouper/config.py`: desktop compatibility re-export of `grouper_core.config`
- `grouper_core/config.py`: shared config paths and `ConfigManager`
- `grouper_core/database/connection.py`: database path initialization and `db_path.txt` persistence
- `grouper_cli/__main__.py`: CLI entry
- `grouper_server/__main__.py`: server entry
- `grouper_install/setup.py`: installer UI and install/uninstall flow
- `grouper/ui/dialogs.py`: shared frameless dialogs and dialog base behavior
- `grouper/ui/activity_config.py`: activity editor flow that launches `AddGroupDialog`
- `grouper/ui/summary.py`: Summary tab stats and `MiniBarTrend` daily trend chart
- `grouper/ui/animated_stack.py`: page and inner-panel slide transitions
- `grouper/ui/animated_card.py`: session card expand/collapse and pause/resume slide helpers
- `grouper/ui/task_board.py`: task card expand/collapse and board/task-panel transitions
- `grouper/ui/splash.py`: startup splash/spinner animation
- `grouper/ui/activity_week.py`: dashboard activity-week grid and active-session pulse

## Installer Modules

- `grouper_install/dist_meta.py`: parse and validate `dist.toml`
- `grouper_install/path_env.py`: machine PATH updates
- `grouper_install/elevation.py`: UAC helpers
- `grouper_install/manifest.py`: install manifest persistence
- `grouper_install/registry.py`: ARP uninstall registration

## Test Infrastructure

- `tests/conftest.py`: root autouse fixture isolating both DB and config paths per test
- `tests/unit/`: fast logic tests
- `tests/widget/`: Qt widget tests
- `tests/cli/`: CLI tests
- `tests/integration/`: cross-module tests
- `tests/unit/test_test_isolation.py`: regression tests proving sandboxing stays intact
- `tests/unit/sync/test_sync_entrypoint_import.py`: sync entrypoint import purity checks
- `tests/widget/test_animated_stack.py`: slide transition behavior
- `tests/widget/test_activity_week.py`: activity-week layout and pulse behavior
- `tests/widget/test_task_board_drag.py`: task card interactions and board drag/drop behavior

## Dialog / Theme Hotspots

- `grouper/styles/_base.qss`: shared widget and dialog QSS
- `grouper_core/colors.py`: theme palettes and dialog surface tokens
- `tests/widget/test_transparency.py`: dialog contrast regressions, including parented dialog checks
- `tests/widget/test_theme_validation.py`: token coverage for dialog surface palette entries
- `tests/widget/test_dialogs.py`: construction tests for all `FramelessDialog` subclasses
- `tests/widget/test_summary_stats.py`: Summary calculations and trend-bar theme-switch regressions
- `tests/widget/test_activity_config.py`: rename persistence via `editingFinished` signal
- `.agents/context/qt-pitfalls.md`: lessons learned from the dialog contrast investigation
