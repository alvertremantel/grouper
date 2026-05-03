"""
Entry point: python -m server

Commands:
    serve   Start sync + web servers
    connect One-shot sync with a peer
    status  Show sync status
    web     Start only the web server
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from typing import TYPE_CHECKING

from grouper_core.database.connection import get_database_path, init_database

if TYPE_CHECKING:
    from server.runtime.runner import ServerRunner


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="grouper-server",
        description="Grouper Server — unified sync + web dashboard",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    sub = parser.add_subparsers(dest="command")

    # ── serve ───────────────────────────────────────────────────────────
    serve_p = sub.add_parser("serve", help="Start sync + web servers")
    serve_p.add_argument(
        "--host",
        default="0.0.0.0",
        help="Sync server bind address (default: 0.0.0.0)",
    )
    serve_p.add_argument(
        "--sync-port",
        type=int,
        default=53987,
        help="Sync server port (default: 53987)",
    )
    serve_p.add_argument(
        "--web-host",
        default="127.0.0.1",
        help="Web server bind address (default: 127.0.0.1)",
    )
    serve_p.add_argument(
        "--web-port",
        type=int,
        default=4747,
        help="Web server port (default: 4747)",
    )
    serve_p.add_argument(
        "--no-mdns",
        action="store_true",
        help="Disable mDNS advertisement",
    )
    serve_p.add_argument(
        "--no-web",
        action="store_true",
        help="Disable web server",
    )
    serve_p.add_argument(
        "--behind-proxy",
        action="store_true",
        help="Enable reverse proxy support (trust X-Forwarded-* headers)",
    )
    serve_p.add_argument(
        "--url-prefix",
        default="",
        help="URL path prefix for sub-path hosting (e.g. /grouper)",
    )

    # ── connect ─────────────────────────────────────────────────────────
    conn_p = sub.add_parser("connect", help="Sync with a peer")
    conn_p.add_argument("address", help="Peer address as HOST:PORT")

    # ── status ──────────────────────────────────────────────────────────
    sub.add_parser("status", help="Show sync status")

    # ── web ─────────────────────────────────────────────────────────────
    web_p = sub.add_parser("web", help="Start only the web server")
    web_p.add_argument(
        "--host",
        default="127.0.0.1",
        help="Web server bind address (default: 127.0.0.1)",
    )
    web_p.add_argument(
        "--port",
        type=int,
        default=4747,
        help="Web server port (default: 4747)",
    )
    web_p.add_argument(
        "--behind-proxy",
        action="store_true",
        help="Enable reverse proxy support (trust X-Forwarded-* headers)",
    )
    web_p.add_argument(
        "--url-prefix",
        default="",
        help="URL path prefix for sub-path hosting (e.g. /grouper)",
    )

    args = parser.parse_args()

    init_database()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.command == "serve":
        _cmd_serve(args)
    elif args.command == "connect":
        _cmd_connect(args)
    elif args.command == "status":
        _cmd_status()
    elif args.command == "web":
        _cmd_web(args)
    else:
        parser.print_help()


def _cmd_serve(args: argparse.Namespace) -> None:
    from server.runtime.runner import ServerConfig, ServerRunner

    config = ServerConfig(
        sync_host=args.host,
        sync_port=args.sync_port,
        web_host=args.web_host,
        web_port=args.web_port,
        no_mdns=args.no_mdns,
        no_web=args.no_web,
        behind_proxy=args.behind_proxy,
        url_prefix=args.url_prefix,
    )
    runner = ServerRunner(config)

    # Headless mode only (TUI removed)
    _cmd_serve_headless(runner)


def _cmd_serve_headless(runner: ServerRunner) -> None:
    """Run servers with plain logging output."""

    async def run() -> None:
        runner.start_web()
        await runner.start_sync()

        s = runner.status
        print(f"Sync server running on {s.sync_host}:{s.sync_port}")
        if s.sync_device_id:
            print(f"Device: {s.sync_device_id[:8]}...")
        else:
            print("Device: (unknown)")
        if s.web_running:
            print(f"Web server running at http://{runner.config.web_host}:{s.web_port}")
        print("Press Ctrl+C to stop")

        try:
            await runner.serve_forever()
        except asyncio.CancelledError:
            pass
        finally:
            await runner.stop()

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\nStopped.")


def _cmd_connect(args: argparse.Namespace) -> None:
    from grouper_sync.changelog import ensure_triggers
    from grouper_sync.client import sync_with_peer
    from grouper_sync.device import enable_cdc

    host, _, port_str = args.address.rpartition(":")
    if not host or not port_str:
        print(f"Invalid address: {args.address!r} (expected HOST:PORT)", file=sys.stderr)
        sys.exit(1)

    try:
        port = int(port_str)
    except ValueError:
        print(
            f"Invalid port: {port_str!r} in address {args.address!r} (port must be an integer)",
            file=sys.stderr,
        )
        sys.exit(1)

    if not (1 <= port <= 65535):
        print(
            f"Invalid port {port} in address {args.address!r} (must be 1-65535)",
            file=sys.stderr,
        )
        sys.exit(1)

    db_path = get_database_path()

    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        enable_cdc(conn)
        ensure_triggers(conn)
    finally:
        conn.close()

    async def run() -> dict:
        return await sync_with_peer(db_path, host, port)

    result = asyncio.run(run())
    print(f"Sync complete: sent {result['sent']}, received {result['received']} changes")


def _cmd_status() -> None:
    import sqlite3

    db_path = get_database_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        if "sync_state" not in tables:
            print("Sync not initialized. Run 'serve' or 'connect' first.")
            return

        row = conn.execute("SELECT * FROM sync_state WHERE id = 1").fetchone()
        if row:
            print(f"Device ID:  {(row['device_id'] or '')[:8]}...")
            print(f"CDC active: {'yes' if not row['syncing'] else 'suppressed'}")
        else:
            print("Sync not initialized. Run 'serve' or 'connect' first.")
            return

        count = conn.execute("SELECT COUNT(*) FROM sync_changelog").fetchone()[0]
        print(f"Changelog:  {count} entries")

        peers = conn.execute("SELECT * FROM sync_peers").fetchall()
        if peers:
            print(f"\nKnown peers ({len(peers)}):")
            for p in peers:
                print(
                    f"  {p['peer_name'] or 'unknown'} ({(p['peer_device_id'] or '')[:8]}...) "
                    f"-- last sync: {p['last_sync_at'] or 'never'}, "
                    f"hwm: {p['last_changelog_id']}"
                )
        else:
            print("\nNo known peers yet.")
    finally:
        conn.close()


def _cmd_web(args: argparse.Namespace) -> None:
    """Start only the web server (blocking)."""
    import time

    from server.web import start_web_server

    start_web_server(
        args.port,
        args.host,
        behind_proxy=args.behind_proxy,
        url_prefix=args.url_prefix,
    )
    print(f"Web server running at http://{args.host}:{args.port}")
    print("Press Ctrl+C to stop")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
