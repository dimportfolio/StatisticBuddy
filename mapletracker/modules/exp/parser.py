"""Turn raw OCR text from the EXP bar into numbers.

The in-game EXP bar shows something like ``EXP. 12345678901 [45.678%]``.
OCR output is noisy, so we normalise common letter/digit confusions and
pick out the percentage and the EXP value independently.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from mapletracker.core.textnum import digit_runs, normalize_digits

_LABEL = re.compile(r"E\s*X\s*P\s*[.:]?", re.IGNORECASE)
_PCT = re.compile(r"(\d{1,3})\s*[.,]\s*(\d{1,4})\s*%|(\d{1,3})\s*%")
_PCT_NO_SIGN = re.compile(r"[\[(]\s*(\d{1,3})\s*[.,]\s*(\d{1,4})")


@dataclass(frozen=True)
class ExpReading:
    exp: int
    pct: float | None = None


def _find_pct(text: str) -> tuple[float | None, tuple[int, int] | None]:
    m = _PCT.search(text)
    if m:
        if m.group(1) is not None:
            value = float(f"{m.group(1)}.{m.group(2)}")
        else:
            value = float(m.group(3))
        return value, m.span()
    m = _PCT_NO_SIGN.search(text)
    if m:
        return float(f"{m.group(1)}.{m.group(2)}"), m.span()
    return None, None


def parse_exp_text(text: str) -> ExpReading | None:
    """Return the EXP value (and percentage when visible), or None."""
    if not text:
        return None
    cleaned = normalize_digits(_LABEL.sub(" ", text))

    pct, span = _find_pct(cleaned)
    if pct is not None and not (0 <= pct < 100):
        pct, span = None, None

    # Look for the EXP number outside the percentage, preferring the text before it.
    runs = digit_runs(cleaned[: span[0]] if span else cleaned)
    if not runs and span:
        runs = digit_runs(cleaned[span[1]:])
    if not runs:
        return None
    return ExpReading(exp=int(max(runs, key=len)), pct=pct)
