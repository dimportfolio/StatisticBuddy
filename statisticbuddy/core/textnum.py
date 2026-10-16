"""Helpers for pulling numbers out of noisy OCR text."""
from __future__ import annotations

import re

# Letters OCR commonly returns in place of digits.
_DIGIT_FIXES = str.maketrans({
    "O": "0", "o": "0", "D": "0", "Q": "0",
    "l": "1", "I": "1", "i": "1", "|": "1", "!": "1",
    "S": "5", "s": "5", "B": "8", "Z": "2", "z": "2", "g": "9", "q": "9",
})
_TOKEN = re.compile(r"[^\s\[\]()]+")
# Commas/dots/apostrophes join thousands groups; spaces don't, so stray OCR digits stay separate.
_DIGIT_RUN = re.compile(r"\d(?:[\d,.']*\d)?")


def normalize_digits(text: str) -> str:
    """Fix letter/digit confusions, only inside tokens that already contain a digit."""
    return _TOKEN.sub(
        lambda m: m.group(0).translate(_DIGIT_FIXES) if any(c.isdigit() for c in m.group(0)) else m.group(0),
        text,
    )


def digit_runs(text: str) -> list[str]:
    """Digit groups with thousands separators removed: '1,234 x 56' -> ['1234', '56']."""
    runs = [re.sub(r"\D", "", r) for r in _DIGIT_RUN.findall(text)]
    return [r for r in runs if r]
