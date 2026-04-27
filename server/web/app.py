"""Flask application factory."""

from __future__ import annotations

import re
import secrets
from pathlib import Path

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

_VALID_PREFIX_RE = re.compile(r"^/[a-zA-Z0-9_\-]+(/[a-zA-Z0-9_\-]+)*$")


def create_app(
    port: int = 4747,
    *,
    behind_proxy: bool = False,
    url_prefix: str = "",
) -> Flask:
    """Create and configure the Flask application."""
    template_dir = str(Path(__file__).parent / "templates")
    app = Flask(__name__, template_folder=template_dir)

    # Disable reloader/debugger — this runs as a daemon thread
    app.config["DEBUG"] = False
    app.config["SECRET_KEY"] = secrets.token_hex(32)
    app.config["WEB_PORT"] = port

    from . import routes

    routes.register(app)

    @app.after_request
    def _set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self' 'unsafe-inline'"
        )
        # Prevent stale HTML pages from being served by the proxy cache.
        # JSON API responses are left alone — browsers handle them correctly.
        if "text/html" in response.content_type:
            response.headers["Cache-Control"] = "no-cache"
        return response

    # Set SCRIPT_NAME so url_for() generates prefixed URLs (e.g. /grouper/dashboard).
    # Applied first so ProxyFix's X-Forwarded-Prefix can override if present.
    if url_prefix:
        prefix = "/" + url_prefix.strip("/")
        if prefix != "/" and not _VALID_PREFIX_RE.match(prefix):
            raise ValueError(
                f"Invalid url_prefix: {url_prefix!r}. "
                "Must be a simple path like '/grouper' or '/app/v1'."
            )
        app.wsgi_app = _PrefixMiddleware(app.wsgi_app, prefix)  # type: ignore[method-assign]

    if behind_proxy:
        # Trust one proxy hop for X-Forwarded-For, X-Forwarded-Proto,
        # X-Forwarded-Host, and X-Forwarded-Prefix so url_for() and
        # request.remote_addr are correct when hosted behind a reverse proxy.
        app.wsgi_app = ProxyFix(  # type: ignore[method-assign]
            app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1
        )

    return app


class _PrefixMiddleware:
    """WSGI middleware that sets SCRIPT_NAME for sub-path hosting."""

    __slots__ = ("_app", "_prefix")

    def __init__(self, app: object, prefix: str) -> None:
        self._app = app
        self._prefix = prefix

    def __call__(self, environ: dict, start_response: object) -> object:
        path: str = environ.get("PATH_INFO", "")
        if path.startswith(self._prefix):
            environ["PATH_INFO"] = path[len(self._prefix) :] or "/"
        environ["SCRIPT_NAME"] = self._prefix
        return self._app(environ, start_response)  # type: ignore[operator]
