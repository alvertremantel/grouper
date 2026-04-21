"""Pure-Python color utilities and theme palettes -- re-exported from grouper_core."""

from typing import Any

import grouper_core.colors as _core_colors
from grouper_core.colors import *


def __getattr__(name: str) -> Any:
    return getattr(_core_colors, name)
