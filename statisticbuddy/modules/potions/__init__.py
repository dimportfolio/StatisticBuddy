"""Potions: reads potion counts on quickslot keys, prices what's used, and estimates
when you'll need to go back to town to repot."""
from __future__ import annotations

import time

from statisticbuddy.core import fmt
from statisticbuddy.core.module import AppContext, RegionRead, RegionSpec, TrackerModule
from statisticbuddy.modules.loot.digits import DigitReader
from statisticbuddy.modules.potions import store
from statisticbuddy.modules.potions.tracker import PotionTracker

SLOTS = 4
KINDS = ("HP", "MP", "Other")
RAN_OUT_BELOW = 5  # a key that shows no number after having this few left has run out


class PotionModule(TrackerModule):
    key = "potions"
    title = "Potions"
    regions = tuple(
        RegionSpec(f"pot_{i}", f"Potion quickslot {i}",
                   "Drag a box around ONE quickslot key that holds a potion: the whole key, "
                   "including its icon and the number at the bottom.", ocr="none")
        for i in range(1, SLOTS + 1)
    )
    history_headers = ("Potions used", "Potion cost")

    def __init__(self):
        self.ctx: AppContext | None = None
        self.tracker = PotionTracker()
        self.session_id: int | None = None
        self.panel = None
        self._digits: DigitReader | None = None

    def init_schema(self, db) -> None:
        store.init_schema(db)

    def create_panel(self, ctx: AppContext):
        from statisticbuddy.modules.potions.widget import PotionPanel
        self.ctx = ctx
        self.panel = PotionPanel(self)
        return self.panel

    # ----- slot settings ------------------------------------------------------------------
    @property
    def cfg(self) -> dict:
        return self.ctx.settings.section("potions")

    def slot_info(self, key: str) -> dict:
        info = self.cfg.setdefault("slots", {}).setdefault(key, {})
        n = key.split("_")[-1]
        info.setdefault("name", f"Potion {n}")
        info.setdefault("kind", "HP" if n == "1" else "MP" if n == "2" else "Other")
        info.setdefault("price", 0.0)
        return info

    def update_slot(self, key: str, **changes) -> None:
        self.slot_info(key).update(changes)
        self.ctx.settings.save()
        self._save()

    def active_slots(self) -> list[str]:
        """Quickslot keys that have a region selected."""
        session = self.ctx.session if self.ctx else None
        return [s.key for s in self.regions if session is None or session.region(s.key) is not None]

    @property
    def digits(self) -> DigitReader:
        if self._digits is None:
            self._digits = DigitReader(self.ctx.settings.section("loot").get("glyphs"))
        return self._digits

    # ----- lifecycle -----------------------------------------------------------------------
    def on_start(self, session_id: int, ts: float) -> None:
        self.session_id = session_id
        self.tracker.reset()
        self.tracker.start(ts)

    def on_pause(self, ts: float) -> None:
        self.tracker.pause(ts)
        self._save()

    def on_resume(self, ts: float) -> None:
        self.tracker.start(ts)

    def on_stop(self, ts: float) -> None:
        self.tracker.pause(ts)
        self._save()
        self.session_id = None
        self.tracker.reset()

    def _save(self) -> None:
        if self.session_id is None:
            return
        counts = self.tracker.counts
        for key in set(self.tracker.used) | set(self.tracker.bought) | set(counts.current) | set(counts.start_counts):
            info = self.slot_info(key)
            store.save_slot(self.ctx.db, self.session_id, key, name=info["name"], kind=info["kind"],
                            price=float(info["price"]), used=self.tracker.used.get(key, 0),
                            bought=self.tracker.bought.get(key, 0), change=self.tracker.change(key),
                            start_count=counts.start_counts.get(key), end_count=counts.current.get(key))

    def on_continue(self, session_id: int, active_seconds: float) -> None:
        rows = store.session_rows(self.ctx.db, session_id)
        self.session_id = session_id
        self.tracker.restore(
            used={r["slot"]: r["used"] for r in rows},
            bought={r["slot"]: r["bought"] for r in rows},
            changes={r["slot"]: r["change"] for r in rows},
            start_counts={r["slot"]: r["start_count"] for r in rows if r["start_count"] is not None},
            active_seconds=active_seconds,
        )
        self.refresh(time.time())

    # ----- reading -----------------------------------------------------------------------------
    def on_region_changed(self, region_key: str) -> None:
        self.tracker.rebase(region_key)
        self.refresh(time.time())

    def read_count(self, read: RegionRead) -> int | None:
        r = self.digits.read(read.image, max_start=10)
        return None if r is None else r.value

    def on_read(self, reads: dict[str, RegionRead], ts: float) -> str | None:
        counts: dict[str, int] = {}
        unreadable: set[str] = set()
        for key, read in reads.items():
            r = self.digits.read(read.image, max_start=10)
            if r is not None and r.value is not None:
                counts[key] = r.value
            elif r is None and (self.tracker.current(key) or 0) <= RAN_OUT_BELOW and self.tracker.current(key) is not None:
                counts[key] = 0   # the number disappeared after running low: out of potions
            else:
                unreadable.add(key)
        msg = self.tracker.feed(counts, unreadable, ts)
        changed = False
        for key in reads:
            have = self.tracker.current(key)
            if have is not None and self.slot_info(key).get("have") != have:
                self.slot_info(key)["have"] = have   # remembered between sessions
                changed = True
        if changed:
            self.ctx.settings.save()
        self._save()
        self.refresh(time.time())
        return msg + (f", couldn't read {len(unreadable)} key(s)" if unreadable else "")

    def on_snapshot(self, reads: dict[str, RegionRead]) -> None:
        changed = False
        for key, read in reads.items():
            n = self.read_count(read)
            if n is not None and self.slot_info(key).get("have") != n:
                self.slot_info(key)["have"] = n
                changed = True
        if changed:
            self.ctx.settings.save()
            self.refresh(time.time())

    def describe(self, region_key: str, read: RegionRead) -> str:
        n = self.read_count(read)
        name = self.slot_info(region_key)["name"]
        return f"{name} ×{n}" if n is not None else "no number found (box the whole key, including its number)"

    # ----- results ------------------------------------------------------------------------------
    def repot_eta(self) -> dict[str, float | None]:
        """Seconds until each kind (HP, MP) runs out, all keys of that kind together."""
        out = {}
        for kind in ("HP", "MP"):
            keys = [k for k in self.active_slots() if self.slot_info(k)["kind"] == kind]
            if keys:
                out[kind] = self.tracker.runs_out_in(keys)
        return out

    def cost(self) -> float:
        return sum(self.tracker.used.get(k, 0) * float(self.slot_info(k)["price"]) for k in self.tracker.used)

    def refresh(self, ts: float) -> None:
        if self.panel is not None:
            self.panel.show_rows()

    def holdings(self) -> list[tuple[str, float]]:
        if self.ctx is None:
            return []
        known = [self.slot_info(k) for k in self.active_slots()]
        known = [i for i in known if i.get("have") is not None]
        return [("Potions", sum(i["have"] * float(i["price"]) for i in known))] if known else []

    def profit_parts(self, ts: float) -> list[tuple[str, float]]:
        if self.tracker.counts.reference is None and not self.tracker.counts.accumulated:
            return []
        # Value change of potions held: using them costs their price; buying them
        # (mesos spent) is offset by potions gained, so restocking isn't a loss.
        value = sum(self.tracker.change(k) * float(self.slot_info(k)["price"])
                    for k in set(self.tracker.counts.current) | set(self.tracker.counts.accumulated))
        return [("Potions", value)]

    def profit_history(self, db, session_id: int) -> float | None:
        rows = store.session_rows(db, session_id)
        return sum(r["change"] * r["price"] for r in rows) if rows else None

    def history_values(self, db, session_id: int) -> list[str]:
        rows = store.session_rows(db, session_id)
        if not rows:
            return ["-", "-"]
        used = sum(r["used"] for r in rows)
        cost = sum(r["used"] * r["price"] for r in rows)
        return [f"{used:,}", fmt.big_number(cost)]
