"""Web sub-package -- Flask-based HTTP dashboard.

Public API: start_web_server(port) — starts the server in a daemon thread.
Requires Flask (``pip install flask``).
"""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)


def start_web_server(
    port: int = 4747,
    host: str = "127.0.0.1",
    *,
    behind_proxy: bool = False,
    url_prefix: str = "",
) -> None:
    """Start the Grouper web server in a daemon thread."""
    from .app import create_app

    app = create_app(port, behind_proxy=behind_proxy, url_prefix=url_prefix)
    _start_flask(app, port, host)


def _start_flask(app: object, port: int, host: str = "127.0.0.1") -> None:
    from werkzeug.serving import make_server

    server = make_server(host, port, app)  # type: ignore[arg-type]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("Grouper web server (Flask) running at http://%s:%d", host, port)
