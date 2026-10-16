"""Loot module tables: the item catalog (icon fingerprint, name, NPC price) and per-session changes."""
from __future__ import annotations

import sqlite3
import time

from statisticbuddy.modules.loot.grid import Icon

SCHEMA = """
CREATE TABLE IF NOT EXISTS loot_items (
    id         INTEGER PRIMARY KEY,
    icon_hash  TEXT NOT NULL,
    icon_color TEXT NOT NULL,
    name       TEXT NOT NULL,
    npc_price  REAL NOT NULL DEFAULT 0,
    icon_png   BLOB,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS loot_session_items (
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    item_id    INTEGER NOT NULL REFERENCES loot_items(id) ON DELETE CASCADE,
    change     INTEGER NOT NULL,
    value      REAL NOT NULL,
    PRIMARY KEY (session_id, item_id)
);
CREATE TABLE IF NOT EXISTS loot_session_stats (
    session_id INTEGER PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
    value      REAL NOT NULL DEFAULT 0
);
"""


def init_schema(db: sqlite3.Connection) -> None:
    db.executescript(SCHEMA)
    session_cols = {r[1] for r in db.execute("PRAGMA table_info(loot_session_items)")}
    for col in ("start_count", "end_count"):
        if col not in session_cols:
            db.execute(f"ALTER TABLE loot_session_items ADD COLUMN {col} INTEGER")
    columns = {r[1] for r in db.execute("PRAGMA table_info(loot_items)")}
    if "last_count" not in columns:
        db.execute("ALTER TABLE loot_items ADD COLUMN last_count INTEGER")
    if "icon_thumb" not in columns:
        db.execute("ALTER TABLE loot_items ADD COLUMN icon_thumb BLOB")
        # Items detected by the first grid reader can't be matched any more; drop the ones
        # never named or priced so they don't clutter the table.
        db.execute("DELETE FROM loot_items WHERE npc_price = 0 AND name = 'Item #' || id")
    db.commit()


def _icon(row) -> Icon:
    b, g, r = (int(v) for v in row["icon_color"].split(","))
    return Icon(int(row["icon_hash"], 16), (b, g, r), row["icon_thumb"] or b"")


def load_items(db: sqlite3.Connection) -> list[tuple[sqlite3.Row, Icon]]:
    return [(r, _icon(r)) for r in db.execute("SELECT * FROM loot_items ORDER BY id")]


def add_item(db: sqlite3.Connection, icon: Icon, png: bytes | None) -> int:
    cur = db.execute(
        "INSERT INTO loot_items (icon_hash, icon_color, icon_thumb, name, icon_png, created_at)"
        " VALUES (?, ?, ?, '', ?, ?)",
        (f"{icon.hash:016x}", ",".join(map(str, icon.color)), icon.thumb, png, time.time()),
    )
    item_id = cur.lastrowid
    db.execute("UPDATE loot_items SET name=? WHERE id=?", (f"Item #{item_id}", item_id))
    db.commit()
    return item_id


def update_item(db: sqlite3.Connection, item_id: int, *, name: str | None = None,
                npc_price: float | None = None) -> None:
    if name is not None:
        db.execute("UPDATE loot_items SET name=? WHERE id=?", (name, item_id))
    if npc_price is not None:
        db.execute("UPDATE loot_items SET npc_price=? WHERE id=?", (npc_price, item_id))
    db.commit()


def save_counts(db: sqlite3.Connection, counts: dict[int, int]) -> None:
    """Remember how many of each item you hold (last confirmed read)."""
    db.executemany("UPDATE loot_items SET last_count=? WHERE id=?", [(c, i) for i, c in counts.items()])
    db.commit()


def delete_item(db: sqlite3.Connection, item_id: int) -> None:
    db.execute("DELETE FROM loot_items WHERE id=?", (item_id,))
    db.commit()


def save_session(db: sqlite3.Connection, session_id: int, changes: dict[int, int],
                 prices: dict[int, float], starts: dict[int, int] | None = None,
                 ends: dict[int, int] | None = None) -> float:
    """Save each item's change, value, and count at the start and (so far) end of the session."""
    starts, ends = starts or {}, ends or {}
    total = 0.0
    for item_id in set(changes) | set(starts):
        change = changes.get(item_id, 0)
        value = change * prices.get(item_id, 0)
        total += value
        db.execute(
            "INSERT INTO loot_session_items (session_id, item_id, change, value, start_count, end_count)"
            " VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(session_id, item_id) DO UPDATE SET"
            " change=excluded.change, value=excluded.value,"
            " start_count=COALESCE(excluded.start_count, start_count),"
            " end_count=COALESCE(excluded.end_count, end_count)",
            (session_id, item_id, change, value, starts.get(item_id), ends.get(item_id)),
        )
    db.execute(
        "INSERT INTO loot_session_stats (session_id, value) VALUES (?, ?)"
        " ON CONFLICT(session_id) DO UPDATE SET value=excluded.value",
        (session_id, total),
    )
    db.commit()
    return total


def session_items(db: sqlite3.Connection, session_id: int) -> list[sqlite3.Row]:
    return db.execute("SELECT * FROM loot_session_items WHERE session_id=?", (session_id,)).fetchall()


def session_value(db: sqlite3.Connection, session_id: int) -> float | None:
    r = db.execute("SELECT value FROM loot_session_stats WHERE session_id=?", (session_id,)).fetchone()
    return None if r is None else r["value"]
