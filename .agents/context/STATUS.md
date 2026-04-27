# GROUPER STATUS

## Current State

- Desktop package has been renamed from `grouper/` to `desktop/`; CLI/server/core package names remain unchanged.
- `desktop/ui/` is now domain-organized into `shared/`, `time/`, `tasks/`, `calendar/`, and `views/`.
- Shared Qt foundations now live in `desktop/ui/shared/base_card.py` and `desktop/ui/shared/base_dialog.py`.
- Tests and package metadata use `desktop.*` imports; the installed GUI command is still `grouper` and points at `desktop.main:main`.
- Context plan for this refactor is in `.agents/plans/refactor-grouper-desktop-maintainability.md`.

## Recent Changes

- Added `BaseCard` for card object names, standard row layout helpers, `WA_StyledBackground`, and drag child passthrough.
- Moved `FramelessDialog` to `shared/base_dialog.py`, added `BaseFormDialog`, centralized dialog background/styled-surface handling, and retained re-export compatibility from `desktop.ui.tasks.dialogs`.
- Added generic QSS error-state styling and `QLabel#errorLabel` styling.
- Added launch compatibility for `python -m desktop`, `python desktop/__main__.py`, `python desktop/main.py`, and the installed `grouper.exe` GUI wrapper.
- Suppressed expected PySide disconnect warnings in the shared `reconnect()` helper.

## Active Work

- Refactor implementation is complete; no active blockers.
- Immediate next step is review/QA of the large rename + UI restructure before release packaging.

## Verification

- Full suite: `python -m pytest tests/ -q --tb=short` → `799 passed`.
- Lint: `ruff check desktop tests` → clean.
- Launch smoke checks stayed alive for 8s under offscreen Qt: `python -m desktop`, `python desktop\__main__.py`, `python desktop\main.py`, installed `grouper.exe`.
- Entry point metadata resolves `grouper` GUI script to `desktop.main:main`.
