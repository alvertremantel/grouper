"""Textual TUI application for the unified Grouper server."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime
from typing import ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Footer, Header, RichLog, Static

from ..runner import ServerRunner

logger = logging.getLogger(__name__)


class StatusPanel(Static):
    """Displays server status information."""

    DEFAULT_CSS = """
    StatusPanel {
        width: 1fr;
        height: auto;
        min-height: 5;
        border: solid $accent;
        padding: 1 2;
        margin: 0 1;
    }
    """

    def __init__(self, title: str, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._title = title

    def update_status(self, lines: list[str]) -> None:
        content = f"[bold]{self._title}[/bold]\n" + "\n".join(lines)
        self.update(content)


class ServerTUI(App):
    """Terminal UI for the unified Grouper server."""

    TITLE = "Grouper Server"

    CSS = """
    Screen {
        layout: vertical;
    }

    #status-bar {
        height: auto;
        min-height: 5;
        max-height: 8;
        margin: 1 0;
    }

    #log-panel {
        height: 1fr;
        border: solid $accent;
        margin: 0 1 1 1;
    }
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("q", "quit", "Quit", show=True),
        Binding("c", "clear_logs", "Clear Logs", show=True),
    ]

    def __init__(self, runner: ServerRunner, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._runner = runner
        self._sync_panel = StatusPanel("Sync Server", id="sync-status")
        self._web_panel = StatusPanel("Web Server", id="web-status")
        self._log = RichLog(id="log-panel", highlight=True, markup=True)
        self._update_timer: asyncio.TimerHandle | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="status-bar"):
            yield self._sync_panel
            yield self._web_panel
        yield self._log
        yield Footer()

    async def on_mount(self) -> None:
        # Install custom log handler that writes to the RichLog widget
        handler = _TUILogHandler(self._log, self)
        logging.root.addHandler(handler)
        logging.root.setLevel(logging.INFO)

        # Start the web server (daemon thread)
        self._runner.start_web()

        # Start the sync server as an async task
        self._sync_task = asyncio.create_task(self._run_sync())

        # Start periodic status updates
        self.set_interval(1.0, self._refresh_status)

    async def _run_sync(self) -> None:
        try:
            await self._runner.start_sync()
            await self._runner.serve_forever()
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Sync server error")
        finally:
            await self._runner.stop()

    def _refresh_status(self) -> None:
        s = self._runner.status

        # Sync panel
        if s.sync_running:
            uptime = ""
            if s.started_at:
                delta = datetime.now() - s.started_at
                mins = int(delta.total_seconds()) // 60
                secs = int(delta.total_seconds()) % 60
                uptime = f"{mins}m {secs:02d}s"
            self._sync_panel.update_status(
                [
                    f"[green]\u25cf running[/green]  {s.sync_host}:{s.sync_port}",
                    f"Device:  {s.sync_device_id[:8]}...",
                    f"Uptime:  {uptime}",
                ]
            )
        else:
            self._sync_panel.update_status(
                [
                    "[dim]\u25cb stopped[/dim]",
                ]
            )

        # Web panel
        if s.web_running:
            self._web_panel.update_status(
                [
                    f"[green]\u25cf running[/green]  {self._runner.config.web_host}:{s.web_port}",
                    f"URL:     http://{self._runner.config.web_host}:{s.web_port}",
                ]
            )
        else:
            self._web_panel.update_status(
                [
                    "[dim]\u25cb stopped[/dim]",
                ]
            )

    def action_clear_logs(self) -> None:
        self._log.clear()

    async def action_quit(self) -> None:
        if hasattr(self, "_sync_task"):
            self._sync_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._sync_task
        await self._runner.stop()
        self.exit()


class _TUILogHandler(logging.Handler):
    """Routes log records to the Textual RichLog widget."""

    def __init__(self, log_widget: RichLog, app: App) -> None:
        super().__init__()
        self._log = log_widget
        self._app = app
        self.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%H:%M:%S",
            )
        )

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            # Color by level
            if record.levelno >= logging.ERROR:
                msg = f"[red]{msg}[/red]"
            elif record.levelno >= logging.WARNING:
                msg = f"[yellow]{msg}[/yellow]"
            elif record.levelno >= logging.INFO:
                msg = f"[dim]{msg}[/dim]"

            self._app.call_from_thread(self._log.write, msg)
        except Exception:
            self.handleError(record)
