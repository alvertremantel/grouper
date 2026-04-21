"""
config.py — Application configuration for Grouper.

Singleton ConfigManager backed by a JSON file stored next to the database.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import threading
from dataclasses import asdict, dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

__all__ = [
    "APP_DIR",
    "CONFIG_FILE",
    "Config",
    "ConfigManager",
    "get_config",
]


APP_DIR = Path.home() / ".grouper"
CONFIG_FILE = APP_DIR / "config.json"


@dataclass
class Config:
    """All user-facing configuration."""

    database_path: str = ""
    backup_path: str = ""
    theme: str = "dark"
    default_priority: int = 3
    window_width: int = 1200
    window_height: int = 750
    sidebar_collapsed: bool = False
    web_port: int = 4747
    bg_notes_enabled: bool = False
    animations_enabled: bool = True
    sync_host: str = "127.0.0.1"
    sync_port: int = 53987
    sync_mdns_enabled: bool = True

    def __post_init__(self) -> None:
        orig_port = self.web_port
        self.web_port = max(1024, min(65535, self.web_port))
        if self.web_port != orig_port:
            logger.warning("web_port %s clamped to %s", orig_port, self.web_port)

        orig_width = self.window_width
        self.window_width = max(400, self.window_width)
        if self.window_width != orig_width:
            logger.warning("window_width %s clamped to %s", orig_width, self.window_width)

        orig_height = self.window_height
        self.window_height = max(300, self.window_height)
        if self.window_height != orig_height:
            logger.warning("window_height %s clamped to %s", orig_height, self.window_height)

        orig_priority = self.default_priority
        self.default_priority = max(0, min(4, self.default_priority))
        if self.default_priority != orig_priority:
            logger.warning(
                "default_priority %s clamped to %s", orig_priority, self.default_priority
            )

        orig_sync_port = self.sync_port
        self.sync_port = max(1024, min(65535, self.sync_port))
        if self.sync_port != orig_sync_port:
            logger.warning("sync_port %s clamped to %s", orig_sync_port, self.sync_port)

        try:
            ipaddress.ip_address(self.sync_host)
        except ValueError:
            logger.warning("sync_host %r invalid, falling back to 127.0.0.1", self.sync_host)
            self.sync_host = "127.0.0.1"

    @classmethod
    def default(cls) -> Config:
        data_dir = APP_DIR / "data"
        return cls(
            database_path=str(data_dir / "grouper.db"),
            backup_path=str(data_dir / "backups"),
        )


class ConfigManager:
    """Singleton configuration manager."""

    _instance: ConfigManager | None = None

    def __new__(cls) -> ConfigManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialised = False
        return cls._instance

    def __init__(self):
        if not self._initialised:
            self._initialised = True
            self._config: Config | None = None
            self._lock = threading.Lock()
            self._load_or_create()

    # -- public API ----------------------------------------------------------

    @property
    def config(self) -> Config:
        return self._config

    def update(self, **kwargs) -> None:
        for key, value in kwargs.items():
            if hasattr(self._config, key):
                setattr(self._config, key, value)
        self._save()

    # -- internal ------------------------------------------------------------

    def _load_or_create(self) -> None:
        if CONFIG_FILE.exists():
            try:
                data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                # Migrate legacy theme names
                if data.get("theme") == "jetblack":
                    data["theme"] = "black"
                self._config = Config(
                    **{k: v for k, v in data.items() if k in Config.__dataclass_fields__}
                )
            except Exception as e:
                logger.warning("Failed to load config, using defaults: %s", e)
                self._config = Config.default()
                self._save()
        else:
            self._config = Config.default()
            self._ensure_dirs()
            self._save()

    def _ensure_dirs(self) -> None:
        Path(self._config.database_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self._config.backup_path).mkdir(parents=True, exist_ok=True)

    def _save(self) -> None:
        with self._lock:
            APP_DIR.mkdir(parents=True, exist_ok=True)
            CONFIG_FILE.write_text(
                json.dumps(asdict(self._config), indent=2),
                encoding="utf-8",
            )


def get_config() -> Config:
    """Convenience accessor."""
    return ConfigManager().config
