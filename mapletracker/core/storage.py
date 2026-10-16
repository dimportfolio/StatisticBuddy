"""App data location, settings file and the shared SQLite database."""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path


def data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    path = Path(base) / "MapleTracker"
    path.mkdir(parents=True, exist_ok=True)
    return path


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
