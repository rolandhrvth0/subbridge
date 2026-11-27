"""Show where a chunk's .hu drifts from its .tsv: prints windows where a blank HU faces a clean EN or vice versa
around the first drift, using a crude length-ratio check. LOCAL tool.  python tools/tm_align.py 037f_02"""
import sys
from pathlib import Path
w = Path(__file__).resolve().parents[1] / "build/tm/work"
c = sys.argv[1]
en = [l.rstrip("\n").split("\t", 1)[1] for l in open(w / f"{c}.tsv", encoding="utf-8")]
hu = [l.rstrip("\n") for l in open(w / f"{c}.hu", encoding="utf-8")]
print(len(en), "en /", len(hu), "hu")
for i in range(min(len(en), len(hu))):
    a, b = len(en[i]), len(hu[i])
    if b and (b > 2.2 * a + 15 or a > 2.5 * b + 15):
        print("first suspicious row", i + 1)
        for j in range(max(0, i - 4), min(len(en), i + 3)):
            print(j + 1, ":", en[j][:55], "||", (hu[j] if j < len(hu) else "")[:55])
        break
