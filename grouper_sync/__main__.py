"""
Entry point: python -m grouper_sync

Commands:
    serve [--host HOST] [--port PORT]   Start the sync server
    connect HOST:PORT                    One-shot sync with a peer
    status                               Show device ID and peer info
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from grouper_core.database.connection import get_database_path, init_database


def main() -> None:
    init_database()

    parser = argparse.ArgumentParser(
        prog="grouper-sync",
        description="Grouper LAN Sync — sync your data between devices",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    sub = parser.add_subparsers(dest="command")

    # ── serve ───────────────────────────────────────────────────────────
    serve_p = sub.add_parser("serve", help="Start the sync server")
    serve_p.add_argument(
        "--host",
        default="0.0.0.0",
        help="Bind address (default: 0.0.0.0)",
    )
    serve_p.add_argument(
        "--port",
        type=int,
        default=53987,
        help="Listen port (default: 53987)",
    )
    serve_p.add_argument(
        "--no-mdns",
        action="store_true",
        help="Disable mDNS advertisement",
    )

    # ── connect ─────────────────────────────────────────────────────────
    conn_p = sub.add_parser("connect", help="Sync with a peer")
    conn_p.add_argument(
        "address",
        help="Peer address as HOST:PORT",
    )

    # ── status ──────────────────────────────────────────────────────────
    sub.add_parser("status", help="Show sync status")

    args = parser.parse_args()

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
    else:
        parser.print_help()


def _cmd_serve(args: argparse.Namespace) -> None:
    import sqlite3

    from .device import get_or_create_device_id
    from .discovery import SyncAdvertiser
    from .server import SyncServer

    db_path = get_database_path()
    server = SyncServer(db_path, host=args.host, port=args.port)

    async def run() -> None:
        await server.start()
        port = server.actual_port

        advertiser: SyncAdvertiser | None = None
        if not args.no_mdns:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                device_id = get_or_create_device_id(conn)
            finally:
                conn.close()

            import socket

            advertiser = SyncAdvertiser(
                device_id=device_id,
                device_name=socket.gethostname(),
                port=port,
            )
            advertiser.start()

        print(f"Sync server running on {args.host}:{port}")
        print(f"Device: {server.device_id[:8]}...")
        print("Press Ctrl+C to stop")

        try:
            await server.serve_forever()
        except asyncio.CancelledError:
            pass
        finally:
            if advertiser:
                advertiser.stop()
            await server.stop()

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\nStopped.")


def _cmd_connect(args: argparse.Namespace) -> None:
    from .client import sync_with_peer

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

    # Ensure triggers are set up
    import sqlite3

    from .changelog import ensure_triggers
    from .device import enable_cdc

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
        # Check if sync tables exist
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

        # Changelog stats
        count = conn.execute("SELECT COUNT(*) FROM sync_changelog").fetchone()[0]
        print(f"Changelog:  {count} entries")

        # Peers
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


if __name__ == "__main__":
    main()
