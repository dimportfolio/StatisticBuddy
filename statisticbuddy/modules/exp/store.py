"""EXP module tables: per-session totals plus every reading taken."""
from __future__ import annotations

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS exp_session_stats (
    session_id INTEGER PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
    gained     INTEGER NOT NULL DEFAULT 0,
    pct_gained REAL,
    levels     INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS exp_samples (
    id         INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    ts         REAL NOT NULL,
    exp        INTEGER NOT NULL,
    pct        REAL,
    source     TEXT NOT NULL,
    verdict    TEXT NOT NULL,
    raw_text   TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS exp_samples_session ON exp_samples(session_id);
"""


def init_schema(db: sqlite3.Connection) -> None:
    db.executescript(SCHEMA)
    _migrate_v1(db)
    db.commit()


def _migrate_v1(db: sqlite3.Connection) -> None:
    """Move sessions from the first version (exp_sessions/exp_readings) into the shared tables."""
    old = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='exp_sessions'").fetchone()
    if not old:
        return
    for r in db.execute("SELECT * FROM exp_sessions").fetchall():
        cur = db.execute(
            "INSERT INTO sessions (character, started_at, ended_at, active_seconds) VALUES (?, ?, ?, ?)",
            (r["character"], r["started_at"], r["ended_at"], r["active_seconds"]),
        )
        new_id = cur.lastrowid
        db.execute("INSERT INTO exp_session_stats (session_id, gained, pct_gained, levels) VALUES (?, ?, ?, ?)",
                   (new_id, r["gained"], r["pct_gained"], r["levels"]))
        db.execute(
            "INSERT INTO exp_samples (session_id, ts, exp, pct, source, verdict, raw_text)"
            " SELECT ?, ts, exp, pct, source, verdict, raw_text FROM exp_readings WHERE session_id=?",
            (new_id, r["id"]),
        )
    db.execute("DROP TABLE IF EXISTS exp_readings")
    db.execute("DROP TABLE exp_sessions")


def create_stats(db: sqlite3.Connection, session_id: int) -> None:
    db.execute("INSERT OR IGNORE INTO exp_session_stats (session_id) VALUES (?)", (session_id,))
    db.commit()


def save_stats(db: sqlite3.Connection, session_id: int, *, gained: int,
               pct_gained: float | None, levels: int) -> None:
    db.execute("UPDATE exp_session_stats SET gained=?, pct_gained=?, levels=? WHERE session_id=?",
               (gained, pct_gained, levels, session_id))
    db.commit()


def add_sample(db: sqlite3.Connection, session_id: int, ts: float, exp: int, pct: float | None,
               source: str, verdict: str, raw_text: str = "") -> None:
    db.execute(
        "INSERT INTO exp_samples (session_id, ts, exp, pct, source, verdict, raw_text)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (session_id, ts, exp, pct, source, verdict, raw_text),
    )


def get_stats(db: sqlite3.Connection, session_id: int) -> sqlite3.Row | None:
    return db.execute("SELECT * FROM exp_session_stats WHERE session_id=?", (session_id,)).fetchone()
