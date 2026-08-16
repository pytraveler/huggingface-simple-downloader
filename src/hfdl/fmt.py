"""Turning numbers into the short strings a progress row has room for.

Kept apart from i18n because these are the two places where a language shows up
without a sentence around it: a unit suffix and a duration. Everything else that
is worded lives in i18n.py.
"""

from __future__ import annotations


def human_size(size: float | None) -> str:
    """Bytes as a person reads them. `None` becomes a dash, not "0 B"."""
    if size is None:
        return "-"
    for unit, scale in (("GB", 1024**3), ("MB", 1024**2), ("KB", 1024)):
        if size >= scale:
            return f"{size / scale:.2f} {unit}"
    return f"{int(size)} B"


def human_speed(bytes_per_second: float | None) -> str:
    """A rate. Below a kilobyte a second it is not worth the two decimals."""
    if not bytes_per_second or bytes_per_second <= 0:
        return "-"
    for unit, scale in (("GB/s", 1024**3), ("MB/s", 1024**2), ("KB/s", 1024)):
        if bytes_per_second >= scale:
            return f"{bytes_per_second / scale:.1f} {unit}"
    return f"{int(bytes_per_second)} B/s"


def human_eta(seconds: float | None, lang: str) -> str:
    """A remaining time, rounded to whatever unit still means something.

    Seconds stop being informative past a minute and minutes past a day, so each
    range prints one unit and at most one below it. An estimate that says
    "1 h 03 m 27 s" is pretending to a precision the measurement does not have.
    """
    ru = lang == "ru"
    if seconds is None or seconds != seconds or seconds < 0:  # NaN included
        return "?"
    seconds = int(seconds)
    s, m, h, d = ("с", "мин", "ч", "дн") if ru else ("s", "m", "h", "d")
    if seconds < 60:
        return f"{seconds} {s}"
    if seconds < 3600:
        return f"{seconds // 60} {m} {seconds % 60:02d} {s}"
    if seconds < 86400:
        return f"{seconds // 3600} {h} {(seconds % 3600) // 60:02d} {m}"
    return f"{seconds // 86400} {d} {(seconds % 86400) // 3600:02d} {h}"


def percent(done: int, total: int | None) -> str:
    """A percentage, or a dash while the total is still unknown."""
    if not total:
        return "-"
    return f"{min(100.0, done * 100.0 / total):.1f}%"


def shorten(text: str, width: int = 60) -> str:
    """Middle-elided path: the file name is the half worth keeping."""
    if len(text) <= width:
        return text
    head = width // 3
    return text[:head] + "..." + text[-(width - head - 3):]
