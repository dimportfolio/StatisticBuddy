"""Session maths for item counts. Pure Python so it can be unit tested.

Tracks the change in each item's count since the session started (picked up,
sold, dropped). A count only changes after two reads in a row agree, so a single
misread stack number is ignored. Changes while paused are not counted.
"""
from __future__ import annotations

from statisticbuddy.core.clock import ActiveClock


class LootTracker:
    def __init__(self):
        self.reset()

    def reset(self) -> None:
        self.clock = ActiveClock()
        self.current: dict[int, int] = {}
        self.reference: dict[int, int] | None = None   # counts at (re)start
        self.accumulated: dict[int, int] = {}            # changes banked before pauses
        self.pending: dict[int, int] = {}
        self._rebase: set = set()                         # restart these from their next read
        self.start_counts: dict[int, int] = {}           # each item's count when first seen this session

    def restore(self, changes: dict[int, int], start_counts: dict[int, int], active_seconds: float) -> None:
        """Continue a saved session: keep its changes and starting counts; the next read
        becomes the new reference point (like resuming after a pause)."""
        self.reset()
        self.accumulated = dict(changes)
        self.start_counts = dict(start_counts)
        self.clock.set_elapsed(active_seconds)

    def rebase(self, items) -> None:
        """Take the next read of these items as their new starting point (e.g. the screen
        region was re-selected), keeping the change counted so far."""
        self._rebase |= set(items)

    @property
    def running(self) -> bool:
        return self.clock.running

    def start(self, ts: float) -> None:
        self.clock.start(ts)

    def pause(self, ts: float) -> None:
        if not self.clock.running:
            return
        self.clock.pause(ts)
        if self.reference is not None:
            for item in set(self.current) | set(self.reference):
                self.accumulated[item] = self.change(item)
        self.reference = None
        self.pending.clear()
        self._rebase.clear()   # everything restarts from the next read anyway

    def feed(self, counts: dict[int, int], unreadable: set[int] = frozenset()) -> str:
        """Feed one read. Items in ``unreadable`` were seen but their count couldn't be read;
        they keep their previous count."""
        if not self.running:
            return "paused"
        if self.reference is None:
            self.current = dict(counts)
            self.reference = dict(counts)
            self.pending.clear()
            for item, n in counts.items():
                self.start_counts.setdefault(item, n)
            # Items present but unreadable now get their starting point from their first
            # good read; otherwise everything you already hold would count as picked up.
            self._rebase = set(unreadable)
            return "starting point recorded"
        for item in self._rebase & set(counts):
            if item in self.reference:
                self.accumulated[item] = self.change(item)
            self.current[item] = self.reference[item] = counts[item]
            self.start_counts.setdefault(item, counts[item])
            self.pending.pop(item, None)
        rebased = self._rebase & set(counts)
        self._rebase -= rebased
        changed = []
        for item in (set(counts) | set(self.current)) - set(unreadable) - rebased - self._rebase:
            new, old = counts.get(item, 0), self.current.get(item, 0)
            if new == old:
                self.pending.pop(item, None)
            elif self.pending.get(item) == new:
                self.current[item] = new
                self.pending.pop(item)
                self.start_counts.setdefault(item, 0)   # first picked up this session
                changed.append(item)
            else:
                self.pending[item] = new
        return f"{len(changed)} item(s) changed" if changed else "ok"

    def change(self, item: int) -> int:
        base = self.accumulated.get(item, 0)
        if self.reference is None:
            return base
        return base + self.current.get(item, 0) - self.reference.get(item, 0)

    def changes(self) -> dict[int, int]:
        items = set(self.accumulated) | set(self.current) | set(self.reference or {})
        return {i: self.change(i) for i in items}

    def value(self, prices: dict[int, float]) -> float:
        return sum(prices.get(i, 0) * c for i, c in self.changes().items())
