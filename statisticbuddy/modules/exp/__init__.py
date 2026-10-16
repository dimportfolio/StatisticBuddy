"""EXP tracking: reads the EXP bar, works out EXP/hour, % per hour and time to level."""
from __future__ import annotations

import time

from statisticbuddy.core import fmt
from statisticbuddy.core.module import AppContext, RegionRead, RegionSpec, TrackerModule
from statisticbuddy.modules.exp import store
from statisticbuddy.modules.exp.parser import parse_exp_text
from statisticbuddy.modules.exp.tracker import ExpTracker, Sample, Verdict

MESSAGES = {
    Verdict.BASELINE: "starting point recorded",
    Verdict.ACCEPTED: "ok",
    Verdict.LEVEL_UP: "level up! 🎉",
    Verdict.PENDING: "unusual reading, waiting to confirm",
    Verdict.IGNORED: "paused",
}


class ExpModule(TrackerModule):
    key = "exp"
    title = "EXP"
    regions = (RegionSpec("exp_bar", "EXP bar",
                          "Drag a tight box around the EXP numbers on the EXP bar, e.g. 12345678 [45.678%]."),)
    history_headers = ("EXP gained", "EXP / hour", "% gained", "Levels")

    def __init__(self):
        self.ctx: AppContext | None = None
        self.tracker = ExpTracker()
        self.session_id: int | None = None
        self.panel = None

    def init_schema(self, db) -> None:
        store.init_schema(db)

    def create_panel(self, ctx: AppContext):
        from statisticbuddy.modules.exp.widget import ExpPanel
        self.ctx = ctx
        self.tracker.max_jump_pct = float(ctx.settings.section("exp").get("max_jump_pct", 15.0))
        self.panel = ExpPanel(self)
        return self.panel

    # ----- lifecycle -----------------------------------------------------------------------
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
        store.save_stats(self.ctx.db, self.session_id, gained=s.gained,
                         pct_gained=s.pct_gained, levels=s.levels)

    # ----- readings -------------------------------------------------------------------------
    def on_continue(self, session_id: int, active_seconds: float) -> None:
        r = store.get_stats(self.ctx.db, session_id)
        self.session_id = session_id
        if r is None:
            store.create_stats(self.ctx.db, session_id)
            self.tracker.restore(0, 0, None, active_seconds)
        else:
            self.tracker.restore(r["gained"], r["levels"], r["pct_gained"], active_seconds)
        self.refresh(time.time())

    def on_region_changed(self, region_key: str) -> None:
        self.tracker.rebaseline()

    def on_read(self, reads: dict[str, RegionRead], ts: float) -> str | None:
        text = reads["exp_bar"].text
        reading = parse_exp_text(text)
        if reading is None:
            return "couldn't read the EXP bar"
        return self.feed(Sample(ts, reading.exp, reading.pct, "ocr"), text)

    def describe(self, region_key: str, read: RegionRead) -> str:
        r = parse_exp_text(read.text)
        if r is None:
            return "couldn't find a number"
        return f"EXP {r.exp:,}" + (f" [{r.pct}%]" if r.pct is not None else " (no % found)")

    def add_manual(self, exp: int, pct: float | None) -> str:
        self.ctx.session.ensure_running()
        return self.feed(Sample(time.time(), exp, pct, "manual"), "", trusted=True)

    def feed(self, sample: Sample, raw: str, trusted: bool = False) -> str:
        verdict = self.tracker.feed(sample, trusted=trusted)
        if self.session_id is not None:
            store.add_sample(self.ctx.db, self.session_id, sample.ts, sample.exp, sample.pct,
                             sample.source, verdict.value, raw)
            self._save()
        self.refresh(time.time())
        return MESSAGES[verdict]

    def refresh(self, ts: float) -> None:
        if self.panel is not None:
            self.panel.show_stats(self.tracker.stats(ts))

    def history_values(self, db, session_id: int) -> list[str]:
        r = store.get_stats(db, session_id)
        if r is None:
            return ["-"] * len(self.history_headers)
        active = db.execute("SELECT active_seconds FROM sessions WHERE id=?", (session_id,)).fetchone()[0] or 0
        rate = r["gained"] / active * 3600 if active >= 30 else None
        return [fmt.big_number(r["gained"]), fmt.big_number(rate),
                fmt.percent(r["pct_gained"], 2), str(r["levels"])]
