"""Display formatting helpers."""
from __future__ import annotations


def big_number(n: float | None) -> str:
    if n is None:
        return "-"
    for limit, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(n) >= limit:
            return f"{n / limit:,.2f}{suffix}"
    return f"{n:,.0f}"


def signed(n: float | None) -> str:
    """big_number with an explicit + for gains."""
    if n is None:
        return "-"
    return ("+" if n > 0 else "") + big_number(n)


def duration(seconds: float | None) -> str:
    if seconds is None:
        return "-"
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}"


def eta(seconds: float | None) -> str:
    if seconds is None:
        return "-"
    minutes = int(seconds // 60)
    days, rem = divmod(minutes, 1440)
    h, m = divmod(rem, 60)
    if days:
        return f"{days}d {h}h"
    if h:
        return f"{h}h {m:02d}m"
    return f"{m}m"


def percent(p: float | None, digits: int = 3) -> str:
    return "-" if p is None else f"{p:.{digits}f}%"
