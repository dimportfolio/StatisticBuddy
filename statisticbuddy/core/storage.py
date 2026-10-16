"""App data location, settings file and the shared SQLite database."""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
from pathlib import Path

APP_DIR = "StatisticBuddy"
OLD_APP_DIR = "MapleTracker"   # the app's name before it was renamed


def data_dir() -> Path:
    """Where the app keeps its database, settings and log.

    ``STATISTICBUDDY_DATA_DIR`` overrides it (used for testing with separate data)."""
    override = os.environ.get("STATISTICBUDDY_DATA_DIR")
    if override:
        path = Path(override)
        path.mkdir(parents=True, exist_ok=True)
        return path
    base = Path(os.environ.get("LOCALAPPDATA") or str(Path.home()))
    path = base / APP_DIR
    path.mkdir(parents=True, exist_ok=True)
    migrate_from(base / OLD_APP_DIR, path)
    return path


def migrate_from(old: Path, new: Path) -> bool:
    """Copy data from the pre-rename folder the first time, leaving the old folder as a backup."""
    if (new / "tracker.db").exists() or not (old / "tracker.db").exists():
        return False
    src = sqlite3.connect(old / "tracker.db")
    dst = sqlite3.connect(new / "tracker.db")
    try:
        src.backup(dst)   # consistent copy even if the old database is still open
    finally:
        dst.close()
        src.close()
    if (old / "settings.json").exists() and not (new / "settings.json").exists():
        shutil.copy2(old / "settings.json", new / "settings.json")
    return True


class Settings:
    """JSON settings, namespaced per module: settings.section("exp")["interval"]."""

    def __init__(self, path: Path):
        self.path = path
        try:
            self.data: dict = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.data = {}

    def section(self, name: str) -> dict:
        return self.data.setdefault(name, {})

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
        tmp.replace(self.path)


def open_db(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    return db
