# Grouper

Offline-first productivity app with a PySide6 desktop UI, SQLite storage, CLI tools, and optional LAN/Tailscale sync.

## Packages

- `desktop/`: PySide6 desktop app; installed GUI command remains `grouper`.
- `grouper_core/`: shared models, config, formatting, operations, DB, migrations, and colors.
- `cli/`: CLI tools.
- `grouper_sync/`: LAN sync package shared by desktop and server; must not import `desktop` or `server`.
- `server/`: standalone sync + web server package; installed command remains `grouper-server`.
- `installer/`: Windows installer.

## Quick Commands

```bash
uv sync --all-extras
uv run grouper
uv run grouper-cli
uv run grouper-server serve
uv run pytest <specific test group>
uv run ruff check desktop tests
```

## Durable Notes

- Python imports for the desktop app are now `desktop.*`; do not reintroduce `grouper.*` as a Python package import.
- The distribution/project name and GUI executable remain `grouper`; `[project.gui-scripts] grouper = "desktop.main:main"` is intentional.
- `desktop/ui/shared/` contains reusable UI infrastructure: base cards/dialogs, title bar, animation stack/card, icons, widgets, view models, splash.
- Feature UI modules live under `desktop/ui/time/`, `desktop/ui/tasks/`, `desktop/ui/calendar/`, and `desktop/ui/views/`.
- `desktop.ui.tasks.dialogs` still re-exports `FramelessDialog` for compatibility; canonical base classes live in `desktop.ui.shared.base_dialog`.
- Entry modules support source-checkout script execution (`python desktop/__main__.py`, `python desktop/main.py`) by adding the repo root to `sys.path` only when run without package context.
- Main local data lives under `~/.grouper/`.
- Tests isolate DB and config paths via the root autouse fixture in `tests/conftest.py`; no test should write to `~/.grouper/`.
- Database `db_path.txt` persistence must use `grouper_core.config.APP_DIR`; do not add separate `Path.home() / ".grouper"` config paths in database modules.
- Do not run the full test suite as one monolithic command in this repo during this session. It is unreliable in this environment; run test groups separately instead.
- Do not create root-level `STATUS.md` or `NOTES.md`; keep status/notes under `.agents/context/` only.
- The sync entrypoint (`grouper_sync/__main__.py`) has no import-time `init_database()` side effect; DB init happens inside `main()`.
- No `grouper_server` compatibility shim should be reintroduced; use `grouper_sync.*` for sync and `server.*` for server/web/runtime code.
- For Qt visual bugs, prefer testing the exact shown widget hierarchy over `widget.grab()` alone.
- Frameless top-level dialog translucency is suspect; keep dialog frame/content styled and opaque.
- Parent card selectors such as `#card QWidget { background-color: transparent; }` can bleed into parented dialogs; dialog selectors need enough specificity to preserve painted surfaces.
- See `.agents/context/qt-pitfalls.md` for the full dialog-contrast postmortem.

## Installer Notes

- `setup.exe` installs components under `%ProgramFiles%\Grouper Apps\`.
- CLI/server install paths are added to machine PATH.
- Install state is stored at `%ProgramData%\Grouper\install-manifest.json`.
- ARP uninstall registration uses `setup.exe --uninstall` via the stored installer path.
