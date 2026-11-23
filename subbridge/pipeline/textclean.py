"""OCR text clean-up for game subtitles (game-agnostic).

Turns the raw OCR text of one subtitle box into clean dialogue lines:
  "i Theo: Jeez sorry, bro. a Local: Get out!"  ->  [Line("Theo", "Jeez sorry, bro."), Line("Local", "Get out!")]
and rejects HUD / menu / noise text ("PICK UP", "84 BOBCAT XL", "wee vs").
"""
from __future__ import annotations

import gzip
import re
from dataclasses import dataclass
from functools import lru_cache

from ..paths import resource_dir

_WORD_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ']+")
# a speaker label: 1-3 capitalised words (or ALL CAPS), optional number, then a colon
_NAME = r"[A-Z][A-Za-z.'\-]{1,20}(?: [A-Z0-9][A-Za-z.'\-]{0,20}){0,2}"
# where a label may start: line start or after whitespace, possibly glued to 1-3 junk chars ("i Theo:", "BTourist:")
_SPEAKER_SPLIT = re.compile(
    rf"(?:^|(?<=\s))(?:[^\sA-Za-z]{{0,3}}|[a-zA-Z]{{1,2}}\.?\s|[^\s]{{1,2}}(?=[A-Z][a-z]))?({_NAME})\s?[:：]\s+"
    r"|(?<=[.!?…] )([a-z]{3,15}):\s+")          # "...move it! stranger: Hello?" (lower-cased by OCR)
_HONORIFICS = {"mr", "mrs", "ms", "dr", "st", "mx", "sgt", "lt", "officer", "agent", "uncle", "aunt"}
_NOTE = re.compile(r"^\(?\s*(?:In|in) ([A-Z][a-z]+)\s*\)?\s*:\s*")      # "In Spanish: ..."


@dataclass
class Line:
    speaker: str | None
    text: str
    note: str | None = None        # e.g. "Spanish" for "In Spanish: ..."


@lru_cache(maxsize=1)
def english_words() -> frozenset[str]:
    try:
        with gzip.open(resource_dir() / "assets" / "wordlist" / "en.txt.gz", "rt", encoding="utf-8") as f:
            return frozenset(w.strip() for w in f if w.strip())
    except OSError:
        return frozenset()


def is_word(w: str, lang: str = "en") -> bool:
    w = w.lower().strip(".,!?;:\"'()-…_*")
    if not w:
        return False
    if lang != "en":
        return len(w) >= 2
    words = english_words()
    if not words:
        return True
    if w in words or w == "i":
        return True
    for suf in ("'s", "n't", "'re", "'ll", "'ve", "'d", "'m", "s", "in'", "'"):
        if w.endswith(suf) and w[: -len(suf)] in words:
            return True
    if "-" in w:
        return all(is_word(p, lang) for p in w.split("-") if p)
    return False


def clean(text: str) -> str:
    """Normalise whitespace and fix the most common OCR glitches."""
    if not text:
        return ""
    t = text.replace("\r", "\n")
    t = t.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    t = re.sub(r"-\n(?=[a-z])", "", t)                            # hyphenated line break
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"(?:^|\s)_{1,}(?=\s|$)", " ", t)                   # "___" placeholders / underline noise
    t = re.sub(r"^[\s|\[\]!l]+(?=[A-Z])", "", t)                   # box edge read as "|" at start
    t = re.sub(r"[\s|\[\]]+$", "", t)                             # ... and at the end
    t = re.sub(r"(?:(?<=\s)|^)[|\[\]](?=\s+[a-z'])", "I", t)       # "| know" / "[ don't" -> "I"
    t = re.sub(r"(?<=[.!?,…])\s*[|\]\[]\s*(?=\S|$)", " ", t)        # "too.|"
    t = re.sub(r"(?<![A-Za-z])\|(?![A-Za-z])", "I", t)
    t = re.sub(r"^[^\w\"'(¿¡\[]+", "", t)                         # leading junk
    t = re.sub(r"\s+[^\w\s\"'.!?…)\]]{1,3}$", "", t)              # trailing junk symbols
    t = re.sub(r"\s+[^\w\s]{1,2}(?=\s)", "", t)                   # lone symbols mid-line
    t = re.sub(r"\s{2,}", " ", t)
    return t.strip()


_NAV = re.compile(r"^(?:U-?Turn|Turn|Keep|Bear|Take|Merge|Exit|Continue|Head)\b.{0,30}?\b(?:Left|Right|Straight|ft|m|mi|km|yd)\b",
                  re.IGNORECASE)


def is_navigation(text: str) -> bool:
    """GPS directions under the minimap/at the bottom ("Turn Left 108 ft"): the distance changes every
    frame – never a subtitle."""
    return bool(_NAV.match(text.strip()))


_SHORT_OK = {"I", "A", "Ok", "No", "So", "Oh", "Hi", "Yo", "Mr", "Dr", "Ms", "Uh", "Um", "Ah", "Go", "Me", "We",
             "He", "My", "Be", "Do", "If", "It", "Is", "In", "On", "At", "Up", "Us", "An", "As", "By", "Or", "To"}


def strip_ocr_junk(text: str, lang: str = "en") -> str:
    """Specks read as letters in front of a sentence ("a Fy Yeah, that's…", "aa 2 Yeah", "x «gf »Yeah",
    "breakdown. ee This Giorgio…"): at a sentence start, up to 4 short tokens that are not a
    capitalised word, followed by a capitalised word, are dropped."""
    toks = text.split(" ")
    out: list[str] = []
    i = 0
    while i < len(toks):
        start = not out or re.search(r"[.!?…]$", out[-1])
        if start:
            j = i
            while j < len(toks) and j - i < 4:
                bare = re.sub(r"[^A-Za-z0-9']", "", toks[j])
                short_cap = bare[:1].isupper() and len(bare) <= 2 and bare not in _SHORT_OK and \
                    not is_word(bare.lower(), lang)                     # "Fy", "Ee"
                if len(bare) > 3 or re.fullmatch(r"\d{2,}", bare) or \
                        (bare[:1].isupper() and not short_cap and (len(bare) > 1 or bare in ("I", "A"))):
                    break
                j += 1
            if i < j < len(toks) and toks[j][:1].isupper() is False:
                m = re.search(r"[A-Z]", toks[j])         # "»Yeah," – junk glued to the word
                if m and len(re.sub(r"[^A-Za-z]", "", toks[j][:m.start()])) <= 3:
                    toks[j] = toks[j][m.start():]
            if i < j < len(toks) and toks[j][:1].isupper() and len(re.sub(r"[^A-Za-z]", "", toks[j])) >= 2 \
                    and len(toks) - j >= 2:
                i = j                                    # skip the junk run
        out.append(toks[i])
        i += 1
    return " ".join(out)


def strip_trailing_junk(text: str, lang: str = "en") -> str:
    """'Move it! 4' / 'Let's go! gags' / 'be a pussy! Wi' -> drop the junk after the last sentence end."""
    m = re.search(r"^(.*[.!?…\"])\s+(\S.{0,12})$", text)
    if m:
        tail = m.group(2)
        toks = _WORD_RE.findall(tail)
        if not toks or not any(is_word(w, lang) and len(w) >= 3 for w in toks) or len(tail) <= 2:
            return m.group(1)
    return text


def has_real_text(text: str, min_letters: int = 2) -> bool:
    letters = sum(ch.isalpha() for ch in text)
    return letters >= min_letters and any(len(w) >= 2 for w in _WORD_RE.findall(text))


def word_ratio(text: str, lang: str = "en") -> float:
    toks = [w for w in _WORD_RE.findall(text) if len(w.strip("'")) >= 1]
    if not toks:
        return 0.0
    return sum(1 for w in toks if is_word(w, lang)) / len(toks)


def is_dialogue(line: Line, lang: str = "en") -> bool:
    """Reject HUD/menu/noise. Dialogue has real words and normal casing."""
    body = line.text
    if not has_real_text(body) or is_navigation(body):
        return False
    toks = _WORD_RE.findall(body)
    lower = sum(ch.islower() for ch in body)
    upper = sum(ch.isupper() for ch in body)
    ratio = word_ratio(body, lang)
    ends = bool(re.search(r"[!?.…\"']$", body))
    if line.speaker is None:
        if lower < 1 or upper > lower + 1:        # "PICK UP", "DECLASSE 84 BOBCAT XL", "ACCESS KEY"
            return False
        if len(toks) <= 2:                         # short label without punctuation: "Lento", "wee vs"
            return ends and ratio >= 0.99
        if not ends:
            return ratio >= 0.99 and lower >= 6
        return ratio >= 0.8
    if len(toks) <= 2:
        return ratio >= 0.5
    return ratio >= 0.6


def _clean_speaker(name: str) -> str | None:
    name = name.strip(" .-'")
    words = name.split()
    # junk glued in front of the real name: "Bi. Stranger" -> "Stranger"
    while len(words) > 1 and len(words[0].rstrip(".")) <= 2 and words[0].rstrip(".").lower() not in _HONORIFICS:
        words = words[1:]
    name = " ".join(words)
    if not name or not any(c.isalpha() for c in name):
        return None
    if name.isupper() and len(name) > 3:
        name = name.title()                        # "LENA" -> "Lena"
    return name


def split_lines(text: str, enabled: bool = True, lang: str = "en") -> list[Line]:
    """Split OCR text of a box into speaker lines (a merged box can contain several)."""
    text = clean(text)
    # a name cut off at the start ("er: Hello?", "ranger: Hey") – speaker unknown, keep the words
    text = re.sub(r"^[a-z]{1,10}\s?:\s+", "", text)
    if not text:
        return []
    if not enabled:
        return [Line(None, strip_trailing_junk(text, lang))]
    parts: list[Line] = []
    matches = list(_SPEAKER_SPLIT.finditer(text))
    # ignore "label:" matches whose name isn't plausible (e.g. "Time is 10:30")
    matches = [m for m in matches if not re.match(r"^(?:Time|Note|Warning|Tip)$", m.group(1) or "")]
    if not matches:
        parts.append(Line(None, text))
    else:
        head = text[: matches[0].start()].strip()
        if head and word_ratio(head, lang) >= 0.75 and len(head) > 3 and not re.fullmatch(r"[a-z]{1,8}", head.rstrip(":")):
            parts.append(Line(None, head))
        for i, m in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            name = m.group(1) or m.group(2).capitalize()
            body = text[m.end():end].strip()
            lang_note = re.fullmatch(r"In ([A-Z][a-z]+)", name)
            if lang_note:                        # "rist: In Spanish: ..." -> note, speaker unknown
                if parts and parts[-1].text == "" :
                    parts[-1].note = lang_note.group(1)
                    parts[-1].text = body
                    continue
                parts.append(Line(None, f"In {lang_note.group(1)}: {body}"))
                continue
            parts.append(Line(_clean_speaker(name), body))
    out = []
    for ln in parts:
        body = ln.text
        note = ln.note
        nm = _NOTE.match(body)
        if nm:
            note, body = nm.group(1), body[nm.end():]
        body = strip_trailing_junk(strip_ocr_junk(clean(body), lang), lang)
        if body:
            out.append(Line(ln.speaker, body, note))
    return out


def split_speaker(text: str, enabled: bool = True) -> tuple[str | None, str]:
    """Backwards-compatible helper: 'LENA: Let's go.' -> ('Lena', "Let's go.")."""
    lines = split_lines(text, enabled)
    if len(lines) == 1:
        return lines[0].speaker, lines[0].text
    return None, clean(text)


def normalise_for_compare(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())
