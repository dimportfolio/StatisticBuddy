"""Meso module tables."""
from __future__ import annotations

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS meso_session_stats (
    session_id  INTEGER PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
    start_value INTEGER,
    end_value   INTEGER,
    gained      INTEGER NOT NULL DEFAULT 0,
    spent       INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS meso_samples (
    id         INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    ts         REAL NOT NULL,
    value      INTEGER NOT NULL,
    source     TEXT NOT NULL,
    verdict    TEXT NOT NULL,
    raw_text   TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS meso_samples_session ON meso_samples(session_id);
"""


def init_schema(db: sqlite3.Connection) -> None:
    db.executescript(SCHEMA)
    db.commit()


def create_stats(db: sqlite3.Connection, session_id: int) -> None:
    db.execute("INSERT OR IGNORE INTO meso_session_stats (session_id) VALUES (?)", (session_id,))
    db.commit()


def save_stats(db: sqlite3.Connection, session_id: int, *, start_value: int | None,
               end_value: int | None, gained: int, spent: int) -> None:
    db.execute(
        "UPDATE meso_session_stats SET start_value=?, end_value=?, gained=?, spent=? WHERE session_id=?",
        (start_value, end_value, gained, spent, session_id),
    )
    db.commit()


def add_sample(db: sqlite3.Connection, session_id: int, ts: float, value: int,
               source: str, verdict: str, raw_text: str = "") -> None:
    db.execute(
        "INSERT INTO meso_samples (session_id, ts, value, source, verdict, raw_text) VALUES (?, ?, ?, ?, ?, ?)",
        (session_id, ts, value, source, verdict, raw_text),
    )


def get_stats(db: sqlite3.Connection, session_id: int) -> sqlite3.Row | None:
    return db.execute("SELECT * FROM meso_session_stats WHERE session_id=?", (session_id,)).fetchone()
