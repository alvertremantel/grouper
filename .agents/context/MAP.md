# Repo Map

## Top Level

- `desktop/`: PySide6 desktop GUI package; GUI script command remains `grouper`.
- `grouper_core/`: shared models, config, formatting, operations, DB, migrations, colors.
- `cli/`: CLI entry points and commands.
- `grouper_server/`: sync server and web dashboard.
- `installer/`: Windows installer and release-bundle metadata.
- `tests/`: unit, widget, CLI, integration, and e2e coverage.
- `scripts/`, `userdocs/`: build/release helpers and user-facing docs.

## Desktop Package

- `desktop/__main__.py`: supports `python -m desktop` and direct source-checkout script launch.
- `desktop/main.py`: desktop startup, DB init, web server, QApplication, splash, main window.
- `desktop/app.py`: `MainWindow`, title/sidebar/stack wiring, top-level view registration.
- `desktop/styles/`: QSS loader, theme tokens, desktop color re-exports.
- `desktop/database/`: desktop DB shims; `connection.py` adds the Qt data notifier.
- `desktop/config.py`, `models.py`, `operations.py`, `formatting.py`: re-export shims to `grouper_core`.

## Desktop UI Domains

- `desktop/ui/shared/`: base cards/dialogs, title bar, widgets, icons, animations, view models, splash.
- `desktop/ui/time/`: time tracker, activity config/card/week, session cards, time grid.
- `desktop/ui/tasks/`: task board/list/panel and task/project/board dialogs.
- `desktop/ui/calendar/`: calendar, agenda, event dialog, timeline.
- `desktop/ui/views/`: dashboard, history, summary, settings, about, sync, sidebar.

## Core / Server / Installer

- `grouper_core/config.py`: shared config paths and `ConfigManager`.
- `grouper_core/database/connection.py`: DB path initialization and `db_path.txt` persistence.
- `cli/main.py`: CLI app entry.
- `grouper_server/__main__.py`: server entry; `grouper_server/sync/` contains sync protocol helpers.
- `installer/setup.py`: installer UI and install/uninstall flow.
- `installer/{dist_meta,path_env,elevation,manifest,registry}.py`: installer support modules.

## Test / Theme Hotspots

- `tests/conftest.py`: root autouse fixture isolating DB and config paths per test.
- `tests/widget/test_transparency.py`: dialog/card opacity and parented-dialog regressions.
- `tests/widget/test_dialogs.py`: `FramelessDialog` subclasses.
- `tests/widget/test_task_board_drag.py`: task card interactions and drag/drop.
- `tests/widget/test_animated_stack.py`: page and panel transitions.
- `tests/unit/sync/test_sync_entrypoint_import.py`: sync entrypoint import purity.
- `.agents/context/qt-pitfalls.md`: Qt dialog/theme lessons learned.
