"""Potion module table: per session and quickslot, potions used/bought and their value."""
from __future__ import annotations

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS potion_session_slots (
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    slot       TEXT NOT NULL,
    name       TEXT NOT NULL,
    kind       TEXT NOT NULL,
    price      REAL NOT NULL,
    used       INTEGER NOT NULL,
    bought     INTEGER NOT NULL,
    change     INTEGER NOT NULL,
    PRIMARY KEY (session_id, slot)
);
"""


def init_schema(db: sqlite3.Connection) -> None:
    db.executescript(SCHEMA)
    cols = {r[1] for r in db.execute("PRAGMA table_info(potion_session_slots)")}
    for col in ("start_count", "end_count"):
        if col not in cols:
            db.execute(f"ALTER TABLE potion_session_slots ADD COLUMN {col} INTEGER")
    db.commit()


def save_slot(db: sqlite3.Connection, session_id: int, slot: str, *, name: str, kind: str,
              price: float, used: int, bought: int, change: int,
              start_count: int | None = None, end_count: int | None = None) -> None:
    db.execute(
        "INSERT INTO potion_session_slots (session_id, slot, name, kind, price, used, bought, change,"
        " start_count, end_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(session_id, slot) DO UPDATE SET name=excluded.name, kind=excluded.kind,"
        " price=excluded.price, used=excluded.used, bought=excluded.bought, change=excluded.change,"
        " start_count=COALESCE(excluded.start_count, start_count),"
        " end_count=COALESCE(excluded.end_count, end_count)",
        (session_id, slot, name, kind, price, used, bought, change, start_count, end_count),
    )
    db.commit()


def session_rows(db: sqlite3.Connection, session_id: int) -> list[sqlite3.Row]:
    return db.execute("SELECT * FROM potion_session_slots WHERE session_id=?", (session_id,)).fetchall()
