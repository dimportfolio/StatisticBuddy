"""Read an inventory grid: find the slots, tell empty from occupied, fingerprint
each item icon and read its stack count. Pure numpy/OpenCV so it can be unit tested."""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from mapletracker.modules.loot.digits import BAND_ROWS, CountRead, DigitReader


THUMB = 8  # icons are compared as THUMB x THUMB colour thumbnails


@dataclass(frozen=True)
class Icon:
    hash: int                    # 64-bit difference hash of the icon's shape
    color: tuple[int, int, int]  # mean BGR colour of the icon's own pixels
    thumb: bytes = b""           # THUMB x THUMB x 3 BGR thumbnail

    def distance(self, other: Icon) -> float:
        """Mean colour difference per pixel (0 = identical). Items that share a shape but
        differ in colour (e.g. ores) are told apart by this."""
        if self.thumb and other.thumb:
            a = np.frombuffer(self.thumb, np.uint8).astype(np.int16)
            b = np.frombuffer(other.thumb, np.uint8).astype(np.int16)
            return float(np.abs(a - b).mean())
        shape = bin(self.hash ^ other.hash).count("1")
        color = max(abs(a - b) for a, b in zip(self.color, other.color))
        return shape + color / 3


@dataclass
class Slot:
    index: int
    empty: bool
    icon: Icon | None
    count: CountRead | None   # None when no number is drawn
    image: np.ndarray         # BGR crop of the slot interior

    @property
    def quantity(self) -> int | None:
        """Stack size, 1 if no number is shown, None if the number couldn't be read."""
        if self.count is None:
            return 1
        return self.count.value


def _line_runs(profile: np.ndarray, drop: float = 15) -> list[tuple[int, int]]:
    thr = profile.max() - drop
    runs, start = [], None
    for i, v in enumerate(list(profile) + [-1]):
        if v >= thr and start is None:
            start = i
        elif v < thr and start is not None:
            runs.append((start, i - 1))
            start = None
    return runs


def _segments(profile: np.ndarray, n: int) -> list[tuple[int, int]] | None:
    """Slot interiors between the bright separator lines, if exactly n are found."""
    size = len(profile)
    edges = [(-1, -1)] + _line_runs(profile) + [(size, size)]
    min_len = size / n * 0.6
    segs = [(a[1] + 1, b[0]) for a, b in zip(edges, edges[1:]) if b[0] - (a[1] + 1) >= min_len]
    return segs if len(segs) == n else None


def slot_rects(image: np.ndarray, cols: int, rows: int) -> list[tuple[int, int, int, int]]:
    """(x0, y0, x1, y1) for each slot, row by row. Uses the grid's separator lines when
    they can be found, otherwise divides the box evenly."""
    h, w = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32)
    xs = _segments(gray.mean(axis=0), cols) or [(round(c * w / cols), round((c + 1) * w / cols)) for c in range(cols)]
    ys = _segments(gray.mean(axis=1), rows) or [(round(r * h / rows), round((r + 1) * h / rows)) for r in range(rows)]
    return [(x0, y0, x1, y1) for (y0, y1) in ys for (x0, x1) in xs]


def _middle(slot: np.ndarray) -> np.ndarray:
    h, w = slot.shape[:2]
    return slot[int(h * 0.25):max(int(h * 0.7), int(h * 0.25) + 1), int(w * 0.25):max(int(w * 0.75), int(w * 0.25) + 1)]


def is_empty(slot: np.ndarray, threshold: float) -> bool:
    # An empty slot's middle is flat; check each colour channel so a coloured icon of
    # similar brightness still counts as an item.
    area = _middle(slot).reshape(-1, 3).astype(np.float32)
    return float(area.std(axis=0).max()) < threshold


def icon_area(slot: np.ndarray) -> np.ndarray:
    """The icon without the stack-count digits at the bottom."""
    h, w = slot.shape[:2]
    bottom = max(2, h - BAND_ROWS)  # stop above the number and its outline
    return slot[1:bottom, max(1, int(w * 0.1)):max(int(w * 0.9), 2)]


def icon_signature(slot: np.ndarray) -> Icon:
    area = icon_area(slot)
    gray = cv2.cvtColor(area, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(gray, (9, 8), interpolation=cv2.INTER_AREA).astype(np.int16)
    bits = (small[:, 1:] > small[:, :-1]).flatten()
    h = 0
    for b in bits:
        h = (h << 1) | int(b)
    pixels = area.reshape(-1, 3).astype(np.int16)
    background = pixels[0]  # the slot background shows in the icon area's corner
    fg = pixels[np.abs(pixels - background).max(axis=1) > 25]
    color = tuple(int(v) for v in (fg if len(fg) else pixels).mean(axis=0))
    thumb = cv2.resize(area, (THUMB, THUMB), interpolation=cv2.INTER_AREA).tobytes()
    return Icon(h, color, thumb)


def read_grid(image: np.ndarray, cols: int, rows: int, digits: DigitReader,
              empty_threshold: float = 12.0) -> list[Slot]:
    slots = []
    for i, (x0, y0, x1, y1) in enumerate(slot_rects(image, cols, rows)):
        crop = np.ascontiguousarray(image[y0:y1, x0:x1])
        if crop.size == 0 or is_empty(crop, empty_threshold):
            slots.append(Slot(i, True, None, None, crop))
            continue
        slots.append(Slot(i, False, icon_signature(crop), digits.read(crop), crop))
    return slots


class Catalog:
    """Known items, matched by icon fingerprint."""

    # Same item re-read: ~0.5. Different items of the same shape (e.g. ores): 8+.
    def __init__(self, max_distance: float = 4.0):
        self.max_distance = max_distance
        self.items: dict[int, Icon] = {}

    def add(self, item_id: int, icon: Icon) -> None:
        self.items[item_id] = icon

    def remove(self, item_id: int) -> None:
        self.items.pop(item_id, None)

    def match(self, icon: Icon) -> int | None:
        best, best_score = None, None
        for item_id, known in self.items.items():
            d = icon.distance(known)
            if d <= self.max_distance and (best_score is None or d < best_score):
                best, best_score = item_id, d
        return best
