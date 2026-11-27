"""work/<chunk>.num ("row\thu", only translated rows) -> work/<chunk>.hu (one line per batch row). LOCAL tool."""
import sys
from pathlib import Path
w = Path(__file__).resolve().parents[1] / "build/tm/work"
c = sys.argv[1]
n = sum(1 for _ in open(w / f"{c}.tsv", encoding="utf-8"))
out = [""] * n
for ln in open(w / f"{c}.num", encoding="utf-8"):
    if "\t" in ln:
        i, hu = ln.rstrip("\n").split("\t", 1)
        out[int(i) - 1] = hu
(w / f"{c}.hu").write_text("\n".join(out) + "\n", encoding="utf-8")
print(c, n, "rows,", sum(1 for x in out if x), "translated")
