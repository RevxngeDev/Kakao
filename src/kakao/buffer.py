"""Bounded, drop-oldest queue (D-005).

Absorbs bursts and, under pressure, drops the OLDEST item so a slow consumer
(inference) can never build unbounded lag: a late subtitle is worse than a
missing one. Thread-safe and portable. The `dropped` counter is the raw material
for the lag/health indicator surfaced later in the UI.
"""
from __future__ import annotations

import threading
from collections import deque
from typing import Deque, Generic, Optional, TypeVar

T = TypeVar("T")


class DropOldestQueue(Generic[T]):
    """A bounded FIFO that discards the oldest item when full."""

    def __init__(self, maxsize: int) -> None:
        if maxsize < 1:
            raise ValueError("maxsize must be >= 1")
        self._maxsize = maxsize
        self._dq: Deque[T] = deque()
        self._cond = threading.Condition()
        self._dropped = 0

    def put(self, item: T) -> None:
        """Append `item`; if full, drop the oldest and count it."""
        with self._cond:
            if len(self._dq) >= self._maxsize:
                self._dq.popleft()
                self._dropped += 1
            self._dq.append(item)
            self._cond.notify()

    def get(self, timeout: Optional[float] = None) -> Optional[T]:
        """Pop the oldest item, waiting up to `timeout` s; None if none arrives."""
        with self._cond:
            if not self._dq and not self._cond.wait_for(lambda: bool(self._dq), timeout):
                return None
            return self._dq.popleft()

    @property
    def dropped(self) -> int:
        """How many items have been dropped under pressure since creation."""
        with self._cond:
            return self._dropped

    @property
    def maxsize(self) -> int:
        return self._maxsize

    def __len__(self) -> int:
        with self._cond:
            return len(self._dq)
