"""Meso tracking: reads the meso total in the inventory window."""
from __future__ import annotations

import time

from mapletracker.core import fmt
from mapletracker.core.module import AppContext, RegionRead, RegionSpec, TrackerModule
from mapletracker.modules.exp.tracker import Verdict
from mapletracker.modules.meso import store
from mapletracker.modules.meso.parser import parse_meso_text
from mapletracker.modules.meso.tracker import MesoSample, MesoTracker

MESSAGES = {
    Verdict.BASELINE: "starting point recorded",
    Verdict.ACCEPTED: "ok",
    Verdict.PENDING: "unusual change, waiting to confirm",
    Verdict.IGNORED: "paused",
}


class MesoModule(TrackerModule):
    key = "meso"
    title = "Mesos"
    regions = (RegionSpec("meso_inventory", "Meso count (inventory)",
                          "Open your inventory, then drag a tight box around the meso number at its bottom."),)
    history_headers = ("Mesos gained", "Mesos / hour", "Mesos spent")

    def __init__(self):
        self.ctx: AppContext | None = None
        self.tracker = MesoTracker()
        self.session_id: int | None = None
        self.panel = None

    def init_schema(self, db) -> None:
        store.init_schema(db)

    def create_panel(self, ctx: AppContext):
        from mapletracker.modules.meso.widget import MesoPanel
        self.ctx = ctx
        cfg = ctx.settings.section("meso")
        self.tracker.jump_abs = int(cfg.get("jump_abs", 1_000_000))
        self.panel = MesoPanel(self)
        return self.panel

    def on_start(self, session_id: int, ts: float) -> None:
        self.session_id = session_id
        self.tracker.reset()
        self.tracker.start(ts)
        store.create_stats(self.ctx.db, session_id)

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
        s = self.tracker.stats(time.time())
        store.save_stats(self.ctx.db, self.session_id, start_value=self.tracker.start_value,
                         end_value=s.current, gained=s.gained, spent=s.spent)

    def on_continue(self, session_id: int, active_seconds: float) -> None:
        r = store.get_stats(self.ctx.db, session_id)
        self.session_id = session_id
        if r is None:
            store.create_stats(self.ctx.db, session_id)
            self.tracker.restore(0, 0, None, active_seconds)
        else:
            self.tracker.restore(r["gained"], r["spent"], r["start_value"], active_seconds)
        self.refresh(time.time())

    def on_region_changed(self, region_key: str) -> None:
        self.tracker.rebaseline()

    def on_read(self, reads: dict[str, RegionRead], ts: float) -> str | None:
        text = reads["meso_inventory"].text
        value = parse_meso_text(text)
        if value is None:
            return "couldn't read mesos (inventory closed?)"
        return self.feed(MesoSample(ts, value, "ocr"), text)

    def on_snapshot(self, reads: dict[str, RegionRead]) -> None:
        value = parse_meso_text(reads["meso_inventory"].text)
        cfg = self.ctx.settings.section("meso")
        if value is not None and cfg.get("last_mesos") != value:
            cfg["last_mesos"] = value
            self.ctx.settings.save()

    def holdings(self) -> list[tuple[str, float]]:
        last = self.ctx.settings.section("meso").get("last_mesos") if self.ctx else None
        return [("Mesos", last)] if last is not None else []

    def profit_parts(self, ts: float) -> list[tuple[str, float]]:
        if self.tracker.last is None:
            return []
        return [("Mesos (net)", self.tracker.stats(ts).net or 0)]

    def profit_history(self, db, session_id: int) -> float | None:
        r = store.get_stats(db, session_id)
        return None if r is None or r["start_value"] is None else r["gained"] - r["spent"]

    def describe(self, region_key: str, read: RegionRead) -> str:
        v = parse_meso_text(read.text)
        return "couldn't find a number" if v is None else f"{v:,} mesos"

    def add_manual(self, value: int) -> str:
        self.ctx.session.ensure_running()
        return self.feed(MesoSample(time.time(), value, "manual"), "", trusted=True)

    def feed(self, sample: MesoSample, raw: str, trusted: bool = False) -> str:
        verdict = self.tracker.feed(sample, trusted=trusted)
        last = self.tracker.last.value if self.tracker.last else None
        cfg = self.ctx.settings.section("meso")
        if last is not None and cfg.get("last_mesos") != last:
            cfg["last_mesos"] = last   # remembered between sessions, for net worth
            self.ctx.settings.save()
        if self.session_id is not None:
            store.add_sample(self.ctx.db, self.session_id, sample.ts, sample.value,
                             sample.source, verdict.value, raw)
            self._save()
        self.refresh(time.time())
        return MESSAGES.get(verdict, verdict.value)

    def refresh(self, ts: float) -> None:
        if self.panel is not None:
            self.panel.show_stats(self.tracker.stats(ts))

    def history_values(self, db, session_id: int) -> list[str]:
        r = store.get_stats(db, session_id)
        if r is None:
            return ["-"] * len(self.history_headers)
        active = db.execute("SELECT active_seconds FROM sessions WHERE id=?", (session_id,)).fetchone()[0] or 0
        rate = r["gained"] / active * 3600 if active >= 30 else None
        return [fmt.big_number(r["gained"]), fmt.big_number(rate), fmt.big_number(r["spent"])]
