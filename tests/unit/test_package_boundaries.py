"""Package boundary regression tests.

Verify that architectural boundaries are enforced at the import level:
- server/ does not import desktop or grouper_server
- desktop/ does not import server or grouper_server
- grouper_sync/ does not import desktop, server, or grouper_server
- No non-plan source/config file imports or references textual

Allow desktop to import grouper_sync (this is the intended coupling).
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from typing import ClassVar

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent


def _get_python_files(package_dir: Path) -> list[Path]:
    """Get all Python files under a package directory."""
    if not package_dir.exists():
        return []
    return list(package_dir.rglob("*.py"))


def _parse_imports(file_path: Path) -> tuple[set[str], set[str]]:
    """Parse a Python file and return (imported_modules, string_references).

    Returns:
        Tuple of (direct imports, string literals that look like module paths)
    """
    content = file_path.read_text(encoding="utf-8")

    try:
        tree = ast.parse(content)
    except SyntaxError:
        return set(), set()

    imports: set[str] = set()
    strings: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level > 0:
                # Relative import - resolve to absolute
                parts = file_path.relative_to(REPO_ROOT).parts
                # Remove 'tests' or package name prefix to find root
                if parts[0] in ("server", "desktop", "grouper_sync", "grouper_core"):
                    base = parts[0]
                elif parts[0] == "tests":
                    # Skip test files for boundary checking of source
                    continue
                else:
                    base = parts[0]
                imports.add(base)
            else:
                imports.add(module.split(".")[0])
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            strings.add(node.value)

    return imports, strings


class TestServerPackageBoundaries:
    """server/ must not import desktop, grouper_server, or textual."""

    @pytest.fixture
    def server_files(self) -> list[Path]:
        return _get_python_files(REPO_ROOT / "server")

    def test_server_does_not_import_desktop(self, server_files: list[Path]) -> None:
        """server/ must not import desktop."""
        violations = []
        for file_path in server_files:
            imports, _ = _parse_imports(file_path)
            if "desktop" in imports:
                violations.append(f"{file_path.relative_to(REPO_ROOT)} imports 'desktop'")
        assert not violations, "server/ imports desktop:\n" + "\n".join(violations)

    def test_server_does_not_import_grouper_server(self, server_files: list[Path]) -> None:
        """server/ must not import grouper_server (old package name)."""
        violations = []
        for file_path in server_files:
            imports, _ = _parse_imports(file_path)
            if "grouper_server" in imports:
                violations.append(f"{file_path.relative_to(REPO_ROOT)} imports 'grouper_server'")
        assert not violations, "server/ imports grouper_server:\n" + "\n".join(violations)

    def test_server_does_not_import_textual(self, server_files: list[Path]) -> None:
        """server/ must not import textual (TUI removed)."""
        violations = []
        for file_path in server_files:
            imports, strings = _parse_imports(file_path)
            if "textual" in imports:
                violations.append(f"{file_path.relative_to(REPO_ROOT)} imports 'textual'")
            # Also check string literals for textual references
            for s in strings:
                if "textual" in s.lower() and "grouper" not in s.lower():
                    violations.append(
                        f"{file_path.relative_to(REPO_ROOT)} references 'textual' in string: {s[:50]}"
                    )
        assert not violations, "server/ references textual:\n" + "\n".join(violations)


class TestDesktopPackageBoundaries:
    """desktop/ must not import server or grouper_server."""

    @pytest.fixture
    def desktop_files(self) -> list[Path]:
        return _get_python_files(REPO_ROOT / "desktop")

    def test_desktop_does_not_import_server(self, desktop_files: list[Path]) -> None:
        """desktop/ must not import server (circular dependency prevention)."""
        violations = []
        for file_path in desktop_files:
            imports, _ = _parse_imports(file_path)
            if "server" in imports:
                # Allow 'server' in test file names or as variable names, not imports
                violations.append(f"{file_path.relative_to(REPO_ROOT)} imports 'server'")
        assert not violations, "desktop/ imports server:\n" + "\n".join(violations)

    def test_desktop_does_not_import_grouper_server(self, desktop_files: list[Path]) -> None:
        """desktop/ must not import grouper_server (old package name)."""
        violations = []
        for file_path in desktop_files:
            imports, _ = _parse_imports(file_path)
            if "grouper_server" in imports:
                violations.append(f"{file_path.relative_to(REPO_ROOT)} imports 'grouper_server'")
        assert not violations, "desktop/ imports grouper_server:\n" + "\n".join(violations)

    def test_desktop_may_import_grouper_sync(self) -> None:
        """desktop/ SHOULD be able to import grouper_sync (expected coupling)."""
        # This is a positive test - verify the import works
        spec = importlib.util.find_spec("grouper_sync")
        assert spec is not None, "grouper_sync should be importable"

        # Verify desktop can import it
        sync_view_file = REPO_ROOT / "desktop" / "ui" / "views" / "sync_view.py"
        if sync_view_file.exists():
            imports, _ = _parse_imports(sync_view_file)
            # Should have grouper_sync imports (TYPE_CHECKING or runtime)
            assert "grouper_sync" in imports, "desktop sync view should import grouper_sync"


class TestGrouperSyncPackageBoundaries:
    """grouper_sync/ must not import desktop, server, or grouper_server."""

    @pytest.fixture
    def sync_files(self) -> list[Path]:
        return _get_python_files(REPO_ROOT / "grouper_sync")

    def test_grouper_sync_does_not_import_desktop(self, sync_files: list[Path]) -> None:
        """grouper_sync/ must not import desktop."""
        violations = []
        for file_path in sync_files:
            imports, _ = _parse_imports(file_path)
            if "desktop" in imports:
                violations.append(f"{file_path.relative_to(REPO_ROOT)} imports 'desktop'")
        assert not violations, "grouper_sync/ imports desktop:\n" + "\n".join(violations)

    def test_grouper_sync_does_not_import_server(self, sync_files: list[Path]) -> None:
        """grouper_sync/ must not import server."""
        violations = []
        for file_path in sync_files:
            imports, _ = _parse_imports(file_path)
            if "server" in imports:
                violations.append(f"{file_path.relative_to(REPO_ROOT)} imports 'server'")
        assert not violations, "grouper_sync/ imports server:\n" + "\n".join(violations)

    def test_grouper_sync_does_not_import_grouper_server(self, sync_files: list[Path]) -> None:
        """grouper_sync/ must not import grouper_server (old package name)."""
        violations = []
        for file_path in sync_files:
            imports, _ = _parse_imports(file_path)
            if "grouper_server" in imports:
                violations.append(f"{file_path.relative_to(REPO_ROOT)} imports 'grouper_server'")
        assert not violations, "grouper_sync/ imports grouper_server:\n" + "\n".join(violations)


class TestOldPackageNotImportable:
    """The old grouper_server package should no longer exist."""

    def test_grouper_server_not_importable(self) -> None:
        """grouper_server package should not be found."""
        spec = importlib.util.find_spec("grouper_server")
        assert spec is None, "grouper_server should not be importable after refactor"

    def test_server_is_importable(self) -> None:
        """server package should be importable."""
        spec = importlib.util.find_spec("server")
        assert spec is not None, "server should be importable"

    def test_grouper_sync_is_importable(self) -> None:
        """grouper_sync package should be importable."""
        spec = importlib.util.find_spec("grouper_sync")
        assert spec is not None, "grouper_sync should be importable"


class TestTextualRemoved:
    """Textual/TUI references should be removed from active source/config."""

    EXCLUDED_PATHS: ClassVar[tuple[str, ...]] = (
        ".venv",
        "__pycache__",
        ".agents/plans",
        ".agents/context",
        ".agents/reviews",
        "uv.lock",  # Will be regenerated separately
        "STATUS.md",
        "NOTES.md",
        "tests/",  # Test files are allowed to reference these for testing purposes
    )

    def _get_active_source_files(self) -> list[Path]:
        """Get Python and config files, excluding certain paths."""
        files = []
        for pattern in ["*.py", "*.toml", "*.txt", "*.bat"]:
            files.extend(REPO_ROOT.rglob(pattern))

        filtered = []
        for f in files:
            rel = str(f.relative_to(REPO_ROOT))
            if any(excl in rel for excl in self.EXCLUDED_PATHS):
                continue
            filtered.append(f)
        return filtered

    def test_no_textual_imports_in_source(self) -> None:
        """No active source file should import textual."""
        violations = []
        for file_path in self._get_active_source_files():
            # Skip this test file itself
            if file_path.name == "test_package_boundaries.py":
                continue
            try:
                content = file_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            # Check for actual textual imports (not docstrings mentioning it)
            lines = content.split("\n")
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                # Skip comments and docstrings
                if (
                    stripped.startswith("#")
                    or stripped.startswith('"""')
                    or stripped.startswith("'")
                ):
                    continue
                # Check for actual import statements
                if ("import textual" in line or "from textual" in line) and not stripped.startswith(
                    '"""'
                ):
                    violations.append(f"{file_path.relative_to(REPO_ROOT)}:{i} imports textual")

        assert not violations, "Active source files reference textual:\n" + "\n".join(violations)

    def test_no_no_tui_flag_in_cli(self) -> None:
        """The --no-tui flag should be removed from CLI."""
        cli_file = REPO_ROOT / "server" / "cli" / "main.py"
        if cli_file.exists():
            content = cli_file.read_text(encoding="utf-8")
            assert "--no-tui" not in content, "CLI still contains --no-tui flag"


class TestMonkeypatchPaths:
    """Tests should use correct monkeypatch paths."""

    def test_no_grouper_server_in_monkeypatch_strings(self) -> None:
        """No test file should monkeypatch 'grouper_server.*' paths (except boundary tests themselves)."""
        test_files = _get_python_files(REPO_ROOT / "tests")
        violations = []

        for file_path in test_files:
            # Skip the boundary test file itself - it's allowed to reference grouper_server
            if file_path.name == "test_package_boundaries.py":
                continue
            content = file_path.read_text(encoding="utf-8")
            # Look for actual monkeypatch paths like "grouper_server.sync.client"
            if "grouper_server.sync." in content:
                lines = content.split("\n")
                for i, line in enumerate(lines, 1):
                    if "grouper_server.sync." in line and not line.strip().startswith("#"):
                        violations.append(f"{file_path.relative_to(REPO_ROOT)}:{i}: {line.strip()}")

        assert not violations, (
            "Test files still reference grouper_server.sync in monkeypatch strings:\n"
            + "\n".join(violations)
        )
