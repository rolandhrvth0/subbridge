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
        return lookup(text, self._load(tgt), tgt)

    def count(self, tgt: str = "hu") -> int:
        return len(self._load(tgt))


# ------------------------------------------------------------------ tolerant lookup
# Live reads are often a known line plus something else: two subtitle lines read as one, an objective or the
# phone's caller label glued on ("… Unknown Be 00:08"), a stray glyph at the end. The whole read is tried first,
# then the read without that junk, then sentence by sentence (adjacent sentences joined where the pack has them).

_HUD = re.compile(r"(?i)\s*(\b(unknown|incoming call|call ended|outgoing call)\b.*|\s\d{1,2}[:.]\d{2})\s*$")
_SPLIT = re.compile(r"(?<=[.!?…\"”])\s+(?=[A-Z\"“„'])")
_JUNK_TOKEN = re.compile(r"[^A-Za-z'’.,!?\-\"“”…]")
SHORT = {  # short sentences the pack has no key for (fold shorter than 8 letters), inside a longer read
    "hu": {"yeah": "Igen.", "yes": "Igen.", "yep": "Aha.", "yup": "Aha.", "no": "Nem.", "nah": "Nem.", "nope": "Nem.",
           "okay": "Oké.", "ok": "Oké.", "alright": "Rendben.", "allright": "Rendben.", "hey": "Hé!", "yo": "Hé!",
           "what": "Mi?", "huh": "Mi?", "shit": "Basszus.", "damn": "Basszus.", "fuck": "Bassza meg!",
           "fuckoff": "Kopj le!", "comeon": "Gyerünk!", "letsgo": "Menjünk!", "go": "Menj!", "thanks": "Kösz.",
           "thankyou": "Köszönöm.", "sure": "Persze.", "right": "Jó.", "please": "Kérlek.", "wait": "Várj!",
           "stop": "Állj!", "wow": "Hű.", "whoa": "Hűha.", "sorry": "Bocsi.", "really": "Tényleg?", "why": "Miért?",
           "how": "Hogyan?", "who": "Ki?", "where": "Hol?", "uh": "Ö...", "um": "Ö...", "hmm": "Hm.", "mmhmm": "Aha.",
           "ohshit": "Ó, basszus!", "ohfuck": "Ó, bassza meg!", "ohgod": "Istenem.", "jesus": "Jézusom.",
           "move": "Mozgás!", "run": "Fuss!", "getdown": "Le a földre!", "getin": "Szállj be!", "hello": "Helló.",
           "hi": "Szia.", "bye": "Szia.", "cool": "Király.", "nice": "Szép.", "great": "Remek.", "good": "Jó.",
           "fine": "Jó.", "nothing": "Semmi.", "dude": "Haver.", "man": "Haver.", "bro": "Tesó.", "relax": "Nyugi.",
           "easy": "Nyugi.", "help": "Segítség!", "really?": "Tényleg?", "seriously": "Komolyan?"},
}


def _short_key(t: str) -> str:
    return re.sub(r"[^a-z]", "", (t or "").lower().replace("’", "'").replace("'", ""))


def _is_junk(tok: str) -> bool:
    from ..pipeline.textclean import is_word
    w = tok.strip(".,!?;:\"'“”…-")
    if not w:
        return True
    if _JUNK_TOKEN.search(w) or (any(c.isdigit() for c in w)):
        return True
    if len(w) == 1:
        return w.lower() not in "ai"
    return len(w) <= 3 and not is_word(w) and not w[:1].isupper()


def _trimmed(text: str) -> list[str]:
    """The read itself, then without HUD text glued on, then without up to 3 junk tokens at either end."""
    out = [text]
    t = _HUD.sub("", text).strip()
    if t and t != text:
        out.append(t)
    toks = t.split()
    a, b = 0, len(toks)
    while b - a > 2 and len(toks) - b < 3 and _is_junk(toks[b - 1]):
        b -= 1
    while b - a > 2 and a < 2 and _is_junk(toks[a]):
        a += 1
    if (a, b) != (0, len(toks)):
        out.append(" ".join(toks[a:b]))
    return out


def _whole(text: str, table: dict) -> str | None:
    for t in _trimmed(text):
        k = tm_key(t)
        if k and k in table:
            return table[k]
    return None


def lookup(text: str, table: dict, tgt: str = "hu") -> str | None:
    if not table or not text:
        return None
    hit = _whole(text, table)
    if hit is not None:
        return hit
    parts = [p for p in _SPLIT.split(_HUD.sub("", text).strip()) if p.strip()]
    if len(parts) < 2:
        return None
    short = SHORT.get(tgt, {})
    out, i, found = [], 0, 0
    while i < len(parts):
        for j in range(len(parts), i, -1):                 # longest run of sentences the pack knows
            if j - i == len(parts):
                continue
            h = _whole(" ".join(parts[i:j]), table)
            if h is not None:
                out.append(h)
                found += j - i
                i = j
                break
        else:
            p = parts[i]
            s = short.get(_short_key(p))
            if s is not None:
                out.append(s)
            elif not all(_is_junk(x) for x in p.split()) and len(fold(p)) >= 3:
                return None                                 # a real sentence the pack does not have
            i += 1
    return " ".join(out) if found else None


def sentence_keys(en: str, tr: str) -> dict[str, str]:
    """Extra pack keys: each sentence of a translated multi-sentence line, when both sides split the same way."""
    a, b = _SPLIT.split(en.strip()), _SPLIT.split(tr.strip())
    if len(a) < 2 or len(a) != len(b):
        return {}
    out = {}
    for x, y in zip(a, b):
        k = tm_key(x)
        if k:
            out[k] = y
    return out


_inst: Memory | None = None


def memory() -> Memory:
    global _inst
    if _inst is None:
        _inst = Memory()
    return _inst
