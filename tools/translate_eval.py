"""Translate a corpus the way the app does (slang prep -> offline model -> post fixes) for review.
LOCAL ONLY (game text). Usage:
  python tools/translate_eval.py build/corpus/v1/lines.jsonl out.tsv [--limit N] [--min-words 3]
Writes: en <TAB> prepped-en <TAB> hu   (unique, stable lines only)"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from subbridge.pipeline.textclean import normalise_for_compare  # noqa: E402
from subbridge.translate.argos import ArgosTranslator  # noqa: E402
from subbridge.translate.textprep import textprep  # noqa: E402


def stable_lines(rows: list[dict]) -> list[str]:
    """OCR rows contain fade-in fragments ("rry, dude."): keep a line only when no longer line seen
    within a few seconds contains it, and drop near-duplicates."""
    out, seen = [], set()
    for i, r in enumerate(rows):
        t = r["text"].strip()
        n = normalise_for_compare(t)
        if not n or n in seen:
            continue
        frag = False
        for q in rows[max(0, i - 6): i + 7]:
            if q is r:
                continue
            m = normalise_for_compare(q["text"])
            if len(m) > len(n) and n in m and abs(q["t"] - r["t"]) < 6:
                frag = True
                break
        if not frag:
            seen.add(n)
            out.append(t)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("lines")
    ap.add_argument("out")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--min-words", type=int, default=2)
    a = ap.parse_args()
    rows = [json.loads(x) for x in Path(a.lines).read_text(encoding="utf-8").splitlines() if x.strip()]
    lines = [t for t in stable_lines(rows) if len(re.findall(r"[A-Za-z']+", t)) >= a.min_words]
    if a.limit:
        lines = lines[: a.limit]
    tp = textprep()
    tr = ArgosTranslator(threads=8)
    t0 = time.time()
    with open(a.out, "w", encoding="utf-8") as f:
        for i in range(0, len(lines), 32):
            chunk = lines[i:i + 32]
            prepped = [tp.prep(t, "en") for t in chunk]
            hu = [tp.post_fix(h, "hu") for h in tr.translate(prepped, "en", "hu")]
            for en, pe, h in zip(chunk, prepped, hu):
                f.write(f"{en}\t{pe if pe != en else ''}\t{h}\n")
    print(f"{len(lines)} lines in {time.time() - t0:.0f} s -> {a.out}")


if __name__ == "__main__":
    main()
