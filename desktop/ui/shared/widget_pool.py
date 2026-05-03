"""
widget_pool.py — Generic pre-allocated reusable pool of QWidget subclasses.

Used by views that rebuild their content on refresh to avoid the flicker and
overhead of destroying and recreating widgets on every data update.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Generic, TypeVar

from PySide6.QtWidgets import QLayout, QWidget

T = TypeVar("T", bound=QWidget)


class WidgetPool(Generic[T]):
    """Pre-allocated, reusable pool of QWidget subclasses.

    Usage:
        pool = WidgetPool(factory=MyCard, layout=self._layout, initial=8)
        # in refresh():
        pool.begin_update()
        for item in data:
            card = pool.acquire()
            card.populate(item)
        # (no end_update needed — unused cards are already hidden by begin_update)
    """

    def __init__(
        self,
        factory: Callable[[], T],
        layout: QLayout,
        initial: int = 8,
    ) -> None:
        self._factory = factory
        self._layout = layout
        self._pool: list[T] = []
        self._cursor: int = 0
        # Pre-allocate initial widgets, hidden
        for _ in range(initial):
            w = self._factory()
            self._layout.addWidget(w)
            w.setVisible(False)
            self._pool.append(w)

    def begin_update(self) -> None:
        """Hide all pooled widgets and reset cursor."""
        for w in self._pool:
            w.setVisible(False)
        self._cursor = 0

    def acquire(self) -> T:
        """Return the next pooled widget, growing the pool if needed."""
        if self._cursor >= len(self._pool):
            w = self._factory()
            self._layout.addWidget(w)
            w.setVisible(False)
            self._pool.append(w)
        w = self._pool[self._cursor]
        w.setVisible(True)
        self._cursor += 1
        return w

    @property
    def active_count(self) -> int:
        """Number of currently visible widgets."""
        return self._cursor

    def card_at(self, index: int) -> T | None:
        """Return the widget at the given index if it exists and is active."""
        if 0 <= index < self._cursor:
            return self._pool[index]
        return None
