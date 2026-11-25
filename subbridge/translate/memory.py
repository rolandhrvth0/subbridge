"""Dialogue translation memory: pre-translated (one by one) lines of the game's own subtitle lines, used before
any translation engine (instant, offline, consistent names and tone).

Keys are short hashes of an OCR-tolerant "fold" of the English line, so the pack does not contain the
game's script and the typical OCR confusions (o/e/a/c, l/i/1, rn/m, missing spaces) still hit:
"Yeah, could help take our mind eff things." and "...mind off things." share one key.

Pack file: <data>/packs/lines-<lang>.json (from the project feed, see remote.py) or the bundled
assets/packs/lines-<lang>.json – {"version": n, "lines": {"<key>": "<translation>"}}. The newer one wins.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading

from ..paths import data_dir, resource_dir

_FOLD = [("rn", "m"), ("vv", "w"), ("cl", "d")]
_CHARS = str.maketrans({"a": "o", "e": "o", "c": "o", "0": "o", "l": "i", "1": "i", "j": "i", "!": "i", "|": "i",
                        "5": "s", "$": "s", "8": "b", "u": "v"})


# speaker labels the game shows in front of a line ("Lucia: …"); OCR often loses the colon ("Lucia Yeah, I…",
# "Lucia. Thanks…", "Jasor you…") – such a label must not change the key
_SPEAKERS = {"jason", "lucia", "raul", "nate", "andrea", "karim", "moses", "stranger", "vinny", "kevin", "monty",
             "giorgio", "cop", "monterossa", "receptionist", "waitress", "raina", "cal", "brian", "boobie", "dre",
             "juice", "cisco", "billy", "randy", "tyrone", "abe", "gigi", "valentina", "andres", "andrés", "petra",
             "customer", "girl", "woman", "officer", "audio", "kg"}


def _near_name(tok: str) -> bool:
    t = tok.lower()
    if t in _SPEAKERS:
        return True
    if len(t) < 4:
        return False
    for n in _SPEAKERS:
        if len(n) >= 4 and abs(len(n) - len(t)) <= 1:
            diff = sum(a != b for a, b in zip(t, n)) + abs(len(n) - len(t))
            if diff <= (1 if len(n) <= 4 else 2):
                return True
    return False


def strip_speaker(text: str) -> str:
    """'Lucia Yeah, I know.' / 'Lucia. Thanks, Jay.' / 'Jason: Okay.' -> the line without the label.
    'Jason, stay close…' (someone is addressed) and 'Lucia Call Ended' (phone UI) are left alone."""
    t = (text or "").strip()
    m = re.match(r"^([A-Za-zÀ-ÿ][\w'’\-]{1,13})\s*([.:;'’\"«»,]*)\s+(.+)$", t)
    if not m:
        return t
    name, sep, rest = m.groups()
    if not _near_name(name.split()[0].strip("'’")) or re.match(r"(?i)(call ended|incoming call|group call)", rest):
        return t
    if "," in sep:
        return t                                   # vocative / interjection: "Jason, stay close…", "Man, I…"
    if not (rest[:1].isupper() or rest[:1] in "\"'“„" or rest[:1].isdigit()):
        return t
    return rest


def fold(text: str) -> str:
    t = strip_speaker(text or "").lower().replace("’", "'")
    t = re.sub(r"^[^:]{1,24}:\s+", "", t) if re.match(r"^[A-Za-z .'-]{1,24}:\s", text or "") else t
    for a, b in _FOLD:
        t = t.replace(a, b)
    t = t.translate(_CHARS)
    return re.sub(r"[^a-z0-9]", "", t)


def tm_key(text: str) -> str:
    f = fold(text)
    if len(f) < 8:                        # "Yeah." / "Go!" – engines get those right, and short keys collide
        return ""
    return hashlib.blake2b(f.encode(), digest_size=6).hexdigest()


class Memory:
    def __init__(self):
        self._lock = threading.Lock()
        self._packs: dict[str, dict[str, str]] = {}
        self._mtime: dict[str, tuple] = {}

    def _load(self, lang: str) -> dict[str, str]:
        files = [resource_dir() / "assets" / "packs" / f"lines-{lang}.json", data_dir() / "packs" / f"lines-{lang}.json"]
        stamp = tuple((f.stat().st_mtime if f.exists() else 0) for f in files)
        with self._lock:
            if self._mtime.get(lang) == stamp:
                return self._packs[lang]
            best, ver = {}, -1
            for f in files:
                try:
                    d = json.loads(f.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if int(d.get("version", 0)) > ver:
                    best, ver = d.get("lines") or {}, int(d.get("version", 0))
            self._packs[lang], self._mtime[lang] = best, stamp
            return best

    def get(self, text: str, tgt: str) -> str | None:
        k = tm_key(text)
        return self._load(tgt).get(k) if k else None

    def count(self, tgt: str = "hu") -> int:
        return len(self._load(tgt))


_inst: Memory | None = None


def memory() -> Memory:
    global _inst
    if _inst is None:
        _inst = Memory()
    return _inst
