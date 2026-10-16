"""Read the meso total from OCR text of the inventory's meso field, e.g. '12,345,678'."""
from __future__ import annotations

from mapletracker.core.textnum import digit_runs, normalize_digits

MAX_MESOS = 10**13  # anything bigger is a misread


def parse_meso_text(text: str) -> int | None:
    runs = digit_runs(normalize_digits(text or ""))
    if not runs:
        return None
    value = int(max(runs, key=len))
    return value if value < MAX_MESOS else None
