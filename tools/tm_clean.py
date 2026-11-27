"""Filter a batch: drop OCR fragments (a piece of a longer known line, cut-off reads, junk tokens). LOCAL tool.
  python tools/tm_clean.py build/tm/batchk/037.tsv --skip 600 > out.tsv"""
import argparse, json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
from subbridge.pipeline.textclean import is_word
from subbridge.translate.memory import fold
import tm_next as t

ap = argparse.ArgumentParser(); ap.add_argument("batch"); ap.add_argument("--skip", type=int, default=0)
a = ap.parse_args()
rows = [l.rstrip("\n").split("\t", 1) for l in open(a.batch, encoding="utf-8")][a.skip:]
longer = [fold(m["en"]) for m in t.candidates()]
big = "\n".join(f for f in longer if len(f) > 20)
NAMES = re.compile(r"^[A-Z][a-z]+$")
for k, en in rows:
    toks = en.split()
    bad = sum(1 for w in toks if not is_word(w) and not NAMES.match(w.strip(".,!?\"'")))
    if bad > (len(toks) >= 10):          # at most one unknown token in a long line, none in a short one
        continue
    if len(toks) < 3 or not re.search(r"[a-z]", en):
        continue
    f = fold(en)
    if big.count(f) > (1 if len(f) > 20 else 0):   # only a piece of a longer line read elsewhere
        continue
    print(f"{k}\t{en}")
