"""Profit: adds up every module's value change this session (net mesos, loot value,
potions used) to answer "am I meso-positive here?", and shows net worth: the value
of everything you hold (mesos + ETC items + potions)."""
from __future__ import annotations

from statisticbuddy.core import fmt
from statisticbuddy.core.module import AppContext, TrackerModule

MIN_SECONDS_FOR_RATE = 60

SCHEMA = """
CREATE TABLE IF NOT EXISTS profit_session (
    session_id INTEGER PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
    net_worth  REAL NOT NULL
);
"""


def summarize(parts: list[tuple[str, float]], active_seconds: float) -> tuple[float, float | None]:
    """Total profit and profit per hour (None until there's enough time to be meaningful)."""
    total = sum(v for _, v in parts)
    rate = total / active_seconds * 3600 if active_seconds >= MIN_SECONDS_FOR_RATE else None
    return total, rate


class ProfitModule(TrackerModule):
    key = "profit"
    title = "Profit"
    history_headers = ("Profit", "Profit / hour", "Net worth")

    def __init__(self):
        self.ctx: AppContext | None = None
        self.panel = None
        self.session_id: int | None = None

    def init_schema(self, db) -> None:
        db.executescript(SCHEMA)
        db.commit()

    def _others(self) -> list[TrackerModule]:
        return [m for m in self.ctx.session.modules if m is not self]

    def create_panel(self, ctx: AppContext):
        from statisticbuddy.modules.profit.widget import ProfitPanel
        self.ctx = ctx
        self.panel = ProfitPanel()
        return self.panel

    def holdings(self) -> list[tuple[str, float]]:
        return [h for m in self._others() for h in m.holdings()]

    def on_start(self, session_id: int, ts: float) -> None:
        self.session_id = session_id

    def on_continue(self, session_id: int, active_seconds: float) -> None:
        self.session_id = session_id

    def on_stop(self, ts: float) -> None:
        held = self.holdings()
        if self.session_id is not None and held:
            self.ctx.db.execute(
                "INSERT INTO profit_session (session_id, net_worth) VALUES (?, ?)"
                " ON CONFLICT(session_id) DO UPDATE SET net_worth=excluded.net_worth",
                (self.session_id, sum(v for _, v in held)),
            )
            self.ctx.db.commit()
        self.session_id = None

    def refresh(self, ts: float) -> None:
        if self.panel is None or self.ctx.session is None:
            return
        parts = [p for m in self._others() for p in m.profit_parts(ts)]
        total, rate = summarize(parts, self.ctx.session.active_seconds())
        self.panel.show_profit(parts, total, rate, self.holdings())

    def history_values(self, db, session_id: int) -> list[str]:
        row = db.execute("SELECT net_worth FROM profit_session WHERE session_id=?", (session_id,)).fetchone()
        worth = fmt.big_number(row[0]) if row else "-"
        values = [v for m in self._others() if (v := m.profit_history(db, session_id)) is not None]
        if not values:
            return ["-", "-", worth]
        active = db.execute("SELECT active_seconds FROM sessions WHERE id=?", (session_id,)).fetchone()[0] or 0
        total, rate = summarize([("", v) for v in values], active)
        return [fmt.signed(total), fmt.signed(rate), worth]
