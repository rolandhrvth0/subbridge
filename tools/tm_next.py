"""Translation-memory work queue (LOCAL ONLY).

  python tools/tm_next.py next  [--size 300]   -> build/tm/batchk/NNN.tsv  ("key<TAB>english"), the most
                                                   valuable untranslated lines first
  python tools/tm_next.py pack                  -> subbridge/assets/packs/lines-hu.json (+ stats)

Translations live in build/tm/hu/*.tsv (old: "<keep index><TAB>hu") and build/tm/huk/*.tsv ("key<TAB>hu").
Priority: lines seen in several recordings, then how often they were read.
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from tm_build import build  # noqa: E402

from subbridge.pipeline.textclean import word_ratio  # noqa: E402
from subbridge.translate.memory import tm_key  # noqa: E402

TM = ROOT / "build" / "tm"
SOURCES = ["build/corpus/v1/lines.jsonl", "build/corpus/v2/lines.jsonl", "build/tm/v3_lines.jsonl"]


def translated() -> dict[str, str]:
    keep = json.loads((TM / "keep.json").read_text())
    out = {}
    for f in sorted(glob.glob(str(TM / "hu" / "*.tsv"))):
        for ln in open(f, encoding="utf-8"):
            if "\t" in ln:
                i, hu = ln.rstrip("\n").split("\t", 1)
                if hu.strip():
                    k = tm_key(keep[int(i)]["en"])
                    if k:
                        out[k] = hu.strip()
    for f in sorted(glob.glob(str(TM / "huk" / "*.tsv"))):
        for ln in open(f, encoding="utf-8"):
            if "\t" in ln:
                k, hu = ln.rstrip("\n").split("\t", 1)
                if hu.strip() and hu.strip() != "-":
                    out[k] = hu.strip()
    return out


def skipped() -> set[str]:
    out = set()
    for f in glob.glob(str(TM / "huk" / "*.tsv")) + glob.glob(str(TM / "batchk" / "*.tsv")):
        pass
    # a key given out in a batch but missing from its answer file was judged junk
    for f in glob.glob(str(TM / "batchk" / "*.tsv")):
        ans = TM / "huk" / Path(f).name
        if ans.exists():
            got = {ln.split("\t", 1)[0] for ln in open(ans, encoding="utf-8") if "\t" in ln}
            out |= {ln.split("\t", 1)[0] for ln in open(f, encoding="utf-8") if "\t" in ln} - got
    for f in glob.glob(str(TM / "batch" / "*.tsv")):          # old index batches: unanswered ids
        keep = json.loads((TM / "keep.json").read_text())
        ans = TM / "hu" / Path(f).name
        if ans.exists():
            got = {ln.split("\t", 1)[0] for ln in open(ans, encoding="utf-8") if "\t" in ln}
            out |= {tm_key(keep[int(i)]["en"]) for i in (ln.split("\t", 1)[0] for ln in open(f, encoding="utf-8") if "\t" in ln)
                    if i not in got}
    return out


def candidates() -> list[dict]:
    merged: dict[str, dict] = {}
    for src in SOURCES:
        p = ROOT / src
        if not p.exists():
            continue
        for e in build([str(p)]):
            m = merged.setdefault(e["key"], {"key": e["key"], "en": e["en"], "n": 0, "src": set()})
            m["n"] += e["n"]
            m["src"].add(src)
            if word_ratio(e["en"]) > word_ratio(m["en"]):
                m["en"] = e["en"]
    out = []
    for m in merged.values():
        t = m["en"]
        if re.search(r"[@#¢€~£{}\[\]<>\\_=+%^]|[a-z][A-Z]{2}|\s[b-zB-HJ-Z]\s*$|^[a-z]{1,2}\s", t) or word_ratio(t) < 0.9:
            continue
        if re.match(r"^(Change Destination|Set a destination|Group call|Call Ended)", t):
            continue
        out.append(m)
    out.sort(key=lambda m: (-len(m["src"]), -m["n"]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["next", "pack", "stats"])
    ap.add_argument("--size", type=int, default=300)
    ap.add_argument("--min-n", type=int, default=2, help="skip lines read fewer times (flashes, OCR variants)")
    a = ap.parse_args()
    done = translated()
    if a.cmd == "next":
        skip = skipped()
        todo = [m for m in candidates() if m["key"] not in done and m["key"] not in skip
                and (m["n"] >= a.min_n or len(m["src"]) > 1)][: a.size]
        (TM / "batchk").mkdir(exist_ok=True)
        n = len(glob.glob(str(TM / "batchk" / "*.tsv")))
        out = TM / "batchk" / f"{n:03d}.tsv"
        with open(out, "w", encoding="utf-8") as f:
            for m in todo:
                f.write(f"{m['key']}\t{m['en']}\n")
        print(out, len(todo), "lines; first n/src:", todo[0]["n"] if todo else 0, len(todo[0]["src"]) if todo else 0,
              "last:", todo[-1]["n"] if todo else 0, len(todo[-1]["src"]) if todo else 0)
    elif a.cmd == "stats":
        c = candidates()
        multi = [m for m in c if len(m["src"]) > 1]
        print("candidates", len(c), "multi-source", len(multi), "translated", sum(m["key"] in done for m in c),
              "multi translated", sum(m["key"] in done for m in multi))
    else:
        pack = {"version": int(json.loads((ROOT / "subbridge/assets/packs/lines-hu.json").read_text()).get("version", 0)) + 1
                if (ROOT / "subbridge/assets/packs/lines-hu.json").exists() else 1,
                "lang": "hu",
                "about": "Előre lefordított GTA VI párbeszédsorok (SubBridge fordítási memória). Kulcs: az angol sor OCR-tűrő hash-e, "
                         "a játék szövegét nem tartalmazza.",
                "lines": dict(sorted(done.items()))}
        (ROOT / "subbridge/assets/packs/lines-hu.json").write_text(
            json.dumps(pack, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print("pack v%d: %d lines" % (pack["version"], len(done)))


if __name__ == "__main__":
    main()
