"""How much of a recording's dialogue the translation memory covers (LOCAL ONLY).

  python tools/tm_eval.py build/tm/v3_lines.jsonl [--only-v12]

Counts distinct subtitles (grouped OCR reads, at least 2 reads) and how many hit the pack.
--only-v12: use only the translations made from the first two recordings (held-out test on v3)."""
import argparse
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
from tm_build import build  # noqa: E402
from subbridge.translate.memory import lookup, tm_key  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("src")
ap.add_argument("--only-v12", action="store_true")
a = ap.parse_args()
if a.only_v12:
    keep = json.loads((ROOT / "build/tm/keep.json").read_text())
    keys = set()
    for f in glob.glob(str(ROOT / "build/tm/hu/*.tsv")):
        for ln in open(f, encoding="utf-8"):
            if "\t" in ln:
                keys.add(tm_key(keep[int(ln.split("\t", 1)[0])]["en"]))
else:
    keys = json.loads((ROOT / "subbridge/assets/packs/lines-hu.json").read_text())["lines"]
subs = [e for e in build([a.src]) if e["n"] >= 2]
table = keys if isinstance(keys, dict) else {k: "x" for k in keys}
ok = [e["key"] in table or lookup(e["en"], table) is not None for e in subs]
hit = sum(ok)
reads = sum(e["n"] for e in subs)
rhit = sum(e["n"] for e, o in zip(subs, ok) if o)
print(f"subtitles {len(subs)}  covered {hit} ({hit / max(1, len(subs)) * 100:.1f}%)  "
      f"weighted by screen time {rhit / max(1, reads) * 100:.1f}%")
