"""build/tm/huk/NNN.idx ("row<TAB>hu", rows of batchk/NNN.tsv) -> build/tm/huk/NNN.tsv ("key<TAB>hu")."""
import sys
from pathlib import Path

TM = Path(__file__).resolve().parents[1] / "build" / "tm"
for name in sys.argv[1:]:
    keys = [ln.split("\t", 1)[0] for ln in open(TM / "batchk" / f"{name}.tsv", encoding="utf-8") if "\t" in ln]
    out = []
    for ln in open(TM / "huk" / f"{name}.idx", encoding="utf-8"):
        if "\t" in ln:
            i, hu = ln.rstrip("\n").split("\t", 1)
            out.append(f"{keys[int(i)]}\t{hu}\n")
    (TM / "huk" / f"{name}.tsv").write_text("".join(out), encoding="utf-8")
    print(name, len(out))
