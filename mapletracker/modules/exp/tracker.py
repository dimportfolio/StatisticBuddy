"""Session maths for EXP tracking. Pure Python so it can be unit tested.

Every reading (from OCR or typed in) is compared with the last accepted one.
Normal progress is accepted straight away. Anything surprising (a level-up,
a big jump, a value that doesn't match the level's EXP total) is held as a
*candidate* and only accepted once the next reading agrees with it, so a
single OCR misread can't corrupt the session.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum

from mapletracker.core.clock import ActiveClock


class Verdict(str, Enum):
    BASELINE = "baseline"
    ACCEPTED = "accepted"
    LEVEL_UP = "level up"
    PENDING = "pending"
    IGNORED = "ignored"


@dataclass(frozen=True)
class Sample:
    ts: float
    exp: int
    pct: float | None = None
    source: str = "ocr"


@dataclass(frozen=True)
class Stats:
    gained: int
    levels: int
    active_seconds: float
    exp_per_hour: float
    recent_exp_per_hour: float
    pct_per_hour: float | None
    pct_gained: float | None
    eta_seconds: float | None
    current_exp: int | None
    current_pct: float | None
    level_total: float | None


class ExpTracker:
    def __init__(self, max_jump_pct: float = 15.0, total_tolerance: float = 0.03,
                 recent_window: float = 600.0):
        self.max_jump_pct = max_jump_pct
        self.total_tolerance = total_tolerance
        self.recent_window = recent_window
        self.reset()

    # ----- lifecycle -------------------------------------------------------------
    def reset(self) -> None:
        self.last: Sample | None = None
        self.candidate: Sample | None = None
        self.level_total: float | None = None
        self._total_from_pct = 0.0
        self.gained = 0
        self.pct_gained_sum = 0.0
        self.levels = 0
        self.clock = ActiveClock()
        self._rebaseline = False
        self._points: deque[tuple[float, int]] = deque()

    @property
    def running(self) -> bool:
        return self.clock.running

    def start(self, ts: float) -> None:
        if not self.clock.running:
            self.clock.start(ts)
            # EXP earned while paused shouldn't count.
            self._rebaseline = self.last is not None

    def pause(self, ts: float) -> None:
        if self.clock.running:
            self.clock.pause(ts)
            self.candidate = None

    def restore(self, gained: int, levels: int, pct_gained: float | None, active_seconds: float) -> None:
        """Continue a saved session; the next reading becomes the new starting point."""
        self.reset()
        self.gained, self.levels = gained, levels
        self.pct_gained_sum = pct_gained or 0.0
        self.clock.set_elapsed(active_seconds)

    def rebaseline(self) -> None:
        """Take the next reading as a fresh starting point without counting the jump."""
        if self.last is not None:
            self._rebaseline = True
            self.candidate = None

    def active_seconds(self, ts: float) -> float:
        return self.clock.seconds(ts)

    # ----- readings -----------------------------------------------------------------
    def feed(self, s: Sample, trusted: bool = False) -> Verdict:
        if not self.running:
            if not trusted:
                return Verdict.IGNORED
            # A manual entry while paused just updates the reference point.
            self._baseline(s)
            return Verdict.BASELINE
        if self.last is None or self._rebaseline:
            self._rebaseline = False
            self._baseline(s)
            return Verdict.BASELINE

        kind, gain = self._classify(self.last, s)
        if kind == "normal":
            self.candidate = None
            self._accept(s, gain, leveled=False)
            return Verdict.ACCEPTED
        if trusted:
            self.candidate = None
            return self._apply_transition(kind, gain, s)

        if self.candidate is not None:
            # The candidate may be on a new level, so judge it by its own EXP total.
            kind2, gain2 = self._classify(self.candidate, s, total=self._own_total(self.candidate))
            if kind2 == "normal":
                cand_kind, cand_gain = self._classify(self.last, self.candidate)
                verdict = self._apply_transition(cand_kind, cand_gain, self.candidate)
                self.candidate = None
                self._accept(s, gain2, leveled=False)
                return verdict if verdict == Verdict.LEVEL_UP else Verdict.ACCEPTED
        self.candidate = s
        return Verdict.PENDING

    def _apply_transition(self, kind: str, gain: int, s: Sample) -> Verdict:
        if kind == "levelup":
            self._accept(s, gain, leveled=True)
            return Verdict.LEVEL_UP
        if kind in ("jump", "normal"):
            self._accept(s, gain, leveled=False)
            return Verdict.ACCEPTED
        # "drop" (EXP loss / character switch) or "bad" (total changed): restart from here.
        if kind == "bad":
            self.level_total = None
            self._total_from_pct = 0.0
        self._baseline(s)
        return Verdict.BASELINE

    def _baseline(self, s: Sample) -> None:
        self.last = s
        self.candidate = None
        self._learn_total(s)
        self._points.append((self.active_seconds(s.ts), self.gained))

    def _accept(self, s: Sample, gain: int, leveled: bool) -> None:
        old_total = self.level_total
        if leveled:
            self.levels += 1
            self.level_total = None
            self._total_from_pct = 0.0
            if old_total:
                self.pct_gained_sum += (old_total - self.last.exp) / old_total * 100
        elif old_total:
            self.pct_gained_sum += gain / old_total * 100
        self.gained += max(0, gain)
        self.last = s
        self._learn_total(s)
        if leveled and self.level_total:
            self.pct_gained_sum += s.exp / self.level_total * 100
        now = self.active_seconds(s.ts)
        self._points.append((now, self.gained))
        while self._points and now - self._points[0][0] > self.recent_window:
            self._points.popleft()

    def _learn_total(self, s: Sample) -> None:
        # The reading with the largest % gives the most precise estimate.
        if s.pct is not None and s.pct >= 1 and s.pct >= self._total_from_pct:
            self.level_total = s.exp * 100 / s.pct
            self._total_from_pct = s.pct

    @staticmethod
    def _own_total(a: Sample) -> float | None:
        return a.exp * 100 / a.pct if a.pct is not None and a.pct >= 1 else None

    _UNSET = object()

    def _classify(self, a: Sample, b: Sample, total=_UNSET) -> tuple[str, int]:
        """Describe the step from reading a to reading b."""
        if total is self._UNSET:
            total = self.level_total or self._own_total(a)
        if b.exp >= a.exp:
            gain = b.exp - a.exp
            if total and b.pct is not None and b.pct >= 1:
                implied = b.exp * 100 / b.pct
                if abs(implied - total) / total > self.total_tolerance:
                    return "bad", gain
            if total:
                pct_gain = gain / total * 100
            elif a.pct is not None and b.pct is not None:
                pct_gain = b.pct - a.pct
            else:
                pct_gain = None
            if pct_gain is not None:
                return ("jump" if pct_gain > self.max_jump_pct else "normal"), gain
            return ("jump" if a.exp > 0 and gain > a.exp else "normal"), gain

        # EXP went down: level-up, or EXP loss.
        if a.pct is not None and b.pct is not None:
            leveled = a.pct - b.pct >= 30
        else:
            leveled = b.exp < a.exp * 0.5
        if not leveled:
            return "drop", 0
        remaining = max(0, int(round(total)) - a.exp) if total else 0
        return "levelup", remaining + b.exp

    # ----- stats -------------------------------------------------------------------
    def stats(self, ts: float) -> Stats:
        active = self.active_seconds(ts)
        rate = self.gained / active * 3600 if active >= 30 else 0.0

        recent = 0.0
        if len(self._points) >= 2:
            t0, g0 = self._points[0]
            t1, g1 = self._points[-1]
            if t1 - t0 >= 30:
                recent = (g1 - g0) / (t1 - t0) * 3600

        total = self.level_total
        pct_per_hour = rate / total * 100 if total and rate else None
        pct_gained = self.pct_gained_sum if total or self.levels else None
        eta = None
        pace = recent or rate
        if total and pace > 0 and self.last is not None:
            eta = max(0.0, (total - self.last.exp) / pace * 3600)
        return Stats(
            gained=self.gained,
            levels=self.levels,
            active_seconds=active,
            exp_per_hour=rate,
            recent_exp_per_hour=recent,
            pct_per_hour=pct_per_hour,
            pct_gained=pct_gained,
            eta_seconds=eta,
            current_exp=self.last.exp if self.last else None,
            current_pct=self.last.pct if self.last else None,
            level_total=total,
        )
