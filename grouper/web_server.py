"""
web_server.py — Lightweight HTTP server for desktop Grouper HTML readouts.

Serves live HTML panels on http://localhost:<port>/ that mirror the Qt UI tabs.
Started as a daemon thread so it exits automatically when the main process exits.

This module is intentionally desktop-local. The standalone server package keeps
its own Flask-based web dashboard under ``grouper_server.web``.

Routes:
    GET /                → redirect to /dashboard
    GET /dashboard       → active sessions + upcoming tasks (auto-refresh 5s)
    GET /tasks           → all boards → projects → tasks (auto-refresh 30s)
    GET /summary         → 7-day time summary + task stats (auto-refresh 30s)
    GET /api/status      → JSON health check {"ok": true, "port": N}
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timedelta
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import cast

from .config import get_config
from .styles import lerp_hex, theme_colors

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Display-limit constants
# ---------------------------------------------------------------------------

_DASHBOARD_UPCOMING_LIMIT = 10
_DASHBOARD_DISPLAY_LIMIT = 8
_SUMMARY_TOP_ACTIVITIES = 10
_SUMMARY_DEFAULT_DAYS = 7

# ---------------------------------------------------------------------------
# Shared CSS (theme-aware, cached)
# ---------------------------------------------------------------------------

_css_cache: str | None = None
_css_theme_key: str | None = None
_css_lock = threading.Lock()


def _get_css() -> str:
    global _css_cache, _css_theme_key
    with _css_lock:
        current_theme = get_config().theme
        if _css_cache is None or _css_theme_key != current_theme:
            _css_cache = _build_css()
            _css_theme_key = current_theme
        return _css_cache


def _build_css() -> str:
    """Build the web server CSS from the active theme palette."""
    p = theme_colors(get_config().theme)

    # Derive tinted badge/chip backgrounds from the palette
    bg = p["bg-primary"]
    badge_run_bg = lerp_hex(bg, p["success"], 0.08)
    badge_pause_bg = lerp_hex(bg, p["warning"], 0.08)
    badge_done_bg = lerp_hex(bg, p["accent"], 0.08)
    p1_bg = lerp_hex(bg, p["danger"], 0.12)
    p2_bg = lerp_hex(bg, p["warning"], 0.08)
    p3_bg = lerp_hex(bg, p["accent"], 0.08)
    p4_bg = lerp_hex(bg, p["text-muted"], 0.10)
    board_bg = lerp_hex(bg, p["bg-secondary"], 0.30)

    return f"""
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    body {{
        font-family: "Cascadia Mono", "Consolas", monospace;
        background: {p["bg-primary"]};
        color: {p["text"]};
        font-size: 13px;
        padding: 16px;
        line-height: 1.5;
    }}

    h1 {{ font-size: 16px; color: {p["accent"]}; margin-bottom: 12px; font-weight: 600; }}
    h2 {{ font-size: 13px; color: {p["accent"]}; margin: 16px 0 8px; font-weight: 600; }}
    h3 {{ font-size: 12px; color: {p["text-muted"]}; margin: 12px 0 6px; font-weight: 500; text-transform: uppercase; letter-spacing: 0.04em; }}

    .page-header {{
        display: flex;
        align-items: baseline;
        gap: 12px;
        margin-bottom: 16px;
        padding-bottom: 10px;
        border-bottom: 1px solid {p["border"]};
    }}
    .page-header .ts {{
        font-size: 11px;
        color: {p["text-muted"]};
    }}

    .card {{
        background: {p["bg-secondary"]};
        border: 1px solid {p["border"]};
        border-radius: 6px;
        padding: 12px 14px;
        margin-bottom: 8px;
    }}
    .card:last-child {{ margin-bottom: 0; }}

    .card-title {{
        font-size: 13px;
        color: {p["text"]};
        font-weight: 500;
    }}
    .card-meta {{
        font-size: 11px;
        color: {p["text-muted"]};
        margin-top: 3px;
    }}
    .card-row {{
        display: flex;
        justify-content: space-between;
        align-items: center;
    }}

    .timer {{
        font-size: 14px;
        font-weight: 600;
        color: {p["success"]};
        font-variant-numeric: tabular-nums;
    }}
    .timer.paused {{ color: {p["warning"]}; }}

    .badge {{
        display: inline-block;
        padding: 1px 7px;
        border-radius: 4px;
        font-size: 10px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }}
    .badge-running  {{ background: {badge_run_bg}; color: {p["success"]}; border: 1px solid {p["success"]}44; }}
    .badge-paused   {{ background: {badge_pause_bg}; color: {p["warning"]}; border: 1px solid {p["warning"]}44; }}
    .badge-complete {{ background: {badge_done_bg}; color: {p["accent"]}; border: 1px solid {p["accent"]}44; }}

    .priority-chip {{
        display: inline-block;
        padding: 1px 6px;
        border-radius: 3px;
        font-size: 10px;
        font-weight: 600;
        margin-right: 4px;
    }}
    .p1 {{ background: {p1_bg}; color: {p["danger"]}; border: 1px solid {p["danger"]}44; }}
    .p2 {{ background: {p2_bg}; color: {p["warning"]}; border: 1px solid {p["warning"]}44; }}
    .p3 {{ background: {p3_bg}; color: {p["accent"]}; border: 1px solid {p["accent"]}44; }}
    .p4 {{ background: {p4_bg}; color: {p["text-muted"]}; border: 1px solid {p["border"]}; }}

    .due-date {{ font-size: 11px; color: {p["text-muted"]}; }}
    .due-overdue {{ color: {p["danger"]}; font-weight: 600; }}
    .due-today   {{ color: {p["warning"]}; font-weight: 600; }}
    .due-soon    {{ color: {p["accent"]}; }}

    .section {{ margin-bottom: 20px; }}

    .empty-state {{
        color: {p["text-muted"]};
        font-size: 12px;
        padding: 12px 0;
        font-style: italic;
    }}

    .stat-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
        gap: 8px;
        margin-bottom: 16px;
    }}
    .stat-card {{
        background: {p["bg-secondary"]};
        border: 1px solid {p["border"]};
        border-radius: 6px;
        padding: 10px 12px;
    }}
    .stat-label {{ font-size: 10px; color: {p["text-muted"]}; text-transform: uppercase; letter-spacing: 0.05em; }}
    .stat-value {{ font-size: 18px; font-weight: 700; color: {p["accent"]}; margin-top: 2px; }}

    .bar-row {{
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 5px;
    }}
    .bar-label {{ width: 130px; font-size: 11px; color: {p["text"]}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex-shrink: 0; }}
    .bar-bg {{ flex: 1; height: 8px; background: {p["bg-tertiary"]}; border-radius: 4px; overflow: hidden; }}
    .bar-fill {{ height: 100%; background: {p["accent"]}; border-radius: 4px; }}
    .bar-time {{ width: 64px; font-size: 11px; color: {p["text-muted"]}; text-align: right; flex-shrink: 0; font-variant-numeric: tabular-nums; }}

    .board-section {{
        background: {board_bg};
        border: 1px solid {p["border"]};
        border-radius: 6px;
        padding: 12px 14px;
        margin-bottom: 12px;
    }}
    .board-label {{
        font-size: 11px;
        color: {p["text-muted"]};
        text-transform: uppercase;
        letter-spacing: 0.06em;
        font-weight: 600;
        margin-bottom: 10px;
        padding-bottom: 6px;
        border-bottom: 1px solid {p["border"]};
    }}
    .project-block {{ margin-bottom: 10px; }}
    .project-block:last-child {{ margin-bottom: 0; }}

    a {{ color: {p["accent"]}; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}

    .nav {{
        display: flex;
        gap: 4px;
        margin-bottom: 16px;
    }}
    .nav a {{
        padding: 4px 12px;
        border-radius: 4px;
        font-size: 12px;
        color: {p["text-muted"]};
        border: 1px solid {p["border"]};
        background: {p["bg-secondary"]};
    }}
    .nav a.active, .nav a:hover {{
        color: {p["text"]};
        border-color: {p["accent"]};
        background: {p["bg-tertiary"]};
    }}
    """


def _html_page(
    title: str, active_nav: str, body: str, refresh: int = 0, now: datetime | None = None
) -> str:
    ts = now or datetime.now()
    refresh_tag = f'<meta http-equiv="refresh" content="{refresh}">' if refresh else ""
    nav_links = ""
    for label, path in [("Dashboard", "/dashboard"), ("Tasks", "/tasks"), ("Summary", "/summary")]:
        cls = ' class="active"' if active_nav == path else ""
        nav_links += f'<a href="{path}"{cls}>{label}</a>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
{refresh_tag}
<title>Grouper — {escape(title)}</title>
<style>{_get_css()}</style>
</head>
<body>
<div class="page-header">
<h1>Grouper</h1>
<span class="ts">{ts.strftime("%Y-%m-%d %H:%M:%S")}</span>
</div>
<nav class="nav">{nav_links}</nav>
{body}
</body>
</html>"""


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _fmt_seconds(secs: int) -> str:
    h, r = divmod(secs, 3600)
    m, s = divmod(r, 60)
    return f"{h}h {m:02d}m {s:02d}s"


def _fmt_hours(secs: int) -> str:
    h = secs / 3600
    return f"{h:.1f}h"


def _priority_chip(priority: int) -> str:
    labels = {1: "P1", 2: "P2", 3: "P3", 4: "P4"}
    css_cls = {1: "p1", 2: "p2", 3: "p3", 4: "p4"}
    if priority not in labels:
        return ""
    return f'<span class="priority-chip {css_cls[priority]}">{labels[priority]}</span>'


def _due_span(due_date: datetime | None, now: datetime | None = None) -> str:
    if due_date is None:
        return ""
    today = (now or datetime.now()).date()
    d = due_date.date() if isinstance(due_date, datetime) else due_date
    delta = (d - today).days
    if delta < 0:
        css = "due-overdue"
        label = f"overdue {abs(delta)}d"
    elif delta == 0:
        css = "due-today"
        label = "due today"
    elif delta <= 3:
        css = "due-soon"
        label = f"due {d.strftime('%b %d')}"
    else:
        css = "due-date"
        label = d.strftime("%b %d")
    return f'<span class="{css}">{label}</span>'


def _task_card(
    title: str,
    priority: int,
    due_date: datetime | None,
    meta: str = "",
    now: datetime | None = None,
) -> str:
    """Render an HTML card for a task with priority chip, due span, and optional metadata."""
    meta_html = (
        f'\n  <div class="card-meta" style="margin-top:3px">{escape(meta)}</div>' if meta else ""
    )
    return f"""
<div class="card">
  <div class="card-row">
    <span class="card-title">{_priority_chip(priority)}{escape(title)}</span>
    {_due_span(due_date, now=now)}
  </div>{meta_html}
</div>"""


# ---------------------------------------------------------------------------
# Page renderers
# ---------------------------------------------------------------------------


def _render_dashboard(now: datetime | None = None) -> str:
    from .database.projects import get_project_by_id
    from .database.sessions import get_active_sessions
    from .database.tasks import get_tasks_with_due_dates

    now = now or datetime.now()
    active = get_active_sessions()
    upcoming = get_tasks_with_due_dates()[:_DASHBOARD_UPCOMING_LIMIT]

    # --- Active sessions section ---
    sessions_html = ""
    if not active:
        sessions_html = '<p class="empty-state">No active sessions.</p>'
    else:
        for s in active:
            badge_cls = "badge-paused" if s.is_paused else "badge-running"
            badge_label = "Paused" if s.is_paused else "Running"
            timer_cls = "timer paused" if s.is_paused else "timer"
            sessions_html += f"""
<div class="card">
  <div class="card-row">
    <span class="card-title">{escape(s.activity_name)}</span>
    <span class="{timer_cls}">{s.format_duration()}</span>
  </div>
  <div class="card-row" style="margin-top:4px">
    <span class="card-meta">{s.start_time.strftime("%H:%M") if s.start_time else ""}</span>
    <span class="badge {badge_cls}">{badge_label}</span>
  </div>
</div>"""

    # --- Upcoming tasks section (batch-load projects to avoid N+1) ---
    tasks_html = ""
    if not upcoming:
        tasks_html = '<p class="empty-state">No tasks with due dates.</p>'
    else:
        display_tasks = upcoming[:_DASHBOARD_DISPLAY_LIMIT]
        project_ids = {t.project_id for t in display_tasks}
        project_map: dict[int, str] = {}
        for pid in project_ids:
            proj = get_project_by_id(pid)
            project_map[pid] = proj.name if proj else f"#{pid}"
        for t in display_tasks:
            proj_name = project_map.get(t.project_id, f"#{t.project_id}")
            tasks_html += _task_card(t.title, t.priority, t.due_date, meta=proj_name, now=now)

    body = f"""
<div class="section">
  <h2>Active Sessions <span class="badge badge-running">{len(active)}</span></h2>
  {sessions_html}
</div>
<div class="section">
  <h2>Upcoming Tasks</h2>
  {tasks_html}
</div>"""

    return _html_page("Dashboard", "/dashboard", body, refresh=5, now=now)


def _render_tasks(now: datetime | None = None) -> str:
    from .database.boards import list_boards
    from .database.projects import list_projects
    from .database.tasks import get_tasks_by_board

    now = now or datetime.now()
    boards = list_boards()
    body = ""

    for board in boards:
        if board.id is None:
            continue
        projects = list_projects(board_id=board.id)
        if not projects:
            continue

        # Batch-load all tasks for this board (avoids N+1 per-project queries)
        all_board_tasks = [t for t in get_tasks_by_board(board.id) if not t.is_completed]
        tasks_by_project: dict[int, list] = {}
        for t in all_board_tasks:
            tasks_by_project.setdefault(t.project_id, []).append(t)

        projects_html = ""
        total_tasks = 0
        for proj in projects:
            if proj.id is None:
                continue
            tasks = tasks_by_project.get(proj.id, [])
            total_tasks += len(tasks)
            if not tasks:
                continue
            task_items = ""
            for t in tasks:
                task_items += _task_card(t.title, t.priority, t.due_date, now=now)
            projects_html += f"""
<div class="project-block">
  <h3>{escape(proj.name)}</h3>
  {task_items}
</div>"""

        if not projects_html:
            projects_html = '<p class="empty-state">No open tasks.</p>'

        body += f"""
<div class="board-section">
  <div class="board-label">{escape(board.name)} &mdash; {total_tasks} open task{"s" if total_tasks != 1 else ""}</div>
  {projects_html}
</div>"""

    if not body:
        body = '<p class="empty-state">No boards found.</p>'

    return _html_page("Tasks", "/tasks", body, refresh=30, now=now)


def _render_summary(now: datetime | None = None) -> str:
    from .database.sessions import get_summary
    from .database.tasks import get_tasks_with_due_dates

    now = now or datetime.now()
    p = theme_colors(get_config().theme)
    end = now
    start = end - timedelta(days=_SUMMARY_DEFAULT_DAYS)
    totals = get_summary(start_date=start, end_date=end)

    total_secs = sum(totals.values())
    top = sorted(totals.items(), key=lambda x: x[1], reverse=True)[:_SUMMARY_TOP_ACTIVITIES]
    max_secs = top[0][1] if top else 1

    # Task stats
    upcoming = get_tasks_with_due_dates()
    today = now.date()
    overdue = [t for t in upcoming if t.due_date and t.due_date.date() < today]
    due_today = [t for t in upcoming if t.due_date and t.due_date.date() == today]

    # Stats grid
    stats_html = f"""
<div class="stat-grid">
  <div class="stat-card">
    <div class="stat-label">Total ({_SUMMARY_DEFAULT_DAYS} days)</div>
    <div class="stat-value">{_fmt_hours(total_secs)}</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">Activities tracked</div>
    <div class="stat-value">{len(totals)}</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">Open tasks</div>
    <div class="stat-value">{len(upcoming)}</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">Overdue</div>
    <div class="stat-value" style="color:{p["danger"]}">{len(overdue)}</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">Due today</div>
    <div class="stat-value" style="color:{p["warning"]}">{len(due_today)}</div>
  </div>
</div>"""

    # Bar chart
    bars_html = ""
    if not top:
        bars_html = '<p class="empty-state">No sessions in the last 7 days.</p>'
    else:
        for name, secs in top:
            pct = int(secs / max_secs * 100)
            safe_name = escape(name)
            bars_html += f"""
<div class="bar-row">
  <span class="bar-label" title="{escape(name, quote=True)}">{safe_name}</span>
  <div class="bar-bg"><div class="bar-fill" style="width:{pct}%"></div></div>
  <span class="bar-time">{_fmt_seconds(secs)}</span>
</div>"""

    body = f"""
<div class="section">
  <h2>Last {_SUMMARY_DEFAULT_DAYS} Days</h2>
  {stats_html}
</div>
<div class="section">
  <h2>Time by Activity</h2>
  {bars_html}
</div>"""

    return _html_page("Summary", "/summary", body, refresh=30, now=now)


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------


class _GrouperHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = self.path.split("?")[0]

        if path == "/":
            self._redirect("/dashboard")
        elif path == "/dashboard":
            try:
                self._html(_render_dashboard())
            except Exception as e:
                logger.exception("Dashboard render failed")
                self._html(
                    _html_page(
                        "Error",
                        path,
                        f'<p class="empty-state">Something went wrong: {escape(str(e))}</p>',
                    )
                )
        elif path == "/tasks":
            try:
                self._html(_render_tasks())
            except Exception as e:
                logger.exception("Tasks render failed")
                self._html(
                    _html_page(
                        "Error",
                        path,
                        f'<p class="empty-state">Something went wrong: {escape(str(e))}</p>',
                    )
                )
        elif path == "/summary":
            try:
                self._html(_render_summary())
            except Exception as e:
                logger.exception("Summary render failed")
                self._html(
                    _html_page(
                        "Error",
                        path,
                        f'<p class="empty-state">Something went wrong: {escape(str(e))}</p>',
                    )
                )
        elif path == "/api/status":
            server_address = cast(tuple[str, int], self.server.server_address)
            self._json({"ok": True, "port": server_address[1]})
        else:
            self._not_found()

    # -- response helpers ----------------------------------------------------

    def _html(self, content: str) -> None:
        data = content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, payload: dict) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _redirect(self, location: str) -> None:
        self.send_response(302)
        self.send_header("Location", location)
        self.end_headers()

    def _not_found(self) -> None:
        body = b"404 Not Found"
        self.send_response(404)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:  # suppress default access log
        pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def start_web_server(port: int = 4747) -> None:
    """Start the Grouper HTTP server in a daemon thread.

    Returns immediately; the server runs until the process exits.
    """
    server = ThreadingHTTPServer(("127.0.0.1", port), _GrouperHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("Grouper web server running at http://localhost:%d", port)
