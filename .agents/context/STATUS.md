# GROUPER STATUS

## Current State

- Core desktop app, CLI, server, and Windows installer are implemented and working.
- Four release variants exist: `core`, `core_cli`, `core_server`, `core_cli_server`.
- Installer supports machine-wide install, elevation, PATH updates, manifest persistence, ARP registration, upgrade detection, and uninstall.
- About page uses GitHub links and GitHub Releases for version checks.
- DRM / activation code has been removed.

## Recent High-Value Changes

- Fixed Nuitka entry-point import issues by using absolute imports in app entry points.
- Added robust installer support modules: `dist_meta`, `path_env`, `elevation`, `manifest`, and `registry`.
- Completed uninstall flow including installer self-cleanup handling.
- Improved task-board dragging behavior and covered it with widget tests.

## Verification Snapshot

- Unit and widget coverage was expanded substantially around installer behavior.
- Prior verification on recent work was clean for `pytest`, `ruff`, and most `ty` checks, with only previously-known type noise noted at the time.
