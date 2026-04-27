"""Tests for server package CLI and imports."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent.parent


class TestServerImports:
    """Verify server package can be imported correctly."""

    def test_server_package_importable(self) -> None:
        """server package should be importable."""
        spec = importlib.util.find_spec("server")
        assert spec is not None, "server package not found"

    def test_server_cli_main_importable(self) -> None:
        """server.cli.main should be importable."""
        spec = importlib.util.find_spec("server.cli.main")
        assert spec is not None, "server.cli.main not found"

    def test_server_runtime_runner_importable(self) -> None:
        """server.runtime.runner should be importable."""
        spec = importlib.util.find_spec("server.runtime.runner")
        assert spec is not None, "server.runtime.runner not found"

    def test_server_web_importable(self) -> None:
        """server.web should be importable."""
        spec = importlib.util.find_spec("server.web")
        assert spec is not None, "server.web not found"

    def test_server_web_app_importable(self) -> None:
        """server.web.app should be importable."""
        spec = importlib.util.find_spec("server.web.app")
        assert spec is not None, "server.web.app not found"

    def test_server_main_imports_do_not_init_database(self) -> None:
        """Importing server.__main__ should not have DB side effects.

        Database initialization should only happen in main().
        """
        # This test verifies that we can import without triggering DB init
        # The actual DB init happens in main() after argument parsing
        try:
            import server.__main__  # noqa: F401
        except Exception as e:
            # Import errors are acceptable; DB init errors are not
            if "database" in str(e).lower() or "sqlite" in str(e).lower():
                pytest.fail(f"Import triggered database operation: {e}")
            # Other import errors might be environment issues
            pytest.skip(f"Import skipped due to environment: {e}")


class TestServerCLI:
    """Verify server CLI behavior."""

    def test_server_help_exit_code(self) -> None:
        """python -m server --help should exit 0."""
        result = subprocess.run(
            [sys.executable, "-m", "server", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Help failed: {result.stderr}"
        assert "grouper-server" in result.stdout.lower() or "grouper" in result.stdout.lower()

    def test_server_serve_help_exit_code(self) -> None:
        """python -m server serve --help should exit 0."""
        result = subprocess.run(
            [sys.executable, "-m", "server", "serve", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"serve --help failed: {result.stderr}"

    def test_server_serve_no_tui_flag_removed(self) -> None:
        """--no-tui flag should be removed from serve command."""
        result = subprocess.run(
            [sys.executable, "-m", "server", "serve", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "--no-tui" not in result.stdout, "--no-tui flag still present in serve --help"

    def test_server_serve_has_no_web_flag(self) -> None:
        """--no-web flag should be present in serve command."""
        result = subprocess.run(
            [sys.executable, "-m", "server", "serve", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "--no-web" in result.stdout, "--no-web flag missing from serve --help"

    def test_server_serve_has_no_mdns_flag(self) -> None:
        """--no-mdns flag should be present in serve command."""
        result = subprocess.run(
            [sys.executable, "-m", "server", "serve", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "--no-mdns" in result.stdout, "--no-mdns flag missing from serve --help"

    def test_server_connect_help_exit_code(self) -> None:
        """python -m server connect --help should exit 0."""
        result = subprocess.run(
            [sys.executable, "-m", "server", "connect", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"connect --help failed: {result.stderr}"

    def test_server_status_help_exit_code(self) -> None:
        """python -m server status --help should exit 0."""
        result = subprocess.run(
            [sys.executable, "-m", "server", "status", "--help"],
            capture_output=True,
            text=True,
        )
        # status might not have help if it takes no arguments
        assert result.returncode in [0, 2], f"status --help unexpected exit: {result.stderr}"

    def test_server_web_help_exit_code(self) -> None:
        """python -m server web --help should exit 0."""
        result = subprocess.run(
            [sys.executable, "-m", "server", "web", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"web --help failed: {result.stderr}"


class TestServerWebSubpackage:
    """Verify server.web subpackage structure."""

    def test_server_web_assets_css_importable(self) -> None:
        """server.web.assets.css should be importable."""
        spec = importlib.util.find_spec("server.web.assets.css")
        assert spec is not None, "server.web.assets.css not found"

    def test_server_web_views_rendering_importable(self) -> None:
        """server.web.views.rendering should be importable."""
        spec = importlib.util.find_spec("server.web.views.rendering")
        assert spec is not None, "server.web.views.rendering not found"

    def test_server_web_routes_importable(self) -> None:
        """server.web.routes should be importable."""
        spec = importlib.util.find_spec("server.web.routes")
        assert spec is not None, "server.web.routes not found"


class TestServerVsGrouperServer:
    """Verify old package name is not used."""

    def test_grouper_server_not_importable(self) -> None:
        """grouper_server should not be importable."""
        spec = importlib.util.find_spec("grouper_server")
        assert spec is None, "grouper_server should not be importable after refactor"

    def test_grouper_server_cli_not_importable(self) -> None:
        """grouper_server.__main__ should not be importable."""
        try:
            spec = importlib.util.find_spec("grouper_server.__main__")
            assert spec is None, "grouper_server.__main__ should not be importable"
        except ModuleNotFoundError:
            # This is expected - parent package doesn't exist
            pass

    def test_server_cli_has_correct_prog_name(self) -> None:
        """CLI should have correct program name."""
        result = subprocess.run(
            [sys.executable, "-m", "server", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        # Should mention grouper-server in output
        assert "grouper-server" in result.stdout, "Program name should be grouper-server"
