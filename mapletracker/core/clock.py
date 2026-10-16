"""Active-time stopwatch that excludes paused stretches."""
from __future__ import annotations


class ActiveClock:
    def __init__(self):
        self.reset()

    def reset(self) -> None:
        self._before = 0.0
        self._since: float | None = None

    @property
    def running(self) -> bool:
        return self._since is not None

    def start(self, ts: float) -> None:
        if self._since is None:
            self._since = ts

    def pause(self, ts: float) -> None:
        if self._since is not None:
            self._before += max(0.0, ts - self._since)
            self._since = None

    def set_elapsed(self, seconds: float) -> None:
        """Paused, with this much active time already counted (continuing a saved session)."""
        self._since = None
        self._before = max(0.0, float(seconds))

    def seconds(self, ts: float) -> float:
        extra = ts - self._since if self._since is not None else 0.0
        return self._before + max(0.0, extra)
