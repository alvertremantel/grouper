"""Data models for Grouper — re-exported from grouper_core."""

from typing import Any

import grouper_core.models as _core_models
from grouper_core.models import *
from grouper_core.models import __all__


def __getattr__(name: str) -> Any:
    return getattr(_core_models, name)
