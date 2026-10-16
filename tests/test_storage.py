import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from statisticbuddy.core.storage import migrate_from


class MigrationTests(unittest.TestCase):
    def setUp(self):
        root = Path(tempfile.mkdtemp())
        self.old, self.new = root / "MapleTracker", root / "StatisticBuddy"
        self.old.mkdir()
        self.new.mkdir()
        db = sqlite3.connect(self.old / "tracker.db")
        db.execute("CREATE TABLE sessions (id INTEGER PRIMARY KEY, started_at REAL)")
        db.execute("INSERT INTO sessions (started_at) VALUES (123)")
        db.commit()
        db.close()
        (self.old / "settings.json").write_text(json.dumps({"loot": {"cols": 5}}))

    def test_copies_data_once_and_keeps_old(self):
        self.assertTrue(migrate_from(self.old, self.new))
        db = sqlite3.connect(self.new / "tracker.db")
        self.assertEqual(db.execute("SELECT started_at FROM sessions").fetchall(), [(123.0,)])
        db.close()
        self.assertEqual(json.loads((self.new / "settings.json").read_text()), {"loot": {"cols": 5}})
        self.assertTrue((self.old / "tracker.db").exists())          # old folder kept as a backup
        self.assertFalse(migrate_from(self.old, self.new))           # never overwrites new data

    def test_nothing_to_migrate(self):
        (self.old / "tracker.db").unlink()
        self.assertFalse(migrate_from(self.old, self.new))
        self.assertFalse((self.new / "tracker.db").exists())


if __name__ == "__main__":
    unittest.main()
