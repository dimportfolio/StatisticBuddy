"""One screenshot of the game window per read, cropped into each tracker's region."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from statisticbuddy.capture.screen import Region, grab_region
from statisticbuddy.capture.window import GameWindow, find_game_window


@dataclass(frozen=True)
class RelRegion:
    """A rectangle inside the game window, in game pixels from its top-left corner."""
    x: int
    y: int
    width: int
    height: int
    frame_width: int   # game window size when the region was selected
    frame_height: int

    def as_dict(self) -> dict:
        return dict(x=self.x, y=self.y, width=self.width, height=self.height,
                    frame_width=self.frame_width, frame_height=self.frame_height)

    @classmethod
    def from_dict(cls, d: dict | None) -> RelRegion | None:
        try:
            r = cls(*(int(d[k]) for k in ("x", "y", "width", "height", "frame_width", "frame_height")))
        except (TypeError, KeyError, ValueError):
            return None
        return r if r.width > 0 and r.height > 0 else None


@dataclass
class Frame:
    window: GameWindow
    image: np.ndarray  # BGR, the whole game client area

    @property
    def size(self) -> tuple[int, int]:
        return self.image.shape[1], self.image.shape[0]

    def crop(self, r: RelRegion) -> np.ndarray | None:
        w, h = self.size
        if r.x < 0 or r.y < 0 or r.x + r.width > w or r.y + r.height > h:
            return None
        return np.ascontiguousarray(self.image[r.y:r.y + r.height, r.x:r.x + r.width])


class GameNotFound(Exception):
    pass


def grab_game_frame(title: str) -> Frame:
    win = find_game_window(title)
    if win is None:
        raise GameNotFound("MapleStory window not found. Is the game open and not minimized?")
    c = win.client
    return Frame(win, grab_region(Region(c.left, c.top, c.width, c.height)))
