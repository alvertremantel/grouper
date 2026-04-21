# Repo Map

## Top-level layout

```
grouper_core/    shared models, config, DB layer, migrations
grouper/         desktop GUI (PySide6)
grouper_cli/     CLI tools
grouper_server/  sync server + web dashboard
grouper_install/ Windows installer / setup wizard
                  dist/ — four variant TOML files (core, core_cli, core_server, core_cli_server)
                  dist_meta.py — VariantInfo (with variant field), load_dist_toml, validate_source_bundle, default_destinations
                  elevation.py — UAC elevation: is_elevated(), relaunch_elevated()
                  manifest.py — InstallManifest dataclass (+ installer_path, manifest_version), write/read/remove at %ProgramData%\Grouper\
                  path_env.py — Windows registry PATH read/write, SendMessageTimeoutW broadcast
                  registry.py — ARP uninstall registration under HKLM\...\Uninstall\Grouper; UninstallString uses installer_path
                  setup.py — SetupDialog: 5-page flow (start → install → complete → uninstall-confirm → uninstall-complete); --uninstall flag
tests/           unit / widget / cli / integration / e2e
scripts/         build scripts (Nuitka .bat files)
userdocs/        end-user README
release/         release assets (gitignored, four variants)
```

## Key entry points

- `grouper/main.py` — desktop app startup (splash → MainWindow)
- `grouper/app.py` — `MainWindow` (sidebar + view stack)
- `grouper_cli/__main__.py` — CLI entry
- `grouper_server/__main__.py` — sync/web server entry

## grouper/ structure

- `_urls.py` — external URLs (contact, GitHub releases API, GitHub repo/releases)
- `_version.py` — `__version__`
- `config.py` — `Config` dataclass, `ConfigManager` singleton
- `models.py` — app-level data models
- `database/` — DB connection init, migrations
- `styles/` — QSS themes (dark, light, sage)
- `ui/` — all Qt widgets/views (about, dashboard, task_board, time_tracker, etc.)
- `web_server.py` — local HTML readouts server

## grouper_core/ structure

- `config.py` — `Config` dataclass, `ConfigManager`, path setup
- `models.py` — shared data models
- `database/` — all DB operations (activities, tasks, sessions, events, etc.)

## tests/ structure

- `conftest.py` — root `isolated_db` fixture
- `unit/` — fast unit tests (core, db, sync, install_setup)
- `widget/` — in-process Qt widget tests
- `cli/` — CLI command tests
- `integration/` — multi-module integration tests
- `e2e/` — full app Windows flows
