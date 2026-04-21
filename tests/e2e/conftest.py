"""conftest.py -- E2E fixtures for tests that launch the full Grouper app.

Provides subprocess launch, pywinauto connection, and screenshot capture.
"""

import os
import subprocess
import sys
import time
from collections.abc import Generator
from datetime import datetime
from pathlib import Path

import psutil
import pytest
from pywinauto import Application

PROJECT_ROOT = Path(__file__).parent.parent.parent


@pytest.fixture
def app_process(test_data_dir: Path) -> Generator[subprocess.Popen, None, None]:
    """Launch Grouper in a subprocess with an isolated test database."""
    env = os.environ.copy()
    env["GROUPER_DATA_DIR"] = str(test_data_dir)
    env["GROUPER_KEEP_CONSOLE"] = "1"

    proc = subprocess.Popen(
        [sys.executable, "-m", "grouper"],
        cwd=str(PROJECT_ROOT),
        env=env,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )

    time.sleep(3)
    assert proc.poll() is None, "App process exited prematurely"

    yield proc

    try:
        parent = psutil.Process(proc.pid)
        for child in parent.children(recursive=True):
            child.kill()
        parent.kill()
        parent.wait(timeout=5)
    except (psutil.NoSuchProcess, psutil.TimeoutExpired):
        pass


@pytest.fixture
def app(app_process: subprocess.Popen) -> Application:
    """Connect pywinauto to the running Grouper window using UIA backend."""
    uia_app = Application(backend="uia")
    uia_app.connect(process=app_process.pid, timeout=10)
    return uia_app


@pytest.fixture
def main_window(app: Application):
    """Return the main Grouper window, maximized and ready for interaction."""
    win = app.window(title_re="Grouper.*Productivity Hub")
    win.wait("visible", timeout=10)
    win.maximize()
    return win


# ---------------------------------------------------------------------------
# Screenshot capture
# ---------------------------------------------------------------------------


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--screenshot-dir",
        default=None,
        help="Directory for persistent screenshot output (default: tmp_path)",
    )


@pytest.fixture
def screenshot_dir(request: pytest.FixtureRequest, tmp_path: Path) -> Path:
    """Resolve screenshot output directory."""
    custom = request.config.getoption("--screenshot-dir")
    if custom:
        d = Path(custom)
        d.mkdir(parents=True, exist_ok=True)
        return d
    d = tmp_path / "screenshots"
    d.mkdir()
    return d


@pytest.fixture
def capture(screenshot_dir: Path):
    """Return a callable that takes a labeled screenshot via mss."""
    import mss

    sct = mss.mss()
    seq = 0

    def _capture(label: str = "") -> Path:
        nonlocal seq
        seq += 1
        ts = datetime.now().strftime("%H%M%S")
        name = f"{seq:03d}_{ts}_{label}.png"
        out = screenshot_dir / name
        sct.shot(output=str(out))
        return out

    return _capture
