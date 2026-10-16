"""Potion usage maths. Pure Python so it can be unit tested.

Counts come from the quickslot keys. A count change is only accepted after two
reads agree (via LootTracker). Decreases are potions used; increases are potions
bought or picked up. The use rate over the last few minutes gives "runs out in".
"""
from __future__ import annotations

from collections import deque

from statisticbuddy.modules.loot.tracker import LootTracker


class PotionTracker:
    def __init__(self, window: float = 600.0):
        self.window = window
        self.reset()

    def reset(self) -> None:
        self.counts = LootTracker()
        self.used: dict[str, int] = {}
        self.bought: dict[str, int] = {}
        self._history: dict[str, deque[tuple[float, int]]] = {}

    @property
    def running(self) -> bool:
        return self.counts.running

    def start(self, ts: float) -> None:
        self.counts.start(ts)

    def pause(self, ts: float) -> None:
        self.counts.pause(ts)

    def current(self, key: str) -> int | None:
        return self.counts.current.get(key) if self.counts.reference is not None else None

    def restore(self, used: dict[str, int], bought: dict[str, int], changes: dict[str, int],
                start_counts: dict[str, int], active_seconds: float) -> None:
        """Continue a saved session (the next read becomes the new reference point)."""
        self.reset()
        self.counts.restore(changes, start_counts, active_seconds)
        self.used, self.bought = dict(used), dict(bought)

    def start_count(self, key: str) -> int | None:
        return self.counts.start_counts.get(key)

    def rebase(self, key: str) -> None:
        """The key's screen region changed: restart its count without counting the jump."""
        self.counts.rebase({key})
        self.counts.start_counts.pop(key, None)   # a different key: its own starting count
        self._history.pop(key, None)

    def feed(self, counts: dict[str, int], unreadable: set[str], ts: float) -> str:
        fresh = self.counts.reference is None   # first read, or first after a pause
        rebased = self.counts._rebase & set(counts)
        before = dict(self.counts.current)
        msg = self.counts.feed(counts, unreadable)
        t = self.counts.clock.seconds(ts)
        for key in set(counts) | set(before):
            if not fresh and key not in rebased and key in before and key in self.counts.current:
                d = self.counts.current[key] - before[key]
                if d < 0:
                    self.used[key] = self.used.get(key, 0) - d
                elif d > 0:
                    self.bought[key] = self.bought.get(key, 0) + d
            hist = self._history.setdefault(key, deque())
            hist.append((t, self.used.get(key, 0)))
            while hist and t - hist[0][0] > self.window:
                hist.popleft()
        return msg

    def rate_per_hour(self, key: str) -> float | None:
        """Potions used per hour over the recent window; None until there's a minute of data."""
        hist = self._history.get(key)
        if not hist or len(hist) < 2:
            return None
        (t0, u0), (t1, u1) = hist[0], hist[-1]
        if t1 - t0 < 60:
            return None
        return (u1 - u0) / (t1 - t0) * 3600

    def runs_out_in(self, keys: list[str]) -> float | None:
        """Seconds until these potions (e.g. all HP potions together) run out at the current rate."""
        total, rate = 0, 0.0
        for k in keys:
            c, r = self.current(k), self.rate_per_hour(k)
            if c is None:
                continue
            total += c
            rate += r or 0.0
        if rate <= 0:
            return None
        return total / rate * 3600

    def change(self, key: str) -> int:
        return self.counts.change(key)
