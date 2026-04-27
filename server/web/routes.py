"""Flask route handlers for the Grouper web dashboard."""

from __future__ import annotations

import logging
from datetime import datetime

from flask import Flask, current_app, jsonify, redirect, render_template, url_for

from .assets.css import get_css
from .views.rendering import (
    due_span,
    fmt_hours,
    fmt_seconds,
    get_dashboard_data,
    get_summary_data,
    get_tasks_data,
    priority_chip,
)

logger = logging.getLogger(__name__)


def register(app: Flask) -> None:
    """Register all route handlers on the Flask app."""

    # Make helpers available in all templates
    @app.context_processor
    def inject_helpers() -> dict:
        return {
            "css": get_css(),
            "now": datetime.now(),
            "priority_chip": priority_chip,
            "due_span": due_span,
            "fmt_seconds": fmt_seconds,
            "fmt_hours": fmt_hours,
        }

    @app.route("/")
    def index():  # type: ignore[return]
        return redirect(url_for("dashboard"))

    @app.route("/dashboard")
    def dashboard():
        try:
            data = get_dashboard_data()
            return render_template("dashboard.html", **data, active_nav="dashboard")
        except Exception:
            logger.exception("Dashboard render failed")
            return (
                render_template(
                    "error.html",
                    error="An internal error occurred.",
                    active_nav="dashboard",
                ),
                500,
            )

    @app.route("/tasks")
    def tasks():
        try:
            data = get_tasks_data()
            return render_template("tasks.html", **data, active_nav="tasks")
        except Exception:
            logger.exception("Tasks render failed")
            return (
                render_template(
                    "error.html",
                    error="An internal error occurred.",
                    active_nav="tasks",
                ),
                500,
            )

    @app.route("/summary")
    def summary():
        try:
            data = get_summary_data()
            return render_template("summary.html", **data, active_nav="summary")
        except Exception:
            logger.exception("Summary render failed")
            return (
                render_template(
                    "error.html",
                    error="An internal error occurred.",
                    active_nav="summary",
                ),
                500,
            )

    @app.route("/api/status")
    def api_status():
        port: int = current_app.config.get("WEB_PORT", 4747)
        return jsonify({"ok": True, "port": port})

    @app.route("/api/sync/status")
    def api_sync_status():
        """Return sync server status as JSON."""
        import sqlite3

        from grouper_core.database.connection import get_database_path

        db_path = get_database_path()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            tables = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            if "sync_state" not in tables:
                return jsonify({"initialized": False})

            row = conn.execute("SELECT * FROM sync_state WHERE id = 1").fetchone()
            if not row:
                return jsonify({"initialized": False})

            changelog_count = conn.execute("SELECT COUNT(*) FROM sync_changelog").fetchone()[0]

            return jsonify(
                {
                    "initialized": True,
                    "device_id": (row["device_id"] or "")[:8],
                    "cdc_active": not row["syncing"],
                    "changelog_entries": changelog_count,
                }
            )
        finally:
            conn.close()

    @app.route("/api/sync/peers")
    def api_sync_peers():
        """Return list of known sync peers as JSON."""
        import sqlite3

        from grouper_core.database.connection import get_database_path

        db_path = get_database_path()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            tables = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            if "sync_peers" not in tables:
                return jsonify({"peers": []})

            peers = conn.execute("SELECT * FROM sync_peers").fetchall()
            return jsonify(
                {
                    "peers": [
                        {
                            "device_id": (p["peer_device_id"] or "")[:8],
                            "name": p["peer_name"] or "unknown",
                            "last_sync": p["last_sync_at"],
                            "hwm": p["last_changelog_id"],
                        }
                        for p in peers
                    ]
                }
            )
        finally:
            conn.close()

    @app.errorhandler(404)
    def not_found(e):
        return render_template("404.html", active_nav=""), 404
