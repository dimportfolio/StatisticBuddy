import sqlite3
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from statisticbuddy.core import session
from statisticbuddy.core.module import AppContext, RegionRead
from statisticbuddy.core.storage import Settings
from statisticbuddy.modules.loot.digits import DigitReader
from statisticbuddy.modules.potions import PotionModule
from statisticbuddy.modules.potions.tracker import PotionTracker
from statisticbuddy.modules.profit import summarize

FIXTURE = Path(__file__).parent / "fixtures" / "quickslot_classic.png"
# Real game screenshots aren't published (Nexon's game art); these tests run only where they exist.
needs_fixture = unittest.skipUnless(FIXTURE.exists(), "game screenshot in tests/fixtures not present")
# Quickslot keys in the fixture (x0, x1) x (y0, y1), and the count each shows (None = skill, no number).
KEY_COLS = [(4, 42), (45, 77), (79, 113), (114, 148)]
KEY_ROWS = [(6, 39), (41, 73)]
KEY_COUNTS = [[11, None, 21, 60], [21, None, 512, 478]]


@needs_fixture
class RealQuickslotTests(unittest.TestCase):
    def test_reads_every_key(self):
        img = cv2.imread(str(FIXTURE))
        reader = DigitReader()
        got = [[(None if (r := reader.read(img[y0:y1, x0:x1], max_start=10)) is None else r.value)
                for (x0, x1) in KEY_COLS] for (y0, y1) in KEY_ROWS]
        self.assertEqual(got, KEY_COUNTS)


@needs_fixture
class LooseBoxTests(unittest.TestCase):
    def test_box_with_extra_rows_below_the_number(self):
        img = cv2.imread(str(FIXTURE))
        (x0, x1), (y0, y1) = KEY_COLS[2], KEY_ROWS[1]   # "512"
        key = img[y0:y1 + 6, x0:x1]                      # box drawn 6px too low
        key = np.vstack([key, np.full((6, key.shape[1], 3), 60, np.uint8)])
        self.assertEqual(DigitReader().read(key, max_start=10).value, 512)


class PotionTrackerTests(unittest.TestCase):
    def setUp(self):
        self.t = PotionTracker()
        self.t.start(0)

    def feed(self, ts, **counts):
        self.t.feed(counts, set(), ts)

    def test_used_rate_and_runs_out(self):
        self.feed(0, red=500)
        for minute in range(1, 11):          # 10 potions a minute, each change seen twice
            self.feed(minute * 60 - 30, red=500 - minute * 10)
            self.feed(minute * 60, red=500 - minute * 10)
        self.assertEqual(self.t.used["red"], 100)
        self.assertAlmostEqual(self.t.rate_per_hour("red"), 600, delta=60)
        # 400 left at ~600/hour -> ~40 minutes
        self.assertAlmostEqual(self.t.runs_out_in(["red"]), 40 * 60, delta=5 * 60)

    def test_buying_is_not_usage(self):
        self.feed(0, red=100)
        self.feed(10, red=90)
        self.feed(20, red=90)
        self.feed(30, red=590)
        self.feed(40, red=590)
        self.assertEqual((self.t.used["red"], self.t.bought["red"]), (10, 500))
        self.assertEqual(self.t.change("red"), 490)

    def test_combined_kind(self):
        self.feed(0, a=100, b=100)
        for i in range(1, 7):
            self.feed(i * 20 - 10, a=100 - i * 2, b=100 - i)
            self.feed(i * 20, a=100 - i * 2, b=100 - i)
        # Two HP potions used together: total left / total use rate.
        a, b = self.t.current("a"), self.t.current("b")
        rate = self.t.rate_per_hour("a") + self.t.rate_per_hour("b")
        self.assertAlmostEqual(self.t.runs_out_in(["a", "b"]), (a + b) / rate * 3600)

    def test_reselecting_a_key_does_not_count_the_jump(self):
        self.feed(0, pot=21)
        self.feed(10, pot=20)
        self.feed(20, pot=20)
        self.t.rebase("pot")                 # region moved to a different key showing 442
        self.feed(30, pot=442)
        self.feed(40, pot=441)
        self.feed(50, pot=441)
        self.assertEqual(self.t.used["pot"], 2)
        self.assertEqual(self.t.bought.get("pot", 0), 0)
        self.assertEqual(self.t.change("pot"), -2)

    def test_pause_does_not_count_usage(self):
        self.feed(0, red=100)
        self.t.pause(10)
        self.t.start(100)
        self.feed(100, red=50)      # used 50 while paused: new reference
        self.feed(110, red=50)
        self.assertEqual(self.t.used.get("red", 0), 0)


class PotionModuleTests(unittest.TestCase):
    def setUp(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        session.init_schema(db)
        self.m = PotionModule()
        self.m.init_schema(db)
        self.m.ctx = AppContext(db=db, settings=Settings(Path(tempfile.mkdtemp()) / "s.json"), ocr=None)
        self.sid = db.execute("INSERT INTO sessions (started_at) VALUES (0)").lastrowid
        self.m.on_start(self.sid, 0)
        self.img = cv2.imread(str(FIXTURE))

    def key(self, col, row):
        (x0, x1), (y0, y1) = KEY_COLS[col], KEY_ROWS[row]
        return RegionRead(image=self.img[y0:y1, x0:x1])

    @needs_fixture
    def test_reads_keys_and_values_usage(self):
        self.m.update_slot("pot_1", name="Red Potion", kind="HP", price=50)
        self.m.on_read({"pot_1": self.key(3, 0)}, 0)          # 60 red potions
        self.assertEqual(self.m.tracker.current("pot_1"), 60)
        self.m.tracker.feed({"pot_1": 55}, set(), 10)
        self.m.tracker.feed({"pot_1": 55}, set(), 20)
        self.assertEqual(self.m.cost(), 5 * 50)
        self.assertEqual(self.m.profit_parts(20), [("Potions", -250)])

    def test_restocking_mid_session_nets_out(self):
        # Buy 100 potions at 50 each (5,000 mesos spent) and use none: profit 0.
        self.m.update_slot("pot_1", price=50)
        self.m.tracker.feed({"pot_1": 10}, set(), 0)
        self.m.tracker.feed({"pot_1": 110}, set(), 10)
        self.m.tracker.feed({"pot_1": 110}, set(), 20)
        total, _ = summarize([("Mesos (net)", -5_000)] + self.m.profit_parts(20), 3600)
        self.assertEqual(total, 0)

    @needs_fixture
    def test_running_out(self):
        self.m.tracker.feed({"pot_1": 3}, set(), 0)
        blank = RegionRead(image=self.img[6:39, 45:77])   # a key showing no number
        self.m.on_read({"pot_1": blank}, 10)
        self.m.on_read({"pot_1": blank}, 20)
        self.assertEqual(self.m.tracker.current("pot_1"), 0)

    def test_start_end_saved_and_continue(self):
        self.m.update_slot("pot_1", price=50)
        self.m.tracker.feed({"pot_1": 60}, set(), 0)
        self.m.tracker.feed({"pot_1": 50}, set(), 10)
        self.m.tracker.feed({"pot_1": 50}, set(), 20)
        self.m._save()
        from statisticbuddy.modules.potions import store as pstore
        (row,) = pstore.session_rows(self.m.ctx.db, self.sid)
        self.assertEqual((row["start_count"], row["end_count"], row["used"]), (60, 50, 10))
        fresh = PotionModule()
        fresh.ctx = self.m.ctx
        fresh.on_continue(self.sid, 120)
        self.assertEqual((fresh.tracker.used, fresh.tracker.start_count("pot_1")), ({"pot_1": 10}, 60))
        self.assertEqual(fresh.cost(), 500)

    def test_history(self):
        self.m.update_slot("pot_1", price=50)
        self.m.tracker.feed({"pot_1": 60}, set(), 0)
        self.m.tracker.feed({"pot_1": 50}, set(), 10)
        self.m.tracker.feed({"pot_1": 50}, set(), 20)
        self.m.on_stop(30)
        self.assertEqual(self.m.history_values(self.m.ctx.db, self.sid), ["10", "500"])
        self.assertEqual(self.m.profit_history(self.m.ctx.db, self.sid), -500)


if __name__ == "__main__":
    unittest.main()
