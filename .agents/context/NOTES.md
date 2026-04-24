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
- For Qt visual bugs, prefer testing the exact shown widget hierarchy over `widget.grab()` alone.
- Frameless top-level dialog translucency is suspect on this app; do not assume offscreen widget colors match on-screen composition.
- `AddGroupDialog` is visually dominated by its inner `QListWidget`, not just the outer dialog frame.
- For the black theme, `AddGroupDialog` should keep the standard black dialog surfaces; do not bring back the oversized solid list-row override from `example-2.png`.
- Parent card selectors such as `#card QWidget { background-color: transparent; }` can bleed into parented dialogs; dialog selectors need enough specificity to preserve painted surfaces.
- See `.agents/context/qt-pitfalls.md` for the full dialog-contrast postmortem.

## Installer Notes

- `setup.exe` installs components under `%ProgramFiles%\Grouper Apps\`.
- CLI/server install paths are added to machine PATH.
- Install state is stored at `%ProgramData%\Grouper\install-manifest.json`.
- ARP uninstall registration uses `setup.exe --uninstall` via the stored installer path.
- Uninstall removes shortcuts, PATH entries, installed components, registry entry, and manifest.
