import sqlite3
import unittest

from mapletracker.core import session
from mapletracker.modules.exp.tracker import ExpTracker, Sample, Verdict
from mapletracker.modules.meso.tracker import MesoSample, MesoTracker


class SessionStoreTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        session.init_schema(self.db)

    def test_close_unfinished(self):
        self.db.execute("INSERT INTO sessions (started_at, ended_at, active_seconds) VALUES (100, 500, 300)")
        self.db.execute("INSERT INTO sessions (started_at, active_seconds) VALUES (1000, 723)")
        self.assertEqual(session.close_unfinished(self.db), 1)
        ends = [r["ended_at"] for r in self.db.execute("SELECT ended_at FROM sessions ORDER BY id")]
        self.assertEqual(ends, [500, 1723])

    def test_latest_unfinished_and_keep(self):
        self.db.execute("INSERT INTO sessions (started_at, active_seconds) VALUES (100, 50)")
        self.db.execute("INSERT INTO sessions (started_at, active_seconds) VALUES (1000, 600)")
        row = session.latest_unfinished(self.db)
        self.assertEqual(row["id"], 2)
        session.close_unfinished(self.db, keep=row["id"])
        open_ids = [r["id"] for r in self.db.execute("SELECT id FROM sessions WHERE ended_at IS NULL")]
        self.assertEqual(open_ids, [2])


class RestoreTests(unittest.TestCase):
    def test_exp_restore_keeps_totals_and_rebaselines(self):
        t = ExpTracker()
        t.restore(gained=5_000_000, levels=1, pct_gained=12.5, active_seconds=600)
        t.start(1000)
        self.assertEqual(t.feed(Sample(1000, 900_000_000, 90.0)), Verdict.BASELINE)
        t.feed(Sample(1060, 910_000_000, 91.0))
        s = t.stats(1060)
        self.assertEqual((s.gained, s.levels), (15_000_000, 1))
        self.assertAlmostEqual(s.active_seconds, 660)

    def test_meso_restore(self):
        t = MesoTracker()
        t.restore(gained=4_000, spent=500, start_value=300_000, active_seconds=600)
        t.start(1000)
        t.feed(MesoSample(1000, 310_000))
        t.feed(MesoSample(1010, 310_100))
        s = t.stats(1010)
        self.assertEqual((s.gained, s.spent, s.net), (4_100, 500, 3_600))


if __name__ == "__main__":
    unittest.main()
