"""ServerRunner — manages the lifecycle of sync server + web server.

Both the TUI and headless mode use this class. It owns the sync server
(async) and the Flask web server (daemon thread).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .sync.discovery import SyncAdvertiser
    from .sync.server import SyncServer

logger = logging.getLogger(__name__)


@dataclass
class ServerConfig:
    """Configuration for the unified server."""

    sync_host: str = "0.0.0.0"
    sync_port: int = 53987
    web_host: str = "127.0.0.1"
    web_port: int = 4747
    no_mdns: bool = False
    no_web: bool = False
    behind_proxy: bool = False
    url_prefix: str = ""


@dataclass
class ServerStatus:
    """Snapshot of current server state."""

    sync_running: bool = False
    sync_host: str = ""
    sync_port: int = 0
    sync_device_id: str = ""
    web_running: bool = False
    web_port: int = 0
    started_at: datetime | None = None
    peer_count: int = 0


class ServerRunner:
    """Manages the lifecycle of sync server + web server."""

    def __init__(self, config: ServerConfig) -> None:
        self.config = config
        self._sync_server: SyncServer | None = None
        self._advertiser: SyncAdvertiser | None = None
        self._web_thread: threading.Thread | None = None
        self._status = ServerStatus()
        self._listeners: list[object] = []  # callbacks for status changes

    @property
    def status(self) -> ServerStatus:
        return self._status

    async def start_sync(self) -> None:
        """Start the async TCP sync server."""

        from grouper_core.database.connection import get_database_path

        from .sync.server import SyncServer

        db_path = get_database_path()
        self._sync_server = SyncServer(
            db_path,
            host=self.config.sync_host,
            port=self.config.sync_port,
        )
        await self._sync_server.start()

        actual_port = self._sync_server.actual_port
        device_id = self._sync_server.device_id

        self._status.sync_running = True
        self._status.sync_host = self.config.sync_host
        self._status.sync_port = actual_port
        self._status.sync_device_id = device_id
        self._status.started_at = datetime.now()

        logger.info(
            "Sync server listening on %s:%d (device %s)",
            self.config.sync_host,
            actual_port,
            device_id[:8],
        )

        # Start mDNS advertisement
        if not self.config.no_mdns:
            try:
                import socket

                from .sync.discovery import SyncAdvertiser

                self._advertiser = SyncAdvertiser(
                    device_id=device_id,
                    device_name=socket.gethostname(),
                    port=actual_port,
                )
                await asyncio.get_event_loop().run_in_executor(None, self._advertiser.start)
            except Exception:
                logger.warning("mDNS advertisement failed — continuing without it")

    def start_web(self) -> None:
        """Start the Flask web server in a daemon thread."""
        if self.config.no_web:
            logger.info("Web server disabled (--no-web)")
            return

        try:
            from .web import start_web_server

            start_web_server(
                self.config.web_port,
                self.config.web_host,
                behind_proxy=self.config.behind_proxy,
                url_prefix=self.config.url_prefix,
            )
            self._status.web_running = True
            self._status.web_port = self.config.web_port
        except Exception:
            logger.exception("Failed to start web server")

    async def serve_forever(self) -> None:
        """Block until the sync server is stopped."""
        if self._sync_server:
            await self._sync_server.serve_forever()

    async def stop(self) -> None:
        """Graceful shutdown of both servers."""
        if self._advertiser:
            with contextlib.suppress(Exception):
                self._advertiser.stop()
            self._advertiser = None

        if self._sync_server:
            await self._sync_server.stop()
            self._sync_server = None

        self._status.sync_running = False
        self._status.web_running = False
        logger.info("Server stopped")
