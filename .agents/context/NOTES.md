# Grouper

Offline-first productivity app with a PySide6 desktop UI, SQLite storage, and optional LAN/Tailscale sync.

## Packages

- `grouper_core/`: shared models, config, DB, migrations
- `grouper/`: desktop app
- `grouper_cli/`: CLI tools
- `grouper_server/`: sync server + web dashboard
- `grouper_install/`: Windows installer

## Quick Commands

```bash
uv sync --all-extras
uv run grouper
uv run grouper-server serve
uv run pytest
uv run ruff check .
```

## Durable Notes

- Main local data lives under `~/.grouper/`.
- Primary desktop focus is time tracking and task management.
- Sync is manual peer-to-peer over raw TCP + NDJSON.
- Web dashboard is read-only.
- Windows is the main desktop target.
- Entry-point modules should use absolute imports for Nuitka builds.
- Version checking uses the GitHub Releases API.
- `dist/` and `release/` are gitignored.
- Animation performance is Qt-widget bound: prefer shorter durations and avoid layout-heavy `maximumHeight` animations on complex/scrollable views. If needed, use snapshot-based page transitions instead of sliding live full pages.
- Tests isolate DB and config paths via the root autouse fixture in `tests/conftest.py`; no test should write to `~/.grouper/`.
- The fixture patches both `grouper_core.config` and re-exported `grouper.config` path constants because `from ... import *` copies references before monkeypatching. `APP_DIR`/`CONFIG_FILE` are monkeypatched **before** `_init_paths()` so any code path that calls `_save_data_directory()` writes to the temp dir.
- Database `db_path.txt` persistence must use `grouper_core.config.APP_DIR`; do not add separate `Path.home() / ".grouper"` config paths in database modules.
- The sync legacy entrypoint (`grouper_server/sync/__main__.py`) has no import-time `init_database()` side effect; DB init happens inside `main()`.
- For Qt visual bugs, prefer testing the exact shown widget hierarchy over `widget.grab()` alone.
- Frameless top-level dialog translucency is suspect on this app; do not assume offscreen widget colors match on-screen composition.
- `AddGroupDialog` is visually dominated by its inner `QListWidget`, not just the outer dialog frame.
- For the black theme, `AddGroupDialog` should keep the standard black dialog surfaces; do not bring back the oversized solid list-row override from `example-2.png`.
- Summary trend bar low-end colors should use real palette surface tokens such as `bg-secondary`, not ad-hoc nonexistent aliases.
- Black dialog body/content should stay on `bg-primary`; the title bar may use `bg-tertiary` for perceptible non-parented chrome contrast.
- Parent card selectors such as `#card QWidget { background-color: transparent; }` can bleed into parented dialogs; dialog selectors need enough specificity to preserve painted surfaces.
- When writing QSS for dialogs that may appear inside `#card`, group `#card` variants with the base selector (e.g., `#dialogFrame, #card #dialogFrame`) instead of duplicating the entire block.
- See `.agents/context/qt-pitfalls.md` for the full dialog-contrast postmortem.

## Installer Notes

- `setup.exe` installs components under `%ProgramFiles%\Grouper Apps\`.
- CLI/server install paths are added to machine PATH.
- Install state is stored at `%ProgramData%\Grouper\install-manifest.json`.
- ARP uninstall registration uses `setup.exe --uninstall` via the stored installer path.
- Uninstall removes shortcuts, PATH entries, installed components, registry entry, and manifest.
