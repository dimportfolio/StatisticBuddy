"""Read-only screen capture of a rectangle, the same way screenshot and streaming
tools do. Nothing here touches the game process, its memory or its input."""
from __future__ import annotations

from dataclasses import asdict, dataclass

import mss
import numpy as np


@dataclass(frozen=True)
class Region:
    """A rectangle in physical screen pixels (virtual-desktop coordinates)."""
    left: int
    top: int
    width: int
    height: int

    def as_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict | None) -> Region | None:
        try:
            r = cls(int(d["left"]), int(d["top"]), int(d["width"]), int(d["height"]))
        except (TypeError, KeyError, ValueError):
            return None
        return r if r.width > 0 and r.height > 0 else None


def monitors() -> list[dict]:
    """Physical monitors (mss index 1..n); index 0 of mss is the whole desktop."""
    with mss.mss() as sct:
        return list(sct.monitors[1:])


def grab_monitor(index: int) -> tuple[np.ndarray, dict]:
    """Screenshot of monitor ``index`` (0-based) as BGRA, plus its geometry."""
    with mss.mss() as sct:
        mons = sct.monitors[1:]
        mon = mons[index] if 0 <= index < len(mons) else mons[0]
        return np.array(sct.grab(mon)), dict(mon)


def grab_region(region: Region) -> np.ndarray:
    """Screenshot of ``region`` as a BGR array."""
    with mss.mss() as sct:
        shot = sct.grab(region.as_dict())
        return np.ascontiguousarray(np.array(shot)[:, :, :3])
