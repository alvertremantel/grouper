# GROUPER STATUS

Update this document frequently as development proceeds.

## 2026-04-20

- Implemented About page polish (plan: `.agents/plans/plan-2026-04-20-about-page-polish.md`).
  - **Icon scaling**: App icon in `_version_card()` enlarged from 96x96 to 288x288 (3x).
  - **GitHub links**: Added `GITHUB_REPO_URL` and `GITHUB_RELEASES_URL` to `_urls.py`; added `github` and `download` SVG icons to `icons.py`; added two link rows to `_links_card()` (GitHub Repository, Releases/Changelog).
  - **Version check**: Switched `version_check.py` from GitLab Releases API to GitHub Releases API (`/repos/alvertremantel/grouper/releases/latest`). Parses single release object (`tag_name` directly, not array). Removed all GitLab constants from `_urls.py`.
  - **Collapsible Features**: Replaced `_readme_card()` with `_collapsible_readme_card()` — toggle button with ▶/▾ indicator, starts collapsed, positioned at bottom of page.
  - **Shoutouts**: Added `_shoutouts_card()` with "Special Thanks" to `@jackgrebin` and `@timecode.violation`, positioned between Links and System Info.
  - **Layout order**: version → links → shoutouts → sysinfo → collapsible readme.
  - **Tests**: 710 pass (excluding e2e), ruff clean, only pre-existing ty error (`app.windowIcon()`).
  - **Branch**: `feat/polish` (not yet merged).

- Implemented system-wide uninstall flow (plan: `.agents/plans/plan-2026-04-20-system-wide-uninstall.md`).
  - **Manifest**: Added `installer_path` and `manifest_version` fields to `InstallManifest` in `grouper_install/manifest.py`. Backward-compatible — `read_manifest()` uses `.get()` with defaults.
  - **Registry**: Updated `register_uninstall()` in `grouper_install/registry.py` — `UninstallString` now uses the manifest's `installer_path` (quoted) with `--uninstall` flag, with fallback to `{app_dest}/setup.exe`.
  - **Installer copy**: During install, `_copy_installer_to_stable_location()` copies `setup.exe` to `%ProgramFiles%\Grouper Apps\Installer\setup.exe`. Path stored in manifest.
  - **Uninstall helpers**: `_remove_shortcut_safe()`, `_remove_dir_safe()`, `_remove_empty_parent()` — all resilient to missing files, report errors as strings.
  - **Uninstall flow** in `SetupDialog._run_uninstall()`:
    1. Remove shortcuts (including empty Start Menu `Grouper` folder)
    2. Remove machine PATH entries via `remove_from_machine_path()`
    3. Remove component directories + empty parent cleanup
    4. Handle installer directory — if running from installer location (ARP launch), schedules `MoveFileExW` for reboot deletion; otherwise removes directly
    5. Registry and manifest removed only if no directory errors occurred; otherwise preserved for re-uninstall
  - **UI**: Added uninstall confirm page (summary of what will be removed, data preservation note) and uninstall complete page (results with ✓/✗ markers). Uninstall button disabled when no manifest exists.
  - **CLI**: `setup.exe --uninstall` flag triggers direct uninstall mode (for ARP entry point).
  - **Elevation**: Uninstall flow prompts for elevation if not admin, relaunches with `--uninstall` flag.
  - **Tests**: 48 tests across `test_manifest.py` (7), `test_registry.py` (5), `test_uninstall_helpers.py` (16), `test_setup_dialog.py` (20). All pass.
  - Verified: ruff clean, ty clean, 709 total tests pass.

- Implemented Phase 5: elevation and machine-wide install behavior.
  - Created `grouper_install/elevation.py` — `is_elevated()` via `ctypes.windll.shell32.IsUserAnAdmin()`, `relaunch_elevated()` via `ShellExecuteW` with `runas`.
  - `relaunch_elevated()` checks return value (≤32 = error), uses `subprocess.list2cmdline` for proper argument quoting.
  - `is_elevated()` stored in `SetupDialog.__init__`; start page shows green/orange elevation status.
  - `_run_install()` gates behind elevation prompt with Yes/No; Yes relaunches elevated, No aborts.
  - Install page shows orange note when not elevated.
- Implemented Phase 6: persist install state for upgrades and uninstall.
  - Created `grouper_install/manifest.py` — `InstallManifest` dataclass, `write_manifest()`, `read_manifest()`, `remove_manifest()` at `%ProgramData%\Grouper\install-manifest.json`.
  - Created `grouper_install/registry.py` — `register_uninstall()` writes ARP entry under `HKLM\...\Uninstall\Grouper` with `EstimatedSize` via `_dir_size()`, `unregister_uninstall()`.
  - Added `variant` field to `VariantInfo` in `grouper_install/dist_meta.py`.
  - Added `_read_version()` helper in `setup.py` (reads `version.txt` or returns "unknown").
  - `_run_install()` writes manifest and registers uninstall after all install operations.
  - Start page detects existing install via `read_manifest()` and shows blue info label with overwrite note.
- Implemented Phase 7: installer UI and messaging updates.
  - Added `_PAGE_COMPLETE = 2` and `_build_complete_page()` with summary label and Close button.
  - `_run_install()` now shows results on completion page (with ✓/✗ markers) instead of `QMessageBox`.
  - Start page shows full component names ("Grouper desktop app, CLI tools, Sync server").
  - Window title includes variant name (e.g. "Grouper Setup — core_cli_server").
- Reviewer found 4 critical issues — all fixed:
  - QStackedWidget page ordering was inverted (complete page added before start/install) — moved `addWidget` to `_build_ui()`.
  - `is_elevated()` returned `True` on `AttributeError` — changed to `False` (fail-safe).
  - `relaunch_elevated()` ignored `ShellExecuteW` failure — now checks return value and raises `OSError`.
  - `UninstallString` pointed to non-existent `uninstall.exe` — changed to `setup.exe --uninstall` placeholder.
- Additional fixes from review: `path_entries` collected directly instead of parsing display strings; `_dir_size()` wrapped in try/except for `OSError`.
- Verified: ruff clean, ty clean, 20 tests pass (13 unit + 7 widget).
- **Next**: Phase 8 (uninstall flow, tests for elevation/manifest/registry modules).

- Implemented Phase 8: comprehensive tests for installer modules.
  - Created `tests/unit/test_dist_meta.py` (15 tests) — `load_dist_toml`, `validate_source_bundle`, `default_destinations`, `VariantInfo`.
  - Created `tests/unit/test_path_env.py` (8 tests) — `split_path`, `normalize_path_entry`, `add_to_machine_path`, `remove_from_machine_path` (all mocked).
  - Created `tests/unit/test_elevation.py` (6 tests) — `is_elevated` with API mocking and fail-safe, `relaunch_elevated` success/failure paths.
  - Created `tests/unit/test_manifest.py` (6 tests) — write, read, roundtrip, corrupt, remove, empty-dir cleanup (with `monkeypatch` on `MANIFEST_DIR`/`MANIFEST_FILE`).
  - Created `tests/unit/test_registry.py` (3 tests) — `register_uninstall` verifies all `SetValueEx` calls, `unregister_uninstall` verifies `DeleteKey`.
  - Created `tests/unit/test_install_copy.py` (3 tests) — `_copy_tree` copy/overwrite/bad-src.
  - Updated `tests/widget/test_setup_dialog.py` — added `TestInstallPageDestinations` (5 tests) and `TestCompletePage` (1 test); added `test_shows_variant_name`. Total: 15 tests (up from 6).
  - `tests/unit/test_install_setup.py` reviewed — no `_install_dir` references needed updating (already uses `_source_root`).
- Verified: ruff clean, 578 tests pass (522 existing + 56 new/updated).

- Rewrote `scripts/build_release.bat` to produce four release variants (`core/`, `core_cli/`, `core_server/`, `core_cli_server/`) instead of one flat folder. Each variant gets its own `app/`, optional `cli/` and `server/` subdirectories, `setup.exe`, and docs. Uses a `:assemble_variant` subroutine to avoid repetition.
- Created `scripts/assemble_release.bat` — assembly-only script that builds the four release variants from existing `dist/` outputs without triggering Nuitka rebuilds.
- Added `--jobs=2` to all four build scripts (`build_grouper.bat`, `build_grouper_cli.bat`, `build_grouper_server.bat`, `build_setup.bat`) for parallel compilation.
- Fixed `grouper/main.py` crash on Nuitka-compiled launch: converted three relative imports (`from .X`) to absolute imports (`from grouper.X`). Nuitka compiles the entry point as `__main__` where `__package__` is unset, causing relative imports to fail with `ImportError`.
- Rebuilt `grouper.exe` and smoke-tested all four executables in `release/core_cli_server/` — clean launches across the board.

## 2026-04-19

- Removed all DRM / license verification from Grouper per `.agents/plans/remove-all-drm.md`.
- Deleted `grouper/licensing.py` (324 lines) and `grouper/ui/activation_dialog.py` (150 lines).
- Removed license gate (`is_licensed()` check), `_RevalidationWorker`, and `_handle_revocation` from `grouper/main.py`; app now launches straight to splash → MainWindow.
- Removed `GUMROAD_URL` from `grouper/_urls.py` and the Gumroad link row from the About page (`grouper/ui/about.py`).
- Removed Gumroad purchase link from `userdocs/README.md`.
- Deleted `tests/unit/licensing/` directory (3 files, ~665 lines of licensing-only tests).
- Extracted non-licensing tests (`TestInstallDir`, `TestDesktopPath`, `TestStartMenuPath`, `TestShortcutCreation`, `TestConfigFirstRun`) into new `tests/unit/test_install_setup.py`.
- Removed `test_licensing_all` from `tests/unit/db/test_optimizations.py`.
- Cleaned up all `GROUPER_DEV` environment variable references from `tests/conftest.py` and 7 widget/unit test files (no longer used by any production code).
- Verified: 636 tests pass, ruff clean, ty errors all pre-existing.

## 2026-04-11

- Reviewed linked worktrees `dragging-tasks` and `summary-cal-fix`; combined report written to `.agents/reviews/2026-04-11-dragging-tasks-and-summary-cal-fix-review.md`.
- Rewired `grouper/ui/task_board.py` so passive `TaskCard` content passes mouse events through to the card frame, which allows drag initiation from labels, tags, and prerequisite chips.
- Added debug logging around task-card drag start and project-column drag enter/drop handling.
- Fixed the task-card drag pixmap render call to use the PySide6-compatible `QWidget.render(...)` signature.
- Added `tests/widget/test_task_board_drag.py` covering passthrough widgets, drag MIME payload generation, click-vs-drag behavior, drop handling, and checkbox clicks.
- Verified with `uv run --extra gui --extra test pytest tests/widget/test_task_board_drag.py` and `uv run ruff check grouper/ui/task_board.py tests/widget/test_task_board_drag.py`.
- Moved the installer Nuitka script from `grouper_install/build_setup.bat` to `scripts/build_setup.bat`, updated `scripts/build_release.bat`, and verified the relocated script by building `dist/setup.exe` successfully.
- Removed the desktop app's direct `grouper_server.web` startup dependency by switching `grouper/main.py` back to the local `grouper.web_server` HTML readouts server and refreshed the `grouper/web_server.py` module description.
- Updated `scripts/build_grouper.bat` for the monorepo layout, added `scripts/build_grouper_cli.bat` and `scripts/build_grouper_server.bat`, and normalized their Nuitka output folders to `dist/grouper*.dist` after compilation.
- Verified with `uv run ruff check grouper/main.py grouper/web_server.py`, `uv run ty check grouper/main.py grouper/web_server.py`, `scripts\build_grouper.bat`, `scripts\build_grouper_cli.bat`, `scripts\build_grouper_server.bat`, and `scripts\build_release.bat`.

- Implemented Phase 9: docs update and manual verification of all four release variants.
  - Updated `.agents/context/NOTES.md` — consolidated installer behavior bullets.
  - Updated `README.md` — added installation section covering: unzip release, run `setup.exe`, elevation prompt, PATH/terminal reopen, Settings > Apps visibility.
  - Manual smoke test — `core` variant: install succeeded, `grouper.exe` runs, shortcuts work, manifest and registry entry verified.
  - Manual smoke test — `core_cli` variant: install succeeded, `grouper-cli --help` works in fresh shell, manifest includes CLI destination.
  - Manual smoke test — `core_server` variant: install succeeded, `grouper-server --help` works in fresh shell.
  - Manual smoke test — `core_cli_server` variant: install succeeded, both CLI and server work in fresh shell.
  - Manual smoke test — custom destinations: files land in selected directories, PATH updated for custom CLI/server paths.
  - Manual smoke test — upgrade detection: second run shows "Existing install found" message, overwrite succeeds without error.

- Phase 9 docs verification complete: rebuilt `setup.exe` via `scripts/build_setup.bat`, all four dist/ executables run cleanly (no tracebacks), `assemble_release.bat` already includes `dist.toml` copying (line 172), all four release variants assembled successfully, manual smoke tests clean.
