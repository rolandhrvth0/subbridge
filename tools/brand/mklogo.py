import math
CX, CY, R = 256, 262, 150
CUT = 300
GAPS = [(214, 222), (240, 252), (268, 284)]
def band(y1, y2, n=48):
    pts = []
    for i in range(n + 1):
        y = y1 + (y2 - y1) * i / n
        dx = math.sqrt(max(0, R * R - (y - CY) ** 2))
        pts.append((CX + dx, y))
    for i in range(n, -1, -1):
        y = y1 + (y2 - y1) * i / n
        dx = math.sqrt(max(0, R * R - (y - CY) ** 2))
        pts.append((CX - dx, y))
    return "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + "Z"
edges = [CY - R] + [v for g in GAPS for v in g] + [CUT]
bands = [(edges[i], edges[i + 1]) for i in range(0, len(edges), 2)]
paths = "".join(f'<path d="{band(a, b)}" fill="url(#sun)"/>' for a, b in bands)
def svg(bg=True, size=512):
    bgs = '<rect width="512" height="512" rx="112" fill="url(#bg)"/>' if bg else ''
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="{size}" height="{size}">
<defs><linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#22123a"/><stop offset="1" stop-color="#0f0a1a"/></linearGradient>
<linearGradient id="sun" gradientUnits="userSpaceOnUse" x1="0" y1="{CY-R}" x2="0" y2="{CUT}"><stop offset="0" stop-color="#ffd36e"/><stop offset=".55" stop-color="#ff7a59"/><stop offset="1" stop-color="#ff2f87"/></linearGradient></defs>
{bgs}{paths}
<rect x="104" y="326" width="304" height="40" rx="20" fill="#ffffff"/>
<rect x="160" y="384" width="192" height="40" rx="20" fill="#ff6fa5" fill-opacity=".85"/>
</svg>'''
open("logo.svg", "w").write(svg())
open("logo-mark.svg", "w").write(svg(bg=False))

# Android adaptive foreground (108dp, content in the 66dp safe zone)
S, OX, OY = 0.19, 54 - 256 * 0.19, 54 - 268 * 0.19
cols = ["#FFFFC46A", "#FFFF8A5C", "#FFFF5A70", "#FFFF2F87"]
def apath(d):
    out = []
    for tok in d.replace("M", " M").replace("L", " L").replace("Z", " Z").split():
        if tok in ("Z",):
            out.append("z"); continue
        c, xy = tok[0], tok[1:]
        x, y = map(float, xy.split(","))
        out.append(f"{c}{OX + x * S:.2f},{OY + y * S:.2f}")
    return " ".join(out)
def rr(x, y, w, h, r):
    x, y, w, h, r = OX + x * S, OY + y * S, w * S, h * S, r * S
    return f"M{x + r:.2f},{y:.2f} h{w - 2 * r:.2f} a{r:.2f},{r:.2f} 0 0,1 0,{2 * r:.2f} h{-(w - 2 * r):.2f} a{r:.2f},{r:.2f} 0 0,1 0,{-2 * r:.2f}z"
fg = ['<?xml version="1.0" encoding="utf-8"?>',
      '<vector xmlns:android="http://schemas.android.com/apk/res/android"',
      '    android:width="108dp" android:height="108dp" android:viewportWidth="108" android:viewportHeight="108">']
for (a, b), col in zip(bands, cols):
    fg.append(f'    <path android:fillColor="{col}" android:pathData="{apath(band(a, b, 16))}" />')
fg.append(f'    <path android:fillColor="#FFFFFFFF" android:pathData="{rr(104, 326, 304, 40, 20)}" />')
fg.append(f'    <path android:fillColor="#D9FF6FA5" android:pathData="{rr(160, 384, 192, 40, 20)}" />')
fg.append('</vector>')
open("ic_launcher_fg.xml", "w").write("\n".join(fg) + "\n")
open("ic_launcher_bg.xml", "w").write('''<?xml version="1.0" encoding="utf-8"?>
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="108dp" android:height="108dp" android:viewportWidth="108" android:viewportHeight="108">
    <path android:fillColor="#FF1A0F2C" android:pathData="M0,0h108v108h-108z" />
</vector>
''')
