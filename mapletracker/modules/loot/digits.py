"""Read inventory stack counts by matching MapleStory's pixel font exactly.

Stack counts are drawn in a fixed bitmap font at the bottom-left of each slot:
a 1-pixel white/light-blue stroke inside a pure-black outline, 9 pixels tall.
Matching that font digit by digit is far more reliable than general OCR at this
size. All ten digits were captured from MapleStory Classic; if a client draws one
differently, it's reported as unknown so the caller can learn it.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

GLYPH_H = 9
BAND_ROWS = 14  # digits live in the bottom rows of a slot

# Fill-stroke bitmaps ('#' = stroke), captured from the game's item-count font.
BUILTIN_TEMPLATES: dict[str, list[str]] = {
    "0": [".####./#....#/#....#/#....#/#....#/#....#/#....#/#....#/.####."],
    "1": ["..#/###/..#/..#/..#/..#/..#/..#/..#"],
    "2": [".####./#....#/.....#/.....#/....#./..##../.#..../#...../######"],
    "3": [".####./#....#/.....#/.....#/..###./.....#/.....#/#....#/.####."],
    "4": ["....#./...##./..#.#./.#..#./#...#./######/....#./....#./....#."],
    "5": ["######/#...../#...../#####./.....#/.....#/.....#/#....#/.####."],
    "6": ["..###./.#..../#...../#####./#....#/#....#/#....#/#....#/.####."],
    "7": ["######/.....#/....#./....#./...#../...#../..#.../..#.../.#...."],
    "8": [".####./#....#/#....#/#....#/.####./#....#/#....#/#....#/.####."],
    "9": [".####./#....#/#....#/#....#/#....#/.#####/.....#/.....#/.####."],
}


def to_bitmap(s: str) -> np.ndarray:
    return np.array([[c == "#" for c in row] for row in s.split("/")], dtype=bool)


def to_string(bm: np.ndarray) -> str:
    return "/".join("".join("#" if v else "." for v in row) for row in bm)


@dataclass
class CountRead:
    value: int | None                   # None when a digit couldn't be identified
    digits: list[str | None]            # one entry per glyph; None = unknown
    glyphs: list[np.ndarray]            # stroke bitmap per glyph (for learning)
    strip: np.ndarray | None = None     # cleaned number image (dark digits on white), for OCR fallback
    damaged: bool = False               # read through the pickup highlight: never learn from it


def _orange(px: np.ndarray) -> np.ndarray:
    b, g, r = (px[..., i].astype(int) for i in range(3))
    return (b < 60) & (r > 200) & (g >= 100) & (g <= 230)


def is_highlighted(slot: np.ndarray) -> bool:
    """True if the slot has the orange pickup/selection frame (top row and left column)."""
    if slot.shape[0] < 4 or slot.shape[1] < 4:
        return False
    return _orange(slot[0]).mean() >= 0.7 and _orange(slot[:, 0]).mean() >= 0.7


def stroke_mask(band: np.ndarray) -> np.ndarray:
    """Pixels belonging to the digits' light stroke.

    The stroke is 1 pixel wide with the black outline on both sides, so a stroke pixel
    has black on two opposite sides (left/right, above/below or diagonally). Light icon
    pixels drawn under the number almost never do."""
    b, g, r = (band[:, :, i].astype(int) for i in range(3))
    black = np.pad((b <= 10) & (g <= 10) & (r <= 10), 1)
    light = (b >= 235) & (g >= 185) & (r >= 140)
    h, w = light.shape

    def n(dy, dx):
        return black[1 + dy:1 + dy + h, 1 + dx:1 + dx + w]

    between_black = ((n(0, -1) & n(0, 1)) | (n(-1, 0) & n(1, 0))
                     | (n(-1, -1) & n(1, 1)) | (n(-1, 1) & n(1, -1)))
    return light & between_black


class DigitReader:
    def __init__(self, extra: dict[str, list[str]] | None = None, tolerance: float = 0.22):
        self.tolerance = tolerance
        self.templates: list[tuple[str, np.ndarray]] = []
        for source in (BUILTIN_TEMPLATES, extra or {}):
            for d, items in source.items():
                for s in items:
                    self.add(d, s)

    def add(self, digit: str, bitmap: str | np.ndarray) -> None:
        bm = to_bitmap(bitmap) if isinstance(bitmap, str) else bitmap.astype(bool)
        if bm.shape[0] == GLYPH_H and not any(d == digit and t.shape == bm.shape and (t == bm).all()
                                              for d, t in self.templates):
            self.templates.append((digit, bm))

    @staticmethod
    def _care(t: np.ndarray) -> np.ndarray:
        """Where a template's stroke and black outline are (one column wider than the glyph).
        Pixels outside that are background or icon and are ignored when matching."""
        padded = np.pad(t, ((0, 0), (0, 1)))
        return cv2.dilate(padded.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0

    def _match(self, window: np.ndarray) -> tuple[str | None, int]:
        """Best digit for a stroke window starting at its left edge; returns (digit, width)."""
        best, best_w, best_err = None, 0, None
        for d, t in self.templates:
            h, w = t.shape
            if window.shape[1] < w:
                continue
            win = np.zeros((h, w + 1), bool)
            win[:, :min(w + 1, window.shape[1])] = window[:, :w + 1]
            tpl = np.pad(t, ((0, 0), (0, 1)))
            care = self._care(t)
            # Missing stroke, plus extra stroke where this digit's outline should be.
            err = int((tpl & ~win).sum() + (win & ~tpl & care).sum())
            limit = max(2, int(t.sum() * self.tolerance))
            if err <= limit and (best_err is None or err / t.sum() < best_err):
                best, best_w, best_err = d, w, err / t.sum()
        return best, best_w

    def read(self, slot: np.ndarray, max_start: int = 4) -> CountRead | None:
        """Read the stack count in a slot image; None if no number is drawn.

        ``max_start``: how far from the left edge the number may begin (numbers are drawn
        at the slot's left edge; allow more when the box may include a margin)."""
        # The pickup highlight moves to whichever slot just received an item: a 1-pixel orange
        # line on that slot's top row and left column. The number starts at the left edge, so
        # the line sits exactly where the first digit's black outline is. Put the outline back
        # (any orange pixel on the edge, so a partly drawn frame is handled too).
        highlighted = is_highlighted(slot)
        left, top_row = _orange(slot[:, 0]), _orange(slot[0])
        if left.any() or top_row.any():
            slot = slot.copy()
            slot[left, 0] = 0
            slot[0, top_row] = 0
        # The number is the lowest text in the slot. Find its baseline rather than assuming
        # the box ends right under it (a box drawn a bit loose has empty rows below).
        rows_with_stroke = np.nonzero(stroke_mask(slot)[:, :max_start + 12].any(axis=1))[0]
        if len(rows_with_stroke) == 0:
            return None
        bottom = int(rows_with_stroke[-1])
        band = slot[max(0, bottom - BAND_ROWS + 3):bottom + 3, :]
        fill = stroke_mask(band)
        xs = np.nonzero(fill.sum(axis=0) >= 1)[0]
        if len(xs) == 0 or xs[0] > max_start:
            return None
        x = int(xs[0])
        # Digits sit on a fixed baseline; icon pixels may poke in above them, so anchor at the bottom.
        ys = np.nonzero(fill[:, x:x + 6].any(axis=1))[0]
        top = int(ys[-1]) - GLYPH_H + 1
        if top < 0:
            return None
        rows = fill[top:top + GLYPH_H]

        digits, glyphs = [], []
        width = rows.shape[1]
        while x < width:
            d, w = self._match(rows[:, x:x + 8])
            if d is None:
                # Something at exactly the digit spacing that spans the full glyph height is a
                # digit we don't know yet; anything shorter (icon pixels) ends the number.
                span = np.nonzero(rows[:, x:x + 6].any(axis=1))[0]
                if not (len(span) and span[0] == 0 and span[-1] == GLYPH_H - 1):
                    break
                w = self._glyph_width(rows, x)
                digits.append(None)
            else:
                digits.append(d)
            glyphs.append(rows[:, x:x + w].copy())
            x += w + 2   # glyphs are always 2 pixels apart
            if x >= width or rows[:, x:x + 2].sum() < 2:
                break

        if not digits:
            return None
        x = min(x, width)
        strip = np.full((GLYPH_H + 8, x + 8), 255, np.uint8)
        strip[4:4 + GLYPH_H, 4:4 + x][rows[:, :x]] = 0
        value = int("".join(digits)) if all(d is not None for d in digits) else None
        return CountRead(value, digits, glyphs, strip, damaged=highlighted)

    @staticmethod
    def _glyph_width(rows: np.ndarray, x: int) -> int:
        w = 1
        while x + w < rows.shape[1] and rows[:, x + w].any() and w < 7:
            w += 1
        return w

    def learn(self, read: CountRead, text: str) -> dict[str, str] | None:
        """Given the true digits for a read with unknowns, add the unknown glyphs as templates.

        Returns {digit: bitmap} learned, or None if ``text`` doesn't fit the glyphs."""
        if len(text) != len(read.digits) or not text.isdigit():
            return None
        if any(d is not None and d != t for d, t in zip(read.digits, text)):
            return None
        # OCR may be wrong too: never teach a digit we already know a shape that looks
        # nothing like this one.
        for d, t, g in zip(read.digits, text, read.glyphs):
            known = [tpl for k, tpl in self.templates if k == t]
            if d is None and known and not any(
                    tpl.shape == g.shape and (tpl != g).sum() <= tpl.sum() * self.tolerance * 2 for tpl in known):
                return None
        learned = {}
        for d, t, g in zip(read.digits, text, read.glyphs):
            if d is None:
                self.add(t, g)
                learned[t] = to_string(g)
        return learned
