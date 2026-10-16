import unittest

from statisticbuddy.modules.exp.parser import ExpReading, parse_exp_text
from statisticbuddy.modules.exp.tracker import ExpTracker, Sample, Verdict


class ParserTests(unittest.TestCase):
    def test_typical_bar(self):
        self.assertEqual(parse_exp_text("EXP. 12345678901 [45.678%]"), ExpReading(12345678901, 45.678))

    def test_commas_and_spaces(self):
        self.assertEqual(parse_exp_text("EXP 1,234,567 [ 3.21 % ]"), ExpReading(1234567, 3.21))

    def test_ocr_letter_confusion(self):
        self.assertEqual(parse_exp_text("EXP 12O45l78 [O.5%]"), ExpReading(12045178, 0.5))

    def test_missing_percent_sign(self):
        self.assertEqual(parse_exp_text("98765432 [12.345"), ExpReading(98765432, 12.345))

    def test_stray_digit_not_merged(self):
        self.assertEqual(parse_exp_text("EXP. 2 450000000 [45.000%]"), ExpReading(450000000, 45.0))

    def test_no_percent(self):
        self.assertEqual(parse_exp_text("EXP 5555555"), ExpReading(5555555, None))

    def test_garbage(self):
        self.assertIsNone(parse_exp_text("Loading..."))
        self.assertIsNone(parse_exp_text(""))


TOTAL = 1_000_000_000  # EXP needed for the level in these tests


def s(ts, pct, source="ocr"):
    return Sample(ts, int(TOTAL * pct / 100), pct, source)


class TrackerTests(unittest.TestCase):
    def setUp(self):
        self.t = ExpTracker()
        self.t.start(0)

    def test_steady_progress(self):
        self.assertEqual(self.t.feed(s(0, 10.0)), Verdict.BASELINE)
        self.assertEqual(self.t.feed(s(1800, 12.0)), Verdict.ACCEPTED)
        self.assertEqual(self.t.feed(s(3600, 14.0)), Verdict.ACCEPTED)
        st = self.t.stats(3600)
        self.assertEqual(st.gained, 40_000_000)
        self.assertAlmostEqual(st.exp_per_hour, 40_000_000)
        self.assertAlmostEqual(st.pct_per_hour, 4.0)
        self.assertAlmostEqual(st.pct_gained, 4.0)
        self.assertAlmostEqual(st.eta_seconds, 86 / 4 * 3600, delta=60)

    def test_single_misread_is_dropped(self):
        self.t.feed(s(0, 10.0))
        # An extra digit read by OCR: wildly inconsistent, held as a candidate.
        bad = Sample(5, 1_000_000_000_0, 10.01)
        self.assertEqual(self.t.feed(bad), Verdict.PENDING)
        self.assertEqual(self.t.feed(s(10, 10.02)), Verdict.ACCEPTED)
        self.assertEqual(self.t.stats(10).gained, 200_000)

    def test_level_up_needs_confirmation(self):
        self.t.feed(s(0, 99.0))
        self.assertEqual(self.t.feed(Sample(10, 5_000_000, 0.4)), Verdict.PENDING)
        self.assertEqual(self.t.feed(Sample(20, 6_000_000, 0.5)), Verdict.LEVEL_UP)
        st = self.t.stats(20)
        self.assertEqual(st.levels, 1)
        # 1% left on the old level + 6M on the new one
        self.assertEqual(st.gained, 10_000_000 + 6_000_000)

    def test_pause_does_not_count(self):
        self.t.feed(s(0, 10.0))
        self.t.feed(s(600, 11.0))
        self.t.pause(600)
        self.assertEqual(self.t.feed(s(900, 20.0)), Verdict.IGNORED)
        self.t.start(1200)
        self.assertEqual(self.t.feed(s(1200, 20.0)), Verdict.BASELINE)
        self.t.feed(s(1800, 21.0))
        st = self.t.stats(1800)
        self.assertEqual(st.gained, 20_000_000)
        self.assertAlmostEqual(st.active_seconds, 1200)

    def test_manual_entry_is_trusted(self):
        self.t.feed(s(0, 10.0, "manual"), trusted=True)
        self.assertEqual(self.t.feed(s(60, 40.0, "manual"), trusted=True), Verdict.ACCEPTED)
        self.assertEqual(self.t.stats(60).gained, 300_000_000)


if __name__ == "__main__":
    unittest.main()
