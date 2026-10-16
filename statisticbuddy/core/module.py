"""Plug-in point for trackers. Each feature (EXP, mesos, loot, ...) is a module that
declares the screen regions it reads, owns its database tables, and shows a
panel on the Live tab. Sessions, the game screenshot and OCR are shared."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np
    from PySide6.QtWidgets import QWidget

    from statisticbuddy.capture.ocr import OcrEngine
    from statisticbuddy.core.session import SessionController
    from statisticbuddy.core.storage import Settings


@dataclass(frozen=True)
class RegionSpec:
    key: str     # unique across modules, e.g. "exp_bar"
    label: str   # shown in the Regions tab
    hint: str    # shown while selecting it
    ocr: str = "text"  # "text": joined text; "boxes": text with positions; "none": pixels only


@dataclass
class RegionRead:
    text: str = ""
    boxes: list = field(default_factory=list)  # [(x0, y0, x1, y1, text)] in region pixels
    image: np.ndarray | None = None            # BGR crop of the region


@dataclass
class AppContext:
    db: sqlite3.Connection
    settings: Settings
    ocr: OcrEngine
    session: SessionController | None = None


class TrackerModule:
    key = "base"
    title = "Base"
    regions: tuple[RegionSpec, ...] = ()
    history_headers: tuple[str, ...] = ()

    def init_schema(self, db: sqlite3.Connection) -> None:
        """Create this module's tables (CREATE TABLE IF NOT EXISTS)."""

    def create_panel(self, ctx: AppContext) -> QWidget | None:
        """Widget shown on the Live tab."""
        return None

    # Session lifecycle, called by the SessionController.
    def on_start(self, session_id: int, ts: float) -> None: ...
    def on_pause(self, ts: float) -> None: ...
    def on_resume(self, ts: float) -> None: ...
    def on_stop(self, ts: float) -> None: ...

    def on_continue(self, session_id: int, active_seconds: float) -> None:
        """Pick up a session that didn't finish (the app closed mid-session) from what was
        saved. The session is left paused; the next read after Resume is the new reference."""

    def on_region_changed(self, region_key: str) -> None:
        """A region was re-selected or cleared: restart from its next read rather than
        counting the jump between the old and new spot as progress."""

    def on_read(self, reads: dict[str, RegionRead], ts: float) -> str | None:
        """This module's regions from one game screenshot; return a short status message."""
        return None

    def on_snapshot(self, reads: dict[str, RegionRead]) -> None:
        """A read outside a session (e.g. Test): update what you hold, count nothing as gained."""

    def describe(self, region_key: str, read: RegionRead) -> str:
        """How a read would be interpreted, for the Regions tab preview."""
        return read.text

    def refresh(self, ts: float) -> None:
        """Called every second to update the panel."""

    def history_values(self, db: sqlite3.Connection, session_id: int) -> list[str]:
        """One string per entry in history_headers."""
        return []

    def holdings(self) -> list[tuple[str, float]]:
        """[(label, mesos)] of what you hold right now (last known), e.g. [("ETC", 12000)].
        Used for net worth, independent of sessions."""
        return []

    # Profit accounting: change in value (in mesos) this module contributes.
    def profit_parts(self, ts: float) -> list[tuple[str, float]]:
        """[(label, mesos)] for the current session, e.g. [("Mesos", 41200)]."""
        return []

    def profit_history(self, db: sqlite3.Connection, session_id: int) -> float | None:
        """This module's contribution to a past session's profit, or None if not tracked."""
        return None
