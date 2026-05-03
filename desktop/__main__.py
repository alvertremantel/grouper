"""Allow running as ``python -m desktop`` or ``python desktop/__main__.py``."""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    # Support direct script execution from a source checkout. In that mode Python
    # sets sys.path[0] to ``desktop/`` itself, so the parent project directory
    # must be added before importing the package by its canonical name.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from desktop.main import main
else:
    from .main import main

main()
