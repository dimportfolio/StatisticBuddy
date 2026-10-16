"""Session maths for mesos. Pure Python so it can be unit tested.

Input is the meso total shown in the inventory. Increases count as gained,
decreases (shops, repairs, trades) count as spent and never reduce "gained".
As with EXP, a surprising reading (big jump or any drop) is only accepted once
the next reading agrees with it, so one OCR misread can't skew the totals.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from statisticbuddy.core.clock import ActiveClock
from statisticbuddy.modules.exp.tracker import Verdict


@dataclass(frozen=True)
class MesoSample:
    ts: float
    value: int
    source: str = "ocr"


@dataclass(frozen=True)
class MesoStats:
    gained: int
    spent: int
    net: int | None
    current: int | None
    active_seconds: float
    per_hour: float
    recent_per_hour: float


class MesoTracker:
    def __init__(self, jump_abs: int = 1_000_000, jump_rel: float = 0.25, recent_window: float = 600.0):
        self.jump_abs = jump_abs
        self.jump_rel = jump_rel
        self.recent_window = recent_window
        self.reset()

    def reset(self) -> None:
        self.clock = ActiveClock()
        self.last: MesoSample | None = None
        self.candidate: MesoSample | None = None
        self.start_value: int | None = None
        self.gained = 0
        self.spent = 0
        self._rebaseline = False
        self._points: deque[tuple[float, int]] = deque()

    @property
    def running(self) -> bool:
        return self.clock.running

    def start(self, ts: float) -> None:
        if not self.clock.running:
            self.clock.start(ts)
            self._rebaseline = self.last is not None

    def pause(self, ts: float) -> None:
        if self.clock.running:
            self.clock.pause(ts)
            self.candidate = None

    def restore(self, gained: int, spent: int, start_value: int | None, active_seconds: float) -> None:
        """Continue a saved session; the next reading becomes the new starting point."""
        self.reset()
        self.gained, self.spent, self.start_value = gained, spent, start_value
        self.clock.set_elapsed(active_seconds)

    def rebaseline(self) -> None:
        """Take the next reading as a fresh starting point without counting the jump."""
        if self.last is not None:
            self._rebaseline = True
            self.candidate = None

    def _classify(self, prev: int, new: int) -> str:
        d = new - prev
        if d < 0:
            return "spend"
        return "normal" if d <= max(self.jump_abs, self.jump_rel * prev) else "jump"

    def feed(self, s: MesoSample, trusted: bool = False) -> Verdict:
        if not self.running:
            if not trusted:
                return Verdict.IGNORED
            self._baseline(s)
            return Verdict.BASELINE
        if self.last is None or self._rebaseline:
            self._rebaseline = False
            self._baseline(s)
            return Verdict.BASELINE

        kind = self._classify(self.last.value, s.value)
        if kind == "normal" or trusted:
            self.candidate = None
            self._apply(s)
            return Verdict.ACCEPTED
        if self.candidate is not None and self._classify(self.candidate.value, s.value) == "normal":
            self._apply(self.candidate)
            self.candidate = None
            self._apply(s)
            return Verdict.ACCEPTED
        self.candidate = s
        return Verdict.PENDING

    def _baseline(self, s: MesoSample) -> None:
        self.last = s
        self.candidate = None
        if self.start_value is None:
            self.start_value = s.value
        self._points.append((self.clock.seconds(s.ts), self.gained))

    def _apply(self, s: MesoSample) -> None:
        d = s.value - self.last.value
        if d >= 0:
            self.gained += d
        else:
            self.spent -= d
        self.last = s
        now = self.clock.seconds(s.ts)
        self._points.append((now, self.gained))
        while self._points and now - self._points[0][0] > self.recent_window:
            self._points.popleft()

    def stats(self, ts: float) -> MesoStats:
        active = self.clock.seconds(ts)
        rate = self.gained / active * 3600 if active >= 30 else 0.0
        recent = 0.0
        if len(self._points) >= 2:
            (t0, g0), (t1, g1) = self._points[0], self._points[-1]
            if t1 - t0 >= 30:
                recent = (g1 - g0) / (t1 - t0) * 3600
        current = self.last.value if self.last else None
        # Gained minus spent, so changes while paused aren't counted.
        net = self.gained - self.spent if self.last is not None else None
        return MesoStats(self.gained, self.spent, net, current, active, rate, recent)
