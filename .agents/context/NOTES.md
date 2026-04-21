# Grouper

Offline-first productivity app with a PySide6 desktop UI, SQLite storage, and optional LAN/Tailscale sync.

## Packages

- `grouper_core/`: shared models, config, DB, migrations
- `grouper/`: desktop GUI
- `grouper_cli/`: CLI tools
- `grouper_server/`: sync + web server
- `tests/`: unit, widget, CLI, and E2E coverage

## Quick Commands

```bash
uv sync --all-extras
uv run grouper
uv run grouper-server serve
uv run pytest
uv run ruff check .
```

## Key Facts

- Main local data lives under `~/.grouper/`
- Desktop app centers on two areas:
  - time tracking
  - task management
- Sync is manual, peer-to-peer, and uses raw TCP + NDJSON
- Web dashboard is read-only
- Windows is the primary desktop target; core packages stay headless-friendly

## Test Buckets

- `tests/unit/`: fast daily-driver tests
- `tests/widget/`: in-process Qt widget tests
- `tests/cli/`: CLI tests
- `tests/e2e/`: slower real-app Windows flows

## Current Limits

- no automatic background sync
- no transport encryption in sync protocol
- desktop sync is CLI-driven, not exposed in the GUI
- week/day calendar views are still incomplete

## Build / Release Notes

- `scripts/assemble_release.bat` — fast path: assembles four release variants from existing `dist/` without rebuilding
- `scripts/build_release.bat` — full path: rebuilds all four executables then assembles
- Four release variants: `core`, `core_cli`, `core_server`, `core_cli_server`
- Each variant ships a `dist.toml` (copied from `grouper_install/dist/%VARIANT_NAME%.toml`) identifying its component set.
- `setup.exe` is now a real installer: copies components to `%ProgramFiles%\Grouper Apps\`, adds CLI/server directories to system PATH, writes install manifest to `%ProgramData%\Grouper\`, and registers ARP uninstall entry.
- `grouper_install/dist_meta.py` parses `dist.toml` and validates the bundle — used by setup.exe (Phase 3+)
- `grouper_install/path_env.py` handles Windows registry PATH manipulation — uses `SendMessageTimeoutW` (not `SendMessageW`) to avoid hangs, context managers for registry handles
- `grouper_install/elevation.py` — UAC elevation via `ctypes.windll.shell32.IsUserAnAdmin()` / `ShellExecuteW(..., "runas", ...)`; `is_elevated()` returns `False` on `AttributeError` (fail-safe); `relaunch_elevated()` checks `ShellExecuteW` return value (≤32 = error)
- `grouper_install/manifest.py` — install state persisted at `%ProgramData%\Grouper\install-manifest.json`; includes `installer_path` and `manifest_version` fields; backward-compatible `read_manifest()` uses `.get()` with defaults
- `grouper_install/registry.py` — ARP uninstall registration under `HKLM\...\Uninstall\Grouper`; `UninstallString` uses manifest's `installer_path` (quoted + `--uninstall`), fallback to `{app_dest}/setup.exe`
- `grouper_install/setup.py` — 5-page SetupDialog (start → install → complete → uninstall-confirm → uninstall-complete); install copies `setup.exe` to `%ProgramFiles%\Grouper Apps\Installer\setup.exe`; uninstall removes shortcuts, PATH entries, component dirs, installer copy (or schedules `MoveFileExW` for reboot if self-deleting), registry, and manifest; `--uninstall` CLI flag for ARP entry point; manifest/registry preserved on directory failure for re-uninstall
- Entry-point modules (`grouper/main.py`) must use absolute imports, not relative — Nuitka runs them as `__main__` where `__package__` is unset
- Nuitka on Python 3.14 is experimental; may need to pin to 3.13 if issues arise
- `dist/` is gitignored; `release/` is also gitignored
- Version checking uses GitHub Releases API (`/repos/alvertremantel/grouper/releases/latest`); `grouper/_urls.py` holds `GITHUB_RELEASES_API_URL`, `GITHUB_REPO_URL`, `GITHUB_RELEASES_URL`, and `CONTACT_URL`
- About page (`grouper/ui/about.py`) layout: version → links (GitHub, Releases, Contact) → shoutouts → sysinfo → collapsible Features & Details (starts collapsed)
