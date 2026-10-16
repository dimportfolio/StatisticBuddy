import unittest

import numpy as np

from statisticbuddy.capture.game import Frame, RelRegion
from statisticbuddy.capture.screen import Region
from statisticbuddy.capture.window import GameWindow
from statisticbuddy.modules.exp.tracker import Verdict
from statisticbuddy.modules.meso.parser import parse_meso_text
from statisticbuddy.modules.meso.tracker import MesoSample, MesoTracker


class MesoParserTests(unittest.TestCase):
    def test_commas(self):
        self.assertEqual(parse_meso_text("12,345,678"), 12345678)

    def test_ocr_noise(self):
        self.assertEqual(parse_meso_text("$ 1,2O4,5l0"), 1204510)

    def test_garbage(self):
        self.assertIsNone(parse_meso_text("Mesos"))
        self.assertIsNone(parse_meso_text(""))


class MesoTrackerTests(unittest.TestCase):
    def setUp(self):
        self.t = MesoTracker(jump_abs=100_000, jump_rel=0.25)
        self.t.start(0)

    def test_gains_and_rate(self):
        self.assertEqual(self.t.feed(MesoSample(0, 1_000_000)), Verdict.BASELINE)
        self.t.feed(MesoSample(1800, 1_050_000))
        self.t.feed(MesoSample(3600, 1_100_000))
        s = self.t.stats(3600)
        self.assertEqual(s.gained, 100_000)
        self.assertAlmostEqual(s.per_hour, 100_000)
        self.assertEqual(s.net, 100_000)

    def test_spending_is_confirmed_and_not_subtracted(self):
        self.t.feed(MesoSample(0, 1_000_000))
        self.assertEqual(self.t.feed(MesoSample(5, 400_000)), Verdict.PENDING)
        self.assertEqual(self.t.feed(MesoSample(10, 400_500)), Verdict.ACCEPTED)
        s = self.t.stats(10)
        self.assertEqual(s.spent, 600_000)
        self.assertEqual(s.gained, 500)
        self.assertEqual(s.net, -599_500)

    def test_single_misread_is_ignored(self):
        self.t.feed(MesoSample(0, 1_000_000))
        self.assertEqual(self.t.feed(MesoSample(5, 100_000)), Verdict.PENDING)    # dropped digit
        self.assertEqual(self.t.feed(MesoSample(10, 1_000_200)), Verdict.ACCEPTED)
        s = self.t.stats(10)
        self.assertEqual((s.gained, s.spent), (200, 0))

    def test_big_gain_needs_confirmation(self):
        self.t.feed(MesoSample(0, 1_000_000))
        self.assertEqual(self.t.feed(MesoSample(5, 3_000_000)), Verdict.PENDING)  # sold loot
        self.assertEqual(self.t.feed(MesoSample(10, 3_000_100)), Verdict.ACCEPTED)
        self.assertEqual(self.t.stats(10).gained, 2_000_100)

    def test_reselected_region_rebaselines(self):
        self.t.feed(MesoSample(0, 1_000_000))
        self.t.feed(MesoSample(5, 1_000_100))
        self.t.rebaseline()
        self.assertEqual(self.t.feed(MesoSample(10, 9_000_000)), Verdict.BASELINE)
        self.t.feed(MesoSample(15, 9_000_050))
        s = self.t.stats(15)
        self.assertEqual((s.gained, s.spent), (150, 0))

    def test_pause_rebaselines(self):
        self.t.feed(MesoSample(0, 1_000_000))
        self.t.pause(60)
        self.t.start(120)
        self.assertEqual(self.t.feed(MesoSample(120, 5_000_000)), Verdict.BASELINE)
        self.assertEqual(self.t.stats(120).gained, 0)


class FrameTests(unittest.TestCase):
    def test_crop_inside_and_outside(self):
        img = np.arange(100 * 200 * 3, dtype=np.uint32).astype(np.uint8).reshape(100, 200, 3)
        frame = Frame(GameWindow("MapleStory", "MapleStoryClass", Region(0, 0, 200, 100)), img)
        crop = frame.crop(RelRegion(10, 20, 30, 5, 200, 100))
        self.assertEqual(crop.shape, (5, 30, 3))
        self.assertTrue(np.array_equal(crop, img[20:25, 10:40]))
        self.assertIsNone(frame.crop(RelRegion(190, 20, 30, 5, 200, 100)))

    def test_region_round_trip(self):
        r = RelRegion(1, 2, 3, 4, 800, 600)
        self.assertEqual(RelRegion.from_dict(r.as_dict()), r)
        self.assertIsNone(RelRegion.from_dict({"x": 1}))


if __name__ == "__main__":
    unittest.main()
