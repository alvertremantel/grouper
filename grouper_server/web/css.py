"""Theme-aware CSS builder for the web dashboard.

Reads color tokens from the Grouper palette and generates CSS.
Thread-safe caching: rebuilds only when the theme changes.
"""

from __future__ import annotations

import threading

from grouper_core.colors import lerp_hex, theme_colors
from grouper_core.config import get_config

_css_cache: str | None = None
_css_theme_key: str | None = None
_css_lock = threading.Lock()


def get_css() -> str:
    """Return cached CSS for the current theme, rebuilding if needed."""
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
