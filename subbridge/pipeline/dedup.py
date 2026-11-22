"""Text similarity helpers used by the line tracker (punctuation/case-insensitive)."""
from __future__ import annotations

import difflib

from .textclean import normalise_for_compare


def similarity(a: str, b: str) -> float:
    a, b = normalise_for_compare(a), normalise_for_compare(b)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def is_extension(old: str, new: str) -> bool:
    """True when ``new`` continues ``old`` (typewriter / fade-in reveal)."""
    o, n = normalise_for_compare(old), normalise_for_compare(new)
    if not o or len(n) <= len(o):
        return False
    if len(o) < 12:                       # short lines must match exactly ("Heya." is not "Hey, do you...")
        return n.startswith(o)
    return n.startswith(o[: int(len(o) * 0.9)])
