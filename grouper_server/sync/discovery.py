"""
discovery.py — LAN peer discovery via mDNS/Zeroconf.

Optional dependency: if ``zeroconf`` is not installed, discovery is
disabled and the user must specify peer addresses manually.

**Tailscale / VPN limitation:** mDNS relies on link-local multicast
(224.0.0.251), which Tailscale and most VPN tunnels do not relay between
nodes.  Two Grouper instances on different Tailscale nodes will *not*
discover each other automatically — they must be added as manual peers
via ``grouper-server connect HOST:PORT``.  Use ``--no-mdns`` to disable
advertisement entirely when running in a Tailscale-only environment.
"""

from __future__ import annotations

import contextlib
import logging
import socket
import threading
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

SERVICE_TYPE = "_grouper-sync._tcp.local."

try:
    from zeroconf import ServiceBrowser, ServiceInfo, Zeroconf  # type: ignore[import-untyped]

    HAS_ZEROCONF = True
except ImportError:
    HAS_ZEROCONF = False


@dataclass
class Peer:
    """A discovered sync peer on the LAN."""

    device_id: str
    device_name: str
    host: str
    port: int


@dataclass
class SyncAdvertiser:
    """Advertise this device's sync server on the LAN via mDNS."""

    device_id: str
    device_name: str
    port: int
    _zc: Any = field(default=None, repr=False)
    _info: Any = field(default=None, repr=False)

    def start(self) -> bool:
        if not HAS_ZEROCONF:
            log.warning("zeroconf not installed — LAN advertisement disabled")
            return False
        try:
            self._zc = Zeroconf()
            local_ip = _get_local_ip()
            self._info = ServiceInfo(
                SERVICE_TYPE,
                f"Grouper-{self.device_id[:8]}.{SERVICE_TYPE}",
                addresses=[socket.inet_aton(local_ip)],
                port=self.port,
                properties={
                    b"device_id": self.device_id.encode(),
                    b"device_name": self.device_name.encode(),
                },
            )
            self._zc.register_service(self._info)
            log.info("Advertising sync on %s:%d", local_ip, self.port)
            log.info("mDNS advertisement active (LAN only — does not work across Tailscale/VPN)")
            return True
        except Exception:
            log.exception("Failed to start mDNS advertisement")
            return False

    def stop(self) -> None:
        if self._zc and self._info:
            with contextlib.suppress(Exception):
                self._zc.unregister_service(self._info)
            self._zc.close()
            self._zc = None
            self._info = None


class SyncBrowser:
    """Browse the LAN for Grouper sync peers via mDNS."""

    def __init__(self, own_device_id: str) -> None:
        self._own_id = own_device_id
        self._peers: dict[str, Peer] = {}
        self._lock = threading.Lock()
        self._zc: Any = None
        self._browser: Any = None

    @property
    def peers(self) -> list[Peer]:
        with self._lock:
            return list(self._peers.values())

    def start(self) -> bool:
        if not HAS_ZEROCONF:
            log.warning("zeroconf not installed — LAN discovery disabled")
            return False
        try:
            self._zc = Zeroconf()
            self._browser = ServiceBrowser(self._zc, SERVICE_TYPE, handlers=[self._on_change])
            log.info("mDNS discovery active (LAN only — does not work across Tailscale/VPN)")
            return True
        except Exception:
            log.exception("Failed to start mDNS browser")
            return False

    def stop(self) -> None:
        if self._browser:
            self._browser.cancel()
            self._browser = None
        if self._zc:
            self._zc.close()
            self._zc = None
        with self._lock:
            self._peers.clear()

    def _on_change(
        self,
        zeroconf: Any,
        service_type: str,
        name: str,
        state_change: Any,
    ) -> None:
        from zeroconf import ServiceStateChange  # type: ignore[import-untyped]

        if state_change == ServiceStateChange.Added:
            info = zeroconf.get_service_info(service_type, name)
            if info is None:
                return
            props = {
                k.decode(): v.decode() if isinstance(v, bytes) else v
                for k, v in (info.properties or {}).items()
            }
            device_id = props.get("device_id", "")
            if device_id == self._own_id:
                return  # don't discover ourselves

            addresses = info.parsed_addresses()
            if not addresses:
                return

            peer = Peer(
                device_id=device_id,
                device_name=props.get("device_name", name),
                host=addresses[0],
                port=info.port,
            )
            with self._lock:
                self._peers[device_id] = peer
            log.info("Discovered peer: %s at %s:%d", peer.device_name, peer.host, peer.port)

        elif state_change == ServiceStateChange.Removed:
            # Try to find and remove by service name
            with self._lock:
                to_remove = [
                    did for did, p in self._peers.items() if name.startswith(f"Grouper-{did[:8]}")
                ]
                for did in to_remove:
                    del self._peers[did]
            for did in to_remove:
                log.info("Peer removed: %s", did[:8])


def _get_local_ip() -> str:
    """Best-effort local IP address (not 127.0.0.1).

    Uses a UDP connect probe to discover the default outbound interface,
    which is typically the physical LAN adapter — the correct address for
    mDNS advertisement since mDNS only works on the local network.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()
