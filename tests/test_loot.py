import sqlite3
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from mapletracker.core import session
from mapletracker.core.module import AppContext, RegionRead
from mapletracker.core.storage import Settings
from mapletracker.modules.loot import LootModule, store
from mapletracker.modules.loot.digits import BUILTIN_TEMPLATES, DigitReader, to_bitmap
from mapletracker.modules.loot.grid import Catalog, icon_signature, read_grid, slot_rects
from mapletracker.modules.loot.tracker import LootTracker
from mapletracker.modules.profit import summarize

FIXTURES = Path(__file__).parent / "fixtures"
# Real game screenshots aren't published (Nexon's game art); these tests run only where they exist.
needs_fixtures = unittest.skipUnless((FIXTURES / "etc_grid_classic.png").exists(),
                                     "game screenshots in tests/fixtures not present")
# Real MapleStory Classic ETC tabs and their stack counts, slot by slot.
REAL_GRIDS = {
    # Slot 13 (88) has the orange pickup highlight over its left edge.
    "etc_grid_classic.png": [2, 10, 1, 44, 1, 8, 20, 1, 5, 93, 158, 118, 12, 88, 200, 99],
    # Here the 198 bananas (slot 15) are highlighted.
    "etc_grid_classic_2.png": [2, 10, 1, 46, 1, 8, 20, 1, 5, 97, 159, 121, 12, 91, 200, 198],
}

SLOT, LINE = 32, 2
BG, LINE_COLOR = (213, 223, 225), (245, 245, 245)
# A made-up digit shape the reader has never seen, to exercise learning.
SEVEN = "######/.....#/....#./....#./...#../...#../..#.../..#.../..#..."


def reader_without_seven() -> DigitReader:
    r = DigitReader()
    r.templates = [(d, t) for d, t in r.templates if d != "7"]
    return r


def draw_number(slot, text, glyphs=None):
    """Draw text in the game's item-count font: white stroke with a black outline."""
    glyphs = glyphs or {d: to_bitmap(v[0]) for d, v in BUILTIN_TEMPLATES.items()}
    h = slot.shape[0]
    stroke = np.zeros(slot.shape[:2], bool)
    x, top = 1, h - 11
    for ch in text:
        g = glyphs[ch]
        stroke[top:top + g.shape[0], x:x + g.shape[1]] |= g
        x += g.shape[1] + 2
    outline = cv2.dilate(stroke.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool) & ~stroke
    slot[outline] = (0, 0, 0)
    slot[stroke] = (255, 255, 255)


def draw_icon(slot, kind):
    if kind == "red":
        cv2.circle(slot, (16, 11), 8, (40, 40, 220), -1)
    elif kind == "green":
        cv2.rectangle(slot, (8, 4), (24, 18), (40, 200, 40), -1)
    elif kind == "blue":
        cv2.fillPoly(slot, [np.array([[16, 3], [7, 19], [25, 19]])], (220, 120, 30))


def make_grid(stacks, cols=5, rows=6, glyphs=None):
    """stacks: {(col, row): (kind, count)} -> an inventory grid image with separator lines."""
    pitch = SLOT + LINE
    img = np.full((rows * pitch + LINE, cols * pitch + LINE, 3), LINE_COLOR, np.uint8)
    for r in range(rows):
        for c in range(cols):
            y, x = LINE + r * pitch, LINE + c * pitch
            slot = img[y:y + SLOT, x:x + SLOT]
            slot[:] = BG
            if (c, r) in stacks:
                kind, count = stacks[(c, r)]
                draw_icon(slot, kind)
                draw_number(slot, str(count), glyphs)
    return img


@needs_fixtures
class RealGridTests(unittest.TestCase):
    """Against a real screenshot of the MapleStory Classic ETC tab."""

    def grid(self, name):
        img = cv2.imread(str(FIXTURES / name))
        return img, [s for s in read_grid(img, 5, 6, DigitReader()) if not s.empty]

    def test_finds_slots_from_grid_lines(self):
        img, slots = self.grid("etc_grid_classic.png")
        self.assertEqual(len(slot_rects(img, 5, 6)), 30)
        self.assertEqual([s.index for s in slots], list(range(16)))

    def test_reads_every_stack_count(self):
        for name, counts in REAL_GRIDS.items():
            with self.subTest(name=name):
                self.assertEqual([s.quantity for s in self.grid(name)[1]], counts)

    def test_tells_items_apart(self):
        cat = Catalog()
        ids = []
        for s in self.grid("etc_grid_classic.png")[1]:
            item = cat.match(s.icon)
            if item is None:
                item = s.index
                cat.add(item, s.icon)
            ids.append(item)
        # 16 stacks, 15 items: the two banana stacks are one item.
        self.assertEqual(len(set(ids)), 15)
        self.assertEqual(ids[14], ids[15])

    def test_items_recognised_across_screenshots(self):
        # Same inventory a few minutes later, after picking things up: every stack matches.
        cat = Catalog()
        for s in self.grid("etc_grid_classic.png")[1]:
            if cat.match(s.icon) is None:
                cat.add(s.index, s.icon)
        later = [cat.match(s.icon) for s in self.grid("etc_grid_classic_2.png")[1]]
        self.assertNotIn(None, later)


class DigitTests(unittest.TestCase):
    def slot_with(self, text, glyphs=None):
        slot = np.full((SLOT, SLOT, 3), BG, np.uint8)
        draw_icon(slot, "green")
        draw_number(slot, text, glyphs)
        return slot

    def test_reads_numbers(self):
        reader = DigitReader()
        for text in ("1", "9", "20", "158", "1000", "4385"):
            with self.subTest(text=text):
                self.assertEqual(reader.read(self.slot_with(text)).value, int(text))

    def test_reads_through_pickup_highlight(self):
        # MapleStory draws a 1-px orange line on the top row and left column of a slot that
        # just received an item, right over the first digit's outline.
        from mapletracker.modules.loot.digits import is_highlighted
        reader = DigitReader()
        for text in ("8", "88", "38", "198", "1000"):
            with self.subTest(text=text):
                slot = self.slot_with(text)
                slot[0, :] = (0, 153, 255)
                slot[:, 0] = (0, 187, 255)
                self.assertTrue(is_highlighted(slot))
                self.assertEqual(reader.read(slot).value, int(text))

    def test_partly_drawn_highlight(self):
        slot = self.slot_with("188")
        slot[18:, 0] = (0, 170, 255)   # only the lower part of the frame's left line
        self.assertEqual(DigitReader().read(slot).value, 188)

    def test_banana_icon_is_not_a_highlight(self):
        from mapletracker.modules.loot.digits import is_highlighted
        slot = self.slot_with("5")
        cv2.circle(slot, (6, 10), 6, (0, 204, 255), -1)   # yellow icon near the left edge
        self.assertFalse(is_highlighted(slot))

    def test_no_number(self):
        slot = np.full((SLOT, SLOT, 3), BG, np.uint8)
        draw_icon(slot, "green")
        self.assertIsNone(DigitReader().read(slot))

    def test_learns_unknown_digit(self):
        glyphs = {d: to_bitmap(v[0]) for d, v in BUILTIN_TEMPLATES.items()}
        glyphs["7"] = to_bitmap(SEVEN)
        reader = reader_without_seven()
        read = reader.read(self.slot_with("17", glyphs))
        self.assertEqual(read.digits, ["1", None])
        self.assertIsNone(read.value)
        self.assertIsNone(reader.learn(read, "12"))    # OCR misread: the glyph looks nothing like a 2
        self.assertIsNone(reader.learn(read, "177"))   # wrong number of digits
        self.assertEqual(reader.learn(read, "17"), {"7": SEVEN})
        self.assertEqual(reader.read(self.slot_with("71", glyphs)).value, 71)


class GridTests(unittest.TestCase):
    def test_synthetic_grid(self):
        img = make_grid({(0, 0): ("red", 12), (2, 1): ("green", 1), (4, 5): ("red", 300)})
        slots = [s for s in read_grid(img, 5, 6, DigitReader()) if not s.empty]
        self.assertEqual([(s.index, s.quantity) for s in slots], [(0, 12), (7, 1), (29, 300)])
        cat = Catalog()
        cat.add(1, slots[0].icon)
        self.assertEqual(cat.match(slots[2].icon), 1)   # same item, other slot, other count
        self.assertIsNone(cat.match(slots[1].icon))

    def test_highlight_in_every_slot_position(self):
        # The frame moves to whichever slot just received an item. Wherever it lands, every
        # stack must still read correctly and still be recognised as the same item.
        stacks = {(c, r): (("red", "green", "blue")[(c + r) % 3], 10 + c * 7 + r * 31)
                  for c in range(5) for r in range(6) if (c + r) % 2 == 0}
        clean = [s for s in read_grid(make_grid(stacks), 5, 6, DigitReader()) if not s.empty]
        cat = Catalog()
        for s in clean:
            if cat.match(s.icon) is None:
                cat.add(s.index, s.icon)
        expected = [n for (c, r), (_, n) in sorted(stacks.items(), key=lambda kv: (kv[0][1], kv[0][0]))]
        pitch = SLOT + LINE
        for (c, r) in stacks:
            with self.subTest(slot=(c, r)):
                img = make_grid(stacks)
                y, x = LINE + r * pitch, LINE + c * pitch
                img[y, x:x + SLOT] = (0, 153, 255)        # top row of that slot
                img[y:y + SLOT, x] = (0, 187, 255)        # left column of that slot
                slots = [s for s in read_grid(img, 5, 6, DigitReader()) if not s.empty]
                self.assertEqual([s.quantity for s in slots], expected)
                self.assertEqual([cat.match(s.icon) for s in slots], [cat.match(s.icon) for s in clean])

    def test_signature_stable_under_noise(self):
        img = make_grid({(0, 0): ("red", 5)})
        slot = [s for s in read_grid(img, 5, 6, DigitReader()) if not s.empty][0].image
        noisy = np.clip(slot.astype(int) + np.random.default_rng(1).integers(-3, 4, slot.shape), 0, 255).astype(np.uint8)
        self.assertLess(icon_signature(noisy).distance(icon_signature(slot)), 2)


class LootTrackerTests(unittest.TestCase):
    def setUp(self):
        self.t = LootTracker()
        self.t.start(0)

    def test_gain_needs_two_matching_reads(self):
        self.t.feed({1: 10})
        self.t.feed({1: 15})
        self.assertEqual(self.t.change(1), 0)
        self.t.feed({1: 15})
        self.assertEqual(self.t.change(1), 5)

    def test_single_misread_ignored(self):
        self.t.feed({1: 10})
        self.t.feed({1: 70})
        self.t.feed({1: 10})
        self.t.feed({1: 10})
        self.assertEqual(self.t.change(1), 0)

    def test_item_unreadable_at_start_is_not_counted_as_picked_up(self):
        # Bananas' stack was highlighted at the first read, so they weren't in the starting point.
        self.t.feed({1: 10}, unreadable={2})
        self.t.feed({1: 10, 2: 613})
        self.t.feed({1: 10, 2: 613})
        self.assertEqual(self.t.change(2), 0)
        self.t.feed({1: 10, 2: 620})
        self.t.feed({1: 10, 2: 620})
        self.assertEqual(self.t.change(2), 7)

    def test_unreadable_item_keeps_count(self):
        self.t.feed({1: 10, 2: 5})
        self.t.feed({2: 6}, unreadable={1})
        self.t.feed({2: 6}, unreadable={1})
        self.assertEqual(self.t.changes(), {1: 0, 2: 1})

    def test_new_item_and_value(self):
        self.t.feed({1: 10})
        self.t.feed({1: 12, 2: 3})
        self.t.feed({1: 12, 2: 3})
        self.assertEqual(self.t.changes(), {1: 2, 2: 3})
        self.assertEqual(self.t.value({1: 25, 2: 100}), 2 * 25 + 3 * 100)

    def test_pause_banks_change_and_ignores_paused_gains(self):
        self.t.feed({1: 10})
        self.t.feed({1: 14})
        self.t.feed({1: 14})
        self.t.pause(100)
        self.t.start(200)
        self.t.feed({1: 30})
        self.t.feed({1: 31})
        self.t.feed({1: 31})
        self.assertEqual(self.t.change(1), 4 + 1)


class FakeOcr:
    def __init__(self, answer):
        self.answer = answer
        self.calls = 0

    def read_line(self, image):
        self.calls += 1
        return self.answer


class LootModuleTests(unittest.TestCase):
    def setUp(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        session.init_schema(db)
        self.m = LootModule()
        self.m.init_schema(db)
        self.ocr = FakeOcr("")
        self.m.ctx = AppContext(db=db, settings=Settings(Path(tempfile.mkdtemp()) / "s.json"), ocr=self.ocr)
        sid = db.execute("INSERT INTO sessions (started_at) VALUES (0)").lastrowid
        self.m.on_start(sid, 0)

    def read(self, stacks, glyphs=None):
        return self.m.on_read({"etc_grid": RegionRead(image=make_grid(stacks, glyphs=glyphs))}, 0)

    def test_pickup_move_and_sell(self):
        self.read({(0, 0): ("red", 10), (1, 0): ("green", 25), (2, 0): ("blue", 1)})
        ore, leaf, gem = sorted(self.m.items)
        for item, price in ((ore, 50), (leaf, 10), (gem, 1000)):
            self.m.set_price(item, price)
        picked = {(0, 0): ("red", 14), (1, 0): ("green", 40), (4, 3): ("blue", 2)}
        self.read(picked)
        self.read(picked)
        self.assertEqual(self.m.tracker.changes(), {ore: 4, leaf: 15, gem: 1})
        self.assertEqual(self.m.total_value(), 4 * 50 + 15 * 10 + 1000)
        sold = {(0, 0): ("red", 14), (4, 3): ("blue", 2)}
        self.read(sold)
        self.read(sold)
        self.assertEqual(self.m.tracker.change(leaf), -25)

    def test_totals_are_remembered_across_sessions(self):
        self.read({(0, 0): ("red", 10)})
        ore = min(self.m.items)
        self.m.set_price(ore, 50)
        self.read({(0, 0): ("red", 14)})
        self.read({(0, 0): ("red", 14)})
        self.assertEqual(self.m.held_value(), 14 * 50)
        self.assertEqual(self.m.holdings(), [("ETC items", 700)])
        self.m.on_stop(100)
        # A new session (or app restart): the total is still known, session change starts at 0.
        (row, _), = store.load_items(self.m.ctx.db)
        self.assertEqual(row["last_count"], 14)
        self.assertEqual(self.m.held_value(), 700)
        self.assertEqual(self.m.total_value(), 0)

    def test_start_and_end_counts_saved(self):
        self.read({(0, 0): ("red", 10)})
        ore = min(self.m.items)
        self.read({(0, 0): ("red", 10), (1, 0): ("green", 3)})
        self.read({(0, 0): ("red", 14), (1, 0): ("green", 3)})
        self.read({(0, 0): ("red", 14), (1, 0): ("green", 3)})
        leaf = max(self.m.items)
        rows = {r["item_id"]: r for r in store.session_items(self.m.ctx.db, self.m.session_id)}
        self.assertEqual((rows[ore]["start_count"], rows[ore]["end_count"], rows[ore]["change"]), (10, 14, 4))
        self.assertEqual((rows[leaf]["start_count"], rows[leaf]["end_count"], rows[leaf]["change"]), (0, 3, 3))
        start_col = [r for r in self.m.rows() if r[0] == ore][0][2]
        self.assertEqual(start_col, 10)

    def test_continue_after_crash(self):
        self.read({(0, 0): ("red", 10)})
        ore = min(self.m.items)
        self.read({(0, 0): ("red", 14)})
        self.read({(0, 0): ("red", 14)})
        sid = self.m.session_id
        # The app closes without Stop & save; a fresh module continues from the database.
        fresh = LootModule()
        fresh.ctx = self.m.ctx
        fresh.catalog, fresh.items = self.m.catalog, self.m.items
        fresh.on_continue(sid, 300)
        self.assertEqual(fresh.tracker.changes(), {ore: 4})
        self.assertEqual(fresh.tracker.start_counts, {ore: 10})
        self.assertEqual(fresh.tracker.clock.seconds(0), 300)
        fresh.on_resume(1000)
        for n in (20, 21, 21):   # picked up 6 while closed (not counted), then 1 more
            fresh.on_read({"etc_grid": RegionRead(image=make_grid({(0, 0): ("red", n)}))}, 1000)
        self.assertEqual(fresh.tracker.change(ore), 5)

    def test_snapshot_outside_session_updates_totals_only(self):
        self.read({(0, 0): ("red", 200), (1, 0): ("red", 200), (2, 0): ("red", 155)})
        banana = min(self.m.items)
        self.m.on_stop(10)
        self.m.on_snapshot({"etc_grid": RegionRead(image=make_grid(
            {(0, 0): ("red", 200), (1, 0): ("red", 200), (2, 0): ("red", 160)}))})
        self.assertEqual(self.m.items[banana]["have"], 560)
        self.assertEqual(self.m.tracker.changes(), {})   # nothing counted as gained

    @needs_fixtures
    def test_highlighted_stack_with_ocr_available_does_not_crash(self):
        # Real ETC tab where one stack has the orange "selected" bar; OCR fallback is on.
        img = cv2.imread(str(FIXTURES / "etc_grid_classic.png"))
        msg = self.m.on_read({"etc_grid": RegionRead(image=img)}, 0)
        self.assertIn("starting point", msg)
        self.assertEqual(self.ocr.calls, 0)
        banana = self.m.catalog.match([s for s in self.m._slots(RegionRead(image=img))][14].icon)
        self.assertEqual(self.m.tracker.current[banana], 200 + 99)

    def test_unpriced_items_are_flagged_in_profit(self):
        self.read({(0, 0): ("red", 10), (1, 0): ("green", 5)})
        ore, leaf = sorted(self.m.items)
        self.m.set_price(ore, 50)
        gained = {(0, 0): ("red", 12), (1, 0): ("green", 6)}
        self.read(gained)
        self.read(gained)
        (label, value), = self.m.profit_parts(0)
        self.assertEqual(value, 100)
        self.assertIn("1 item(s) with no price", label)

    def test_two_stacks_of_one_item_are_summed(self):
        self.read({(0, 0): ("red", 200), (1, 0): ("red", 5)})
        self.assertEqual(len(self.m.items), 1)
        self.assertEqual(list(self.m.tracker.current.values()), [205])

    def test_closed_inventory_is_skipped(self):
        self.read({(0, 0): ("red", 10)})
        game_world = np.random.default_rng(2).integers(0, 255, (206, 172, 3), dtype=np.uint8)
        msg = self.m.on_read({"etc_grid": RegionRead(image=game_world)}, 0)
        self.assertIn("skipped", msg)
        self.assertEqual(len(self.m.items), 1)

    def test_selling_everything_empties_grid(self):
        self.read({(0, 0): ("red", 10)})
        self.read({})
        self.read({})
        self.assertEqual(self.m.tracker.change(min(self.m.items)), -10)

    def test_unknown_digit_learned_with_ocr_and_saved(self):
        glyphs = {d: to_bitmap(v[0]) for d, v in BUILTIN_TEMPLATES.items()}
        glyphs["7"] = to_bitmap(SEVEN)
        self.m._digits = reader_without_seven()
        self.ocr.answer = "17"
        self.read({(0, 0): ("red", 17)}, glyphs)
        self.assertEqual(list(self.m.tracker.current.values()), [17])
        self.assertEqual(self.m.cfg["glyphs"], {"7": [SEVEN]})
        calls = self.ocr.calls
        self.read({(0, 0): ("red", 77)}, glyphs)   # now known: no OCR needed
        self.assertEqual(self.ocr.calls, calls)

    def test_unreadable_count_doesnt_look_like_selling(self):
        glyphs = {d: to_bitmap(v[0]) for d, v in BUILTIN_TEMPLATES.items()}
        glyphs["7"] = to_bitmap(SEVEN)
        self.m._digits = reader_without_seven()
        self.read({(0, 0): ("red", 10)})
        self.ocr.answer = "garbage"
        self.read({(0, 0): ("red", 17)}, glyphs)
        self.read({(0, 0): ("red", 17)}, glyphs)
        self.assertEqual(self.m.tracker.change(min(self.m.items)), 0)


class ProfitTests(unittest.TestCase):
    def test_summarize(self):
        total, rate = summarize([("Mesos", 30_000), ("Loot", 10_000)], 1800)
        self.assertEqual(total, 40_000)
        self.assertAlmostEqual(rate, 80_000)
        self.assertIsNone(summarize([("Mesos", 5)], 10)[1])

    def test_selling_loot_is_not_double_counted(self):
        loot = LootTracker()
        loot.start(0)
        loot.feed({1: 0})
        loot.feed({1: 100})
        loot.feed({1: 100})
        loot.feed({})
        loot.feed({})
        total, _ = summarize([("Mesos", 5_000), ("Loot", loot.value({1: 50}))], 3600)
        # 100 ore picked up and sold for 5,000: profit is 5,000, counted once.
        self.assertEqual(total, 5_000)


class NetWorthTests(unittest.TestCase):
    def test_net_worth_sums_holdings_and_is_saved_per_session(self):
        from mapletracker.core.module import TrackerModule
        from mapletracker.modules.profit import ProfitModule

        class Holding(TrackerModule):
            def __init__(self, label, value):
                self.label, self.value = label, value

            def holdings(self):
                return [(self.label, self.value)]

        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        session.init_schema(db)
        profit = ProfitModule()
        profit.init_schema(db)
        modules = [profit, Holding("Mesos", 285_000), Holding("ETC items", 12_000)]

        class FakeSession:
            pass
        ctx = AppContext(db=db, settings=Settings(Path(tempfile.mkdtemp()) / "s.json"), ocr=None,
                         session=FakeSession())
        ctx.session.modules = modules
        profit.ctx = ctx
        sid = db.execute("INSERT INTO sessions (started_at, active_seconds) VALUES (0, 3600)").lastrowid
        profit.on_start(sid, 0)
        self.assertEqual(sum(v for _, v in profit.holdings()), 297_000)
        profit.on_stop(3600)
        self.assertEqual(profit.history_values(db, sid)[2], "297.00K")


class StoreTests(unittest.TestCase):
    def test_items_and_session_round_trip(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        session.init_schema(db)
        store.init_schema(db)
        slot = [s for s in read_grid(make_grid({(0, 0): ("red", 3)}), 5, 6, DigitReader()) if not s.empty][0]
        item = store.add_item(db, slot.icon, b"png")
        store.update_item(db, item, name="Ore", npc_price=25)
        (row, loaded), = store.load_items(db)
        self.assertEqual((row["name"], row["npc_price"], loaded), ("Ore", 25, slot.icon))
        sid = db.execute("INSERT INTO sessions (started_at) VALUES (0)").lastrowid
        self.assertEqual(store.save_session(db, sid, {item: 4}, {item: 25}), 100)
        self.assertEqual(store.save_session(db, sid, {item: 6}, {item: 25}), 150)
        self.assertEqual(store.session_value(db, sid), 150)


if __name__ == "__main__":
    unittest.main()
