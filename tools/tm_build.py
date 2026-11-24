"""Build the English side of the dialogue translation memory from corpus line dumps (LOCAL ONLY).

  python tools/tm_build.py build/corpus/v1/lines.jsonl build/corpus/v2/lines.jsonl -o build/tm/en.jsonl

Consecutive OCR reads of the same subtitle ("Yeah, nat Snat it said…", "Yeah, that's what it said…") are
grouped; the cleanest variant (most dictionary words, then most frequent, then longest) is kept. Lines are
deduplicated globally by the translation-memory key (subbridge.translate.memory.tm_key), so every
OCR spelling that folds to the same key maps to one translation.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from subbridge.pipeline.textclean import (Line, clean, fix_ocr_words, is_dialogue, split_lines,  # noqa: E402
                                          strip_ocr_junk, strip_trailing_junk, word_ratio)
from subbridge.translate.memory import strip_speaker, tm_key  # noqa: E402


def _prep(text: str) -> list[str]:
    out = []
    for ln in split_lines(text):
        t = strip_speaker(strip_trailing_junk(strip_ocr_junk(fix_ocr_words(clean(ln.text)))))
        if is_dialogue(Line(ln.speaker, t)) and len(t.split()) >= 3:
            out.append(t)
    return out


def _best(group: list[str]) -> str:
    cnt = Counter(group)
    top = max(word_ratio(t) for t in cnt)
    cands = [t for t in cnt if word_ratio(t) >= top - 0.05]
    return max(cands, key=lambda t: (len(t) >= 0.85 * max(len(c) for c in cands), word_ratio(t), cnt[t], len(t)))


def build(paths: list[str]) -> list[dict]:
    seen: dict[str, dict] = {}
    for p in paths:
        rows = [json.loads(x) for x in open(p, encoding="utf-8")]
        rows.sort(key=lambda r: r["t"])
        groups: list[tuple[float, list[str]]] = []
        for r in rows:
            for t in _prep(r["text"]):
                if groups and r["t"] - groups[-1][0] <= 6 and any(
                        SequenceMatcher(None, t.lower(), g.lower()).ratio() >= 0.6 for g in groups[-1][1][-4:]):
                    groups[-1] = (r["t"], groups[-1][1] + [t])
                else:
                    groups.append((r["t"], [t]))
        for _, g in groups:
            best = _best(g)
            k = tm_key(best)
            if not k:
                continue
            e = seen.get(k)
            if e is None:
                seen[k] = {"key": k, "en": best, "n": len(g), "src": Path(p).parent.name}
            else:
                e["n"] += len(g)
                if word_ratio(best) > word_ratio(e["en"]):
                    e["en"] = best
    return sorted(seen.values(), key=lambda e: -e["n"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()
    rows = build(a.inputs)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(len(rows), "unique lines ->", a.out)


if __name__ == "__main__":
    main()
