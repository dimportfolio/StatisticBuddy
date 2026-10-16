"""Shared play sessions: one timer, one game screenshot per read, OCR per region,
results handed to each tracker module."""
from __future__ import annotations

import sqlite3
import time
import traceback

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal
from PySide6.QtGui import QImage

from mapletracker.capture.game import GameNotFound, RelRegion, grab_game_frame
from mapletracker.capture.window import DEFAULT_TITLE
from mapletracker.core import fmt
from mapletracker.core.clock import ActiveClock
from mapletracker.core.module import AppContext, RegionRead, RegionSpec, TrackerModule

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id             INTEGER PRIMARY KEY,
    character      TEXT NOT NULL DEFAULT '',
    started_at     REAL NOT NULL,
    ended_at       REAL,
    active_seconds REAL NOT NULL DEFAULT 0
);
"""


def init_schema(db: sqlite3.Connection) -> None:
    db.executescript(SCHEMA)
    db.commit()


def latest_unfinished(db: sqlite3.Connection) -> sqlite3.Row | None:
    """The most recent session with no end time (the app closed while it was running)."""
    return db.execute("SELECT * FROM sessions WHERE ended_at IS NULL ORDER BY id DESC LIMIT 1").fetchone()


def close_unfinished(db: sqlite3.Connection, keep: int | None = None) -> int:
    """At startup no session is running, so any without an end time was cut off (crash,
    forced restart). Give it an end time from its tracked time so History shows it properly.
    ``keep``: a session being continued, left open."""
    cur = db.execute("UPDATE sessions SET ended_at = started_at + active_seconds"
                     " WHERE ended_at IS NULL AND id IS NOT ?", (keep,))
    db.commit()
    return cur.rowcount


def list_sessions(db: sqlite3.Connection, limit: int = 500) -> list[sqlite3.Row]:
    return db.execute("SELECT * FROM sessions ORDER BY started_at DESC LIMIT ?", (limit,)).fetchall()


def delete_session(db: sqlite3.Connection, session_id: int) -> None:
    db.execute("DELETE FROM sessions WHERE id=?", (session_id,))
    db.commit()


def to_qimage(bgr) -> QImage:
    h, w = bgr.shape[:2]
    return QImage(bgr.data, w, h, bgr.strides[0], QImage.Format_BGR888).copy()


class _Signals(QObject):
    done = Signal(dict)


class _ReadTask(QRunnable):
    def __init__(self, title: str, regions: dict[str, tuple[RelRegion, str]], ctx: AppContext,
                 signals: _Signals, test: bool):
        super().__init__()
        self.title, self.regions, self.ctx, self.signals, self.test = title, regions, ctx, signals, test

    def run(self) -> None:
        out = {"ts": time.time(), "test": self.test, "error": None, "window": None,
               "size": None, "results": {}}
        try:
            frame = grab_game_frame(self.title)
            out["window"], out["size"] = frame.window, frame.size
            for key, (region, mode) in self.regions.items():
                crop = frame.crop(region)
                if crop is None:
                    out["results"][key] = {"image": None, "read": None,
                                           "error": "Region is outside the game window. Select it again."}
                    continue
                read, error = RegionRead(image=crop), None
                try:
                    if mode == "boxes":
                        read.boxes = self.ctx.ocr.read_boxes(crop)
                        read.text = " ".join(b[4] for b in sorted(read.boxes, key=lambda b: (b[1], b[0])))
                    elif mode == "text":
                        read.text = self.ctx.ocr.read_text(crop)
                except Exception as e:
                    error = f"OCR failed: {type(e).__name__}: {e}"
                out["results"][key] = {"image": to_qimage(crop), "read": read, "error": error}
        except GameNotFound as e:
            out["error"] = str(e)
        except Exception as e:  # surface anything unexpected in the status line
            out["error"] = f"Capture failed: {type(e).__name__}: {e}"
        try:
            self.signals.done.emit(out)
        except RuntimeError:
            pass  # app closed mid-read


class SessionController(QObject):
    state_changed = Signal()
    status = Signal(str)
    read_done = Signal(dict)

    def __init__(self, ctx: AppContext, modules: list[TrackerModule]):
        super().__init__()
        self.ctx = ctx
        self.modules = modules
        self.cfg = ctx.settings.section("session")
        self.session_id: int | None = None
        self.clock = ActiveClock()
        self.busy = False
        self._signals = _Signals()
        self._signals.done.connect(self._on_done)
        self.timer = QTimer(self)
        self.timer.timeout.connect(lambda: self.read_now(test=False))

    # ----- settings ----------------------------------------------------------------------
    @property
    def interval(self) -> int:
        return int(self.cfg.get("interval", 5))

    def set_interval(self, seconds: int) -> None:
        self.cfg["interval"] = seconds
        self.ctx.settings.save()
        if self.timer.isActive():
            self.timer.start(seconds * 1000)

    @property
    def character(self) -> str:
        return self.cfg.get("character", "")

    def set_character(self, name: str) -> None:
        self.cfg["character"] = name
        self.ctx.settings.save()

    @property
    def game_title(self) -> str:
        return self.cfg.get("game_title", DEFAULT_TITLE)

    def region_specs(self) -> list[tuple[TrackerModule, RegionSpec]]:
        return [(m, spec) for m in self.modules for spec in m.regions]

    def region(self, key: str) -> RelRegion | None:
        return RelRegion.from_dict(self.ctx.settings.section("regions").get(key))

    def set_region(self, key: str, region: RelRegion | None) -> None:
        self.ctx.settings.section("regions")[key] = region.as_dict() if region else None
        self.ctx.settings.save()
        for m, spec in self.region_specs():
            if spec.key == key:
                m.on_region_changed(key)

    # ----- session lifecycle -----------------------------------------------------------
    @property
    def running(self) -> bool:
        return self.clock.running

    def toggle(self) -> None:
        self.pause() if self.running else self.start()

    def start(self) -> None:
        now = time.time()
        if self.session_id is None:
            cur = self.ctx.db.execute("INSERT INTO sessions (character, started_at) VALUES (?, ?)",
                                      (self.character, now))
            self.ctx.db.commit()
            self.session_id = cur.lastrowid
            self._each("on_start", self.session_id, now)
        else:
            self._each("on_resume", now)
        self.clock.start(now)
        self.timer.start(self.interval * 1000)
        self.status.emit("Tracking…")
        self.state_changed.emit()
        self.read_now(test=False)

    def continue_session(self, row: sqlite3.Row) -> None:
        """Re-open a session the app didn't finish. It starts paused: press Resume to go on."""
        self.session_id = row["id"]
        self.clock.set_elapsed(row["active_seconds"] or 0)
        errors = self._each("on_continue", row["id"], row["active_seconds"] or 0)
        self.status.emit("Continued your unfinished session. Click Resume to keep tracking."
                         + (f" Problems: {errors}" if errors else ""))
        self.state_changed.emit()

    def ensure_running(self) -> None:
        if not self.running:
            self.start()

    def pause(self) -> None:
        if not self.running:
            return
        now = time.time()
        self.clock.pause(now)
        self.timer.stop()
        self._each("on_pause", now)
        self._save()
        self.status.emit("Paused. Gains while paused won't be counted.")
        self.state_changed.emit()

    def stop(self) -> None:
        if self.session_id is None:
            return
        now = time.time()
        self.clock.pause(now)
        self.timer.stop()
        errors = self._each("on_stop", now)
        self._save(ended_at=now)
        self.status.emit(f"Session saved ({fmt.duration(self.clock.seconds(now))} active)."
                         + (f" Problems: {errors}" if errors else ""))
        self.session_id = None
        self.clock.reset()
        self.state_changed.emit()

    def _each(self, method: str, *args) -> str:
        """Call a lifecycle method on every module; one failing never blocks the others
        or the session itself. Returns a summary of any errors."""
        errors = []
        for m in self.modules:
            try:
                getattr(m, method)(*args)
            except Exception as e:
                traceback.print_exc()
                errors.append(f"{m.title}: {type(e).__name__}: {e}")
        return "; ".join(errors)

    def active_seconds(self) -> float:
        return self.clock.seconds(time.time())

    def _save(self, ended_at: float | None = None) -> None:
        if self.session_id is None:
            return
        self.ctx.db.execute(
            "UPDATE sessions SET active_seconds=?, ended_at=COALESCE(?, ended_at) WHERE id=?",
            (self.clock.seconds(time.time()), ended_at, self.session_id),
        )
        self.ctx.db.commit()

    # ----- reading -------------------------------------------------------------------------
    def read_now(self, test: bool = False) -> None:
        regions = {spec.key: (r, spec.ocr) for _, spec in self.region_specs() if (r := self.region(spec.key))}
        if not regions:
            if test:
                self.status.emit("No regions selected yet. Set them up on the Regions tab.")
            elif self.running:
                self.status.emit("Tracking with manual entry only. Select regions on the Regions tab to read automatically.")
            return
        if self.busy:
            return
        self.busy = True
        QThreadPool.globalInstance().start(
            _ReadTask(self.game_title, regions, self.ctx, self._signals, test))

    def _on_done(self, out: dict) -> None:
        self.busy = False
        self.read_done.emit(out)
        if out["error"]:
            self.status.emit(out["error"])
            return
        tracking = self.running and not out["test"]
        messages = []
        for m in self.modules:
            reads = {}
            for spec in m.regions:
                res = out["results"].get(spec.key)
                if not res:
                    continue
                if res["error"]:
                    messages.append(f"{spec.label}: {res['error']}")
                else:
                    reads[spec.key] = res["read"]
            if not reads:
                continue
            # One tracker failing must not stop the others or the session from saving.
            try:
                if not tracking:
                    m.on_snapshot(reads)
                    continue
                msg = m.on_read(reads, out["ts"])
            except Exception as e:
                traceback.print_exc()
                messages.append(f"{m.title}: error ({type(e).__name__}: {e})")
                continue
            if msg:
                messages.append(f"{m.title}: {msg}")
        if not tracking:
            return
        self._save()
        self.status.emit(time.strftime("%H:%M:%S  ") + "  ·  ".join(messages))
