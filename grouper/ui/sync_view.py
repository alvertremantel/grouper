"""
sync_view.py — Sync control panel for Grouper.

Exposes the peer-to-peer sync backend in the desktop GUI: device identity,
server start/stop, known peers, manual connect, and LAN discovery.
"""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import logging
import re
import socket
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QShowEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..config import ConfigManager, get_config
from ..database.connection import get_connection, get_database_path, get_notifier
from .widgets import ThemedSpinBox, clear_layout

if TYPE_CHECKING:
    from grouper_server.sync.discovery import Peer, SyncBrowser

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
#  Workers — run async sync operations in dedicated threads
# ---------------------------------------------------------------------------


class SyncServerWorker(QThread):
    """Runs the async TCP sync server in a background thread."""

    started = Signal(str, int, str)  # host, actual_port, device_id
    stopped = Signal()
    error = Signal(str)

    def __init__(
        self,
        db_path: Path,
        host: str,
        port: int,
        enable_mdns: bool,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._db_path = db_path
        self._host = host
        self._port = port
        self._enable_mdns = enable_mdns
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_event: asyncio.Event | None = None

    def run(self) -> None:
        from grouper_server.sync.runtime import SyncPhaseError, format_sync_error
        from grouper_server.sync.server import SyncServer

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._stop_event = asyncio.Event()

        try:
            loop.run_until_complete(self._serve(SyncServer))
        except Exception as exc:
            if not isinstance(exc, SyncPhaseError):
                log.exception(
                    "Sync server worker failed db=%s host=%s port=%s",
                    self._db_path,
                    self._host,
                    self._port,
                )
            self.error.emit(format_sync_error(exc))
        finally:
            loop.close()
            self._loop = None
            self.stopped.emit()

    async def _serve(self, server_cls: type) -> None:
        server = server_cls(self._db_path, self._host, self._port)
        await server.start()
        self.started.emit(self._host, server.actual_port, server.device_id)

        advertiser = None
        if self._enable_mdns:
            try:
                from grouper_server.sync.discovery import SyncAdvertiser

                advertiser = SyncAdvertiser(
                    device_id=server.device_id,
                    device_name=socket.gethostname(),
                    port=server.actual_port,
                )
                advertiser.start()
            except Exception:
                log.warning("mDNS advertisement failed — continuing without it")

        assert self._stop_event is not None
        await self._stop_event.wait()

        if advertiser is not None:
            with contextlib.suppress(Exception):
                advertiser.stop()
        await server.stop()

    def request_stop(self) -> None:
        """Thread-safe request to shut down the server."""
        if self._loop is not None and self._stop_event is not None:
            self._loop.call_soon_threadsafe(self._stop_event.set)


class SyncClientWorker(QThread):
    """One-shot worker: connect to a peer and sync."""

    success = Signal(int, int)  # sent, received
    error = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        db_path: Path,
        host: str,
        port: int,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._db_path = db_path
        self._host = host
        self._port = port
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_event: asyncio.Event | None = None

    def run(self) -> None:
        from grouper_server.sync.client import sync_with_peer
        from grouper_server.sync.runtime import (
            SyncPhaseError,
            format_sync_error,
            prepare_local_sync_database,
        )

        try:
            prepare_local_sync_database(
                self._db_path,
                logger=log,
                host=self._host,
                port=self._port,
                busy_timeout_ms=5000,
            )

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop
            self._stop_event = asyncio.Event()
            loop.run_until_complete(self._sync_with_cancellation(loop, sync_with_peer))
        except Exception as exc:
            if not isinstance(exc, SyncPhaseError):
                log.exception(
                    "Sync client worker failed db=%s host=%s port=%s",
                    self._db_path,
                    self._host,
                    self._port,
                )
            self.error.emit(format_sync_error(exc))
        finally:
            if self._loop is not None:
                self._loop.close()
            self._loop = None

    async def _sync_with_cancellation(
        self, loop: asyncio.AbstractEventLoop, sync_fn: object
    ) -> None:
        assert self._stop_event is not None
        sync_task = loop.create_task(sync_fn(self._db_path, self._host, self._port))  # type: ignore
        stop_task = loop.create_task(self._stop_event.wait())

        done, _pending = await asyncio.wait(
            [sync_task, stop_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        if stop_task in done:
            sync_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await sync_task
            self.cancelled.emit()
            return

        stop_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await stop_task

        result = sync_task.result()
        self.success.emit(result["sent"], result["received"])

    def request_stop(self) -> None:
        if self._loop is not None and self._stop_event is not None:
            self._loop.call_soon_threadsafe(self._stop_event.set)


# ---------------------------------------------------------------------------
#  SyncView — main widget
# ---------------------------------------------------------------------------


class SyncView(QWidget):
    """Sync control panel — device info, server controls, peers, connect."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._dirty = True
        self._server_worker: SyncServerWorker | None = None
        self._client_worker: SyncClientWorker | None = None
        self._browser: SyncBrowser | None = None  # if available
        self._server_device_id: str = ""
        self._server_had_error: bool = False

        self._build()

        # Refresh timer (debounced data_changed)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(100)
        self._refresh_timer.timeout.connect(self._refresh_status)

        get_notifier().data_changed.connect(
            self._on_data_changed, Qt.ConnectionType.QueuedConnection
        )

        # Discovery poll timer
        self._discovery_timer = QTimer(self)
        self._discovery_timer.setInterval(3000)
        self._discovery_timer.timeout.connect(self._poll_discovered_peers)

    # -- build UI -----------------------------------------------------------

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)

        container = QWidget()
        scroll.setWidget(container)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

        heading = QLabel("Sync")
        heading.setProperty("heading", True)
        layout.addWidget(heading)

        self._build_device_section(layout)
        self._build_server_section(layout)
        self._build_peers_section(layout)
        self._build_connect_section(layout)
        self._build_discovery_section(layout)
        layout.addStretch()

    def _build_device_section(self, parent_layout: QVBoxLayout) -> None:
        group = QGroupBox("This Device")
        form = QFormLayout(group)

        # Device ID row: truncated label + copy button
        id_row = QHBoxLayout()
        self._device_id_label = QLabel("—")
        self._device_id_label.setObjectName("mutedLabel")
        self._device_id_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        id_row.addWidget(self._device_id_label)
        copy_btn = QPushButton("Copy")
        copy_btn.setFixedWidth(60)
        copy_btn.clicked.connect(self._copy_device_id)
        id_row.addWidget(copy_btn)
        id_row.addStretch()
        id_widget = QWidget()
        id_widget.setLayout(id_row)
        id_row.setContentsMargins(0, 0, 0, 0)
        form.addRow("Device ID:", id_widget)

        self._hostname_label = QLabel(socket.gethostname())
        form.addRow("Hostname:", self._hostname_label)

        # CDC status with dot
        cdc_row = QHBoxLayout()
        self._cdc_dot = QLabel()
        self._cdc_dot.setObjectName("statusDotInactive")
        cdc_row.addWidget(self._cdc_dot)
        self._cdc_label = QLabel("Unknown")
        cdc_row.addWidget(self._cdc_label)
        cdc_row.addStretch()
        cdc_widget = QWidget()
        cdc_widget.setLayout(cdc_row)
        cdc_row.setContentsMargins(0, 0, 0, 0)
        form.addRow("CDC:", cdc_widget)

        self._bootstrap_label = QLabel("-")
        form.addRow("Bootstrap:", self._bootstrap_label)

        self._changelog_label = QLabel("-")
        form.addRow("Changelog:", self._changelog_label)

        self._deferred_label = QLabel("-")
        form.addRow("Deferred:", self._deferred_label)

        parent_layout.addWidget(group)

    def _build_server_section(self, parent_layout: QVBoxLayout) -> None:
        group = QGroupBox("Server")
        layout = QVBoxLayout(group)

        form = QFormLayout()
        cfg = get_config()

        self._bind_edit = QLineEdit(cfg.sync_host)
        self._bind_edit.setPlaceholderText("127.0.0.1")
        form.addRow("Bind address:", self._bind_edit)

        self._port_spin = ThemedSpinBox()
        self._port_spin.setRange(1024, 65535)
        self._port_spin.setValue(cfg.sync_port)
        form.addRow("Port:", self._port_spin)

        from grouper_server.sync.discovery import HAS_ZEROCONF

        self._mdns_cb = QCheckBox("Enable mDNS advertisement")
        self._mdns_cb.setChecked(cfg.sync_mdns_enabled)
        if not HAS_ZEROCONF:
            self._mdns_cb.setEnabled(False)
            self._mdns_cb.setToolTip("Install zeroconf for LAN discovery")
        form.addRow(self._mdns_cb)

        layout.addLayout(form)

        # Button + status row
        btn_row = QHBoxLayout()
        self._server_btn = QPushButton("Start Server")
        self._server_btn.clicked.connect(self._on_server_toggle)
        btn_row.addWidget(self._server_btn)

        self._server_dot = QLabel()
        self._server_dot.setObjectName("statusDotInactive")
        btn_row.addWidget(self._server_dot)

        self._server_status_label = QLabel("Stopped")
        self._server_status_label.setObjectName("mutedLabel")
        btn_row.addWidget(self._server_status_label)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        parent_layout.addWidget(group)

    def _build_peers_section(self, parent_layout: QVBoxLayout) -> None:
        group = QGroupBox("Known Peers")
        layout = QVBoxLayout(group)

        self._peers_layout = QVBoxLayout()
        self._peers_layout.setSpacing(8)
        layout.addLayout(self._peers_layout)

        self._peers_empty = QLabel("No known peers yet.")
        self._peers_empty.setObjectName("mutedLabel")
        self._peers_layout.addWidget(self._peers_empty)

        btn_row = QHBoxLayout()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh_peers)
        btn_row.addWidget(refresh_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        parent_layout.addWidget(group)

    def _build_connect_section(self, parent_layout: QVBoxLayout) -> None:
        group = QGroupBox("Quick Connect")
        layout = QVBoxLayout(group)

        row = QHBoxLayout()
        self._connect_edit = QLineEdit()
        self._connect_edit.setPlaceholderText(
            "host[:port], e.g. 192.168.1.10 or 192.168.1.10:53987"
        )
        self._connect_edit.returnPressed.connect(self._on_connect)
        row.addWidget(self._connect_edit, stretch=1)

        self._connect_btn = QPushButton("Connect")
        self._connect_btn.clicked.connect(self._on_connect)
        row.addWidget(self._connect_btn)
        layout.addLayout(row)

        self._connect_result = QLabel()
        self._connect_result.setWordWrap(True)
        layout.addWidget(self._connect_result)

        parent_layout.addWidget(group)

    def _build_discovery_section(self, parent_layout: QVBoxLayout) -> None:
        from grouper_server.sync.discovery import HAS_ZEROCONF

        if not HAS_ZEROCONF:
            hint = QLabel("Install zeroconf for automatic LAN peer discovery.")
            hint.setObjectName("mutedLabel")
            parent_layout.addWidget(hint)
            self._discovery_group: QGroupBox | None = None
            return

        group = QGroupBox("Discovered Peers")
        layout = QVBoxLayout(group)

        self._discovery_layout = QVBoxLayout()
        self._discovery_layout.setSpacing(8)
        layout.addLayout(self._discovery_layout)

        self._discovery_empty = QLabel("Scanning LAN...")
        self._discovery_empty.setObjectName("mutedLabel")
        self._discovery_layout.addWidget(self._discovery_empty)

        parent_layout.addWidget(group)
        self._discovery_group = group

    # -- events -------------------------------------------------------------

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if self._dirty:
            self._dirty = False
            self._refresh_status()

    def _on_data_changed(self) -> None:
        if self.isVisible():
            if not self._refresh_timer.isActive():
                self._refresh_timer.start()
        else:
            self._dirty = True

    # -- refresh ------------------------------------------------------------

    def _refresh_status(self) -> None:
        """Refresh device info and known peers from the database."""
        self._refresh_device_info()
        self._refresh_peers()

    def _refresh_device_info(self) -> None:
        try:
            with get_connection() as conn:
                # Check if sync tables exist
                tables = {
                    r[0]
                    for r in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                if "sync_state" not in tables:
                    self._device_id_label.setText("Not initialized")
                    self._cdc_dot.setObjectName("statusDotInactive")
                    self._cdc_dot.style().polish(self._cdc_dot)
                    self._cdc_label.setText("Inactive")
                    self._changelog_label.setText("0")
                    self._bootstrap_label.setText("Not initialized")
                    self._deferred_label.setText("Unavailable")
                    return

                row = conn.execute("SELECT * FROM sync_state WHERE id = 1").fetchone()
                if row:
                    full_id = row["device_id"] or ""
                    self._device_id_label.setText(f"{full_id[:8]}..." if full_id else "-")
                    self._device_id_label.setProperty("_full_id", full_id)
                    cdc_active = not row["syncing"]
                    dot_name = "statusDotActive" if cdc_active else "statusDotInactive"
                    self._cdc_dot.setObjectName(dot_name)
                    self._cdc_dot.style().polish(self._cdc_dot)
                    self._cdc_label.setText("Active" if cdc_active else "Suppressed")

                    cols = dict(row)
                    if "bootstrap_complete" in cols and "bootstrap_watermark" in cols:
                        is_complete = cols["bootstrap_complete"]
                        self._bootstrap_label.setText("Complete" if is_complete else "Pending")
                    else:
                        self._bootstrap_label.setText("Migration needed")
                else:
                    self._device_id_label.setText("Not initialized")
                    self._bootstrap_label.setText("Not initialized")

                if "sync_changelog" in tables:
                    count = conn.execute("SELECT COUNT(*) FROM sync_changelog").fetchone()[0]
                    self._changelog_label.setText(str(count))
                else:
                    self._changelog_label.setText("0")

                if "sync_deferred_changes" in tables:
                    deferred_count = conn.execute(
                        "SELECT COUNT(*) FROM sync_deferred_changes"
                    ).fetchone()[0]
                    self._deferred_label.setText(str(deferred_count))
                else:
                    self._deferred_label.setText("Unavailable")
        except Exception as exc:
            log.warning("Failed to refresh device info: %s", exc)

    def _refresh_peers(self) -> None:
        try:
            with get_connection() as conn:
                tables = {
                    r[0]
                    for r in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                if "sync_peers" not in tables:
                    peers = []
                else:
                    peers = conn.execute("SELECT * FROM sync_peers").fetchall()
        except Exception as exc:
            log.warning("Failed to refresh peers: %s", exc)
            peers = []

        clear_layout(self._peers_layout)

        if not peers:
            empty = QLabel("No known peers yet.")
            empty.setObjectName("mutedLabel")
            self._peers_layout.addWidget(empty)
            return

        for p in peers:
            card = self._make_peer_card(
                name=p["peer_name"] or "Unknown",
                device_id=p["peer_device_id"] or "",
                last_sync=p["last_sync_at"] or "never",
                hwm=p["last_changelog_id"],
            )
            self._peers_layout.addWidget(card)

    def _make_peer_card(
        self,
        name: str,
        device_id: str,
        last_sync: str,
        hwm: int,
    ) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        top = QHBoxLayout()
        name_label = QLabel(name)
        name_label.setObjectName("cardTitle")
        top.addWidget(name_label)
        id_label = QLabel(f"{device_id[:8]}..." if device_id else "")
        id_label.setObjectName("mutedLabel")
        top.addWidget(id_label)
        top.addStretch()
        layout.addLayout(top)

        info = QLabel(f"Last sync: {last_sync}  |  HWM: {hwm}")
        info.setObjectName("mutedLabel")
        layout.addWidget(info)

        return card

    # -- server controls ----------------------------------------------------

    def _on_server_toggle(self) -> None:
        if self._server_worker is not None and self._server_worker.isRunning():
            self._stop_server()
        else:
            self._start_server()

    def _start_server(self) -> None:
        # Save current settings to config
        host = self._bind_edit.text().strip() or "127.0.0.1"
        try:
            ipaddress.ip_address(host)
        except ValueError:
            self._server_status_label.setText(f"Invalid bind address: {host!r}")
            self._server_status_label.setObjectName("dangerLabel")
            self._server_status_label.style().polish(self._server_status_label)
            return
        port = self._port_spin.value()
        mdns = self._mdns_cb.isChecked()
        ConfigManager().update(sync_host=host, sync_port=port, sync_mdns_enabled=mdns)

        db_path = get_database_path()
        self._server_worker = SyncServerWorker(db_path, host, port, mdns, parent=None)
        self._server_worker.started.connect(self._on_server_started)
        self._server_worker.stopped.connect(self._on_server_stopped)
        self._server_worker.error.connect(self._on_server_error)
        self._server_worker.finished.connect(self._server_worker.deleteLater)
        self._server_worker.start()

        # Disable controls during startup
        self._server_btn.setEnabled(False)
        self._server_btn.setText("Starting...")
        self._set_server_controls_enabled(False)

    def _stop_server(self) -> None:
        if self._server_worker is not None:
            self._server_btn.setEnabled(False)
            self._server_btn.setText("Stopping...")
            self._server_worker.request_stop()

    def _on_server_started(self, host: str, port: int, device_id: str) -> None:
        self._server_had_error = False
        self._server_device_id = device_id
        self._server_btn.setEnabled(True)
        self._server_btn.setText("Stop Server")
        self._server_btn.setProperty("danger", True)
        self._server_btn.style().polish(self._server_btn)
        self._server_dot.setObjectName("statusDotActive")
        self._server_dot.style().polish(self._server_dot)
        self._server_status_label.setText(f"Running on {host}:{port}")
        self._server_status_label.setObjectName("successLabel")
        self._server_status_label.style().polish(self._server_status_label)

        # Start mDNS browser for discovery
        self._start_discovery(device_id)

        # Refresh device info (CDC should now be active)
        self._refresh_device_info()

    def _on_server_stopped(self) -> None:
        if self._server_had_error:
            self._server_had_error = False
            self._server_worker = None
            self._stop_discovery()
            return

        self._server_worker = None
        self._server_btn.setEnabled(True)
        self._server_btn.setText("Start Server")
        self._server_btn.setProperty("danger", False)
        self._server_btn.style().polish(self._server_btn)
        self._server_dot.setObjectName("statusDotInactive")
        self._server_dot.style().polish(self._server_dot)
        self._server_status_label.setText("Stopped")
        self._server_status_label.setObjectName("mutedLabel")
        self._server_status_label.style().polish(self._server_status_label)
        self._set_server_controls_enabled(True)

        self._stop_discovery()

    def _on_server_error(self, message: str) -> None:
        self._server_had_error = True
        self._server_btn.setEnabled(True)
        self._server_btn.setText("Start Server")
        self._server_btn.setProperty("danger", False)
        self._server_btn.style().polish(self._server_btn)
        self._server_dot.setObjectName("statusDotInactive")
        self._server_dot.style().polish(self._server_dot)
        self._server_status_label.setText(message)
        self._server_status_label.setObjectName("dangerLabel")
        self._server_status_label.style().polish(self._server_status_label)
        self._set_server_controls_enabled(True)

    def _set_server_controls_enabled(self, enabled: bool) -> None:
        self._bind_edit.setEnabled(enabled)
        self._port_spin.setEnabled(enabled)
        self._mdns_cb.setEnabled(enabled and self._has_zeroconf())

    @staticmethod
    def _has_zeroconf() -> bool:
        from grouper_server.sync.discovery import HAS_ZEROCONF

        return HAS_ZEROCONF

    # -- quick connect ------------------------------------------------------

    def _on_connect(self) -> None:
        if self._client_worker is not None and self._client_worker.isRunning():
            return

        text = self._connect_edit.text().strip()
        host, port = self._parse_host_port(text)
        if host is None or port is None:
            self._connect_result.setText(f"Invalid address: {text!r}")
            self._connect_result.setObjectName("dangerLabel")
            self._connect_result.style().polish(self._connect_result)
            return

        self._connect_btn.setEnabled(False)
        self._connect_btn.setText("Syncing...")
        self._connect_result.setText("")

        db_path = get_database_path()
        self._client_worker = SyncClientWorker(db_path, host, port, parent=None)
        self._client_worker.success.connect(self._on_sync_success)
        self._client_worker.error.connect(self._on_sync_error)
        self._client_worker.cancelled.connect(self._on_sync_cancelled)
        self._client_worker.finished.connect(self._on_client_finished)
        self._client_worker.finished.connect(self._client_worker.deleteLater)
        self._client_worker.start()

    def _on_sync_success(self, sent: int, received: int) -> None:
        self._connect_result.setText(f"Sync complete — sent {sent}, received {received} changes")
        self._connect_result.setObjectName("successLabel")
        self._connect_result.style().polish(self._connect_result)
        self._refresh_status()

    def _on_sync_error(self, message: str) -> None:
        self._connect_result.setText(message)
        self._connect_result.setObjectName("dangerLabel")
        self._connect_result.style().polish(self._connect_result)

    def _on_sync_cancelled(self) -> None:
        self._connect_result.setText("Sync cancelled")
        self._connect_result.setObjectName("mutedLabel")
        self._connect_result.style().polish(self._connect_result)

    def _on_client_finished(self) -> None:
        self._client_worker = None
        self._connect_btn.setEnabled(True)
        self._connect_btn.setText("Connect")

    @staticmethod
    def _parse_host_port(text: str) -> tuple[str | None, int | None]:
        """Parse 'host:port' or bare 'host' into (host, port) or (None, None).

        If no port is given the default sync port (53987) is used.
        """
        from ..config import get_config

        default_port: int = get_config().sync_port

        if ":" not in text:
            host = text
            port = default_port
        else:
            host, _, port_str = text.rpartition(":")
            if not host or not port_str:
                return None, None
            try:
                port = int(port_str)
            except ValueError:
                return None, None
            if not 1 <= port <= 65535:
                return None, None
            if host.startswith("[") and host.endswith("]"):
                host = host[1:-1]

        if not host:
            return None, None
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if not re.fullmatch(
                r"[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?)*",
                host,
            ):
                return None, None
        return host, port

    # -- discovered peers (mDNS) --------------------------------------------

    def _start_discovery(self, device_id: str) -> None:
        if not self._has_zeroconf():
            return
        try:
            from grouper_server.sync.discovery import SyncBrowser

            browser = SyncBrowser(device_id)
            if browser.start():
                self._browser = browser
                self._discovery_timer.start()
        except Exception:
            log.warning("Failed to start mDNS browser")

    def _stop_discovery(self) -> None:
        self._discovery_timer.stop()
        if self._browser is not None:
            with contextlib.suppress(Exception):
                self._browser.stop()
            self._browser = None

        # Clear discovery UI
        if self._discovery_group is not None and hasattr(self, "_discovery_layout"):
            clear_layout(self._discovery_layout)
            empty = QLabel("Server stopped.")
            empty.setObjectName("mutedLabel")
            self._discovery_layout.addWidget(empty)

    def _poll_discovered_peers(self) -> None:
        if self._browser is None:
            return
        if not hasattr(self, "_discovery_layout"):
            return

        peers: list[Peer] = self._browser.peers
        clear_layout(self._discovery_layout)

        if not peers:
            empty = QLabel("No peers found on LAN yet...")
            empty.setObjectName("mutedLabel")
            self._discovery_layout.addWidget(empty)
            return

        for peer in peers:
            card = self._make_discovery_card(peer)
            self._discovery_layout.addWidget(card)

    def _make_discovery_card(self, peer: Peer) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)

        info_col = QVBoxLayout()
        name_label = QLabel(peer.device_name)
        name_label.setObjectName("cardTitle")
        info_col.addWidget(name_label)

        addr_label = QLabel(f"{peer.host}:{peer.port}")
        addr_label.setObjectName("mutedLabel")
        info_col.addWidget(addr_label)
        layout.addLayout(info_col, stretch=1)

        sync_btn = QPushButton("Sync")
        sync_btn.clicked.connect(
            lambda _=False, h=peer.host, p=peer.port: self._sync_with_discovered(h, p)
        )
        layout.addWidget(sync_btn)

        return card

    def _sync_with_discovered(self, host: str, port: int) -> None:
        """Trigger a sync with a discovered peer."""
        self._connect_edit.setText(f"{host}:{port}")
        self._on_connect()

    # -- cleanup ------------------------------------------------------------

    def _copy_device_id(self) -> None:
        full_id = self._device_id_label.property("_full_id")
        if full_id:
            clipboard = QApplication.clipboard()
            if clipboard is not None:
                clipboard.setText(full_id)

    def cleanup(self) -> None:
        """Stop all workers and discovery. Called on application quit."""
        self._stop_discovery()
        if self._server_worker is not None and self._server_worker.isRunning():
            self._server_worker.request_stop()
            self._server_worker.wait(5000)
        if self._client_worker is not None and self._client_worker.isRunning():
            self._client_worker.request_stop()
            self._client_worker.wait(5000)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.cleanup()
        super().closeEvent(event)
