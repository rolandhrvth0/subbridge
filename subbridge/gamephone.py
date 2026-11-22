"""In-game phone: finds a handheld phone screen in the picture (white rounded screen, possibly tilted),
straightens it, reads chat bubbles / posts / comments / articles and the blue reply buttons.

Ported from the author's earlier subtitle translator. Game-agnostic: it looks for a light, flat,
portrait screen with dark text."""
from __future__ import annotations

import threading
import re
from collections import deque
from PIL import Image, ImageChops, ImageFilter, ImageOps


_ocr_local = threading.local()


def _tsv(img, psm=6) -> str:
    eng = getattr(_ocr_local, "eng", None)
    if eng is None:
        from .ocr.tesseract import TesseractEngine
        eng = _ocr_local.eng = TesseractEngine("en")
    try:
        return eng.tsv(img, psm)
    except Exception:  # noqa: BLE001
        return ""


def _screen_mask(small):
    r, g, b = small.split()
    mn = ImageChops.darker(ImageChops.darker(r, g), b)
    mx = ImageChops.lighter(ImageChops.lighter(r, g), b)
    light = mn.point(lambda p: 255 if p >= 115 else 0)
    flat = ImageChops.subtract(mx, mn).point(lambda p: 255 if p <= 70 else 0)
    m = ImageChops.multiply(light, flat)
    return m


def quick_check(rgb) -> bool:
    """~1–2 ms numpy pre-filter on the raw frame: is there a tall, light, colourless block that does not
    touch the top/bottom edge (a handheld phone screen)? Most frames have none, so the slow search below
    is skipped."""
    import numpy as np
    a = np.asarray(rgb)[::12, ::12]
    if a.ndim != 3 or a.size == 0:
        return False
    mn, mx = a.min(axis=2), a.max(axis=2)
    m = (mn >= 115) & ((mx.astype(np.int16) - mn) <= 70)
    h, w = m.shape
    if m.mean() < 0.012:
        return False
    need, gap = int(h * 0.28), max(2, int(h * 0.1))
    good = 0
    for x in np.nonzero(m.sum(axis=0) >= h * 0.15)[0]:
        d = np.diff(np.concatenate(([0], m[:, x].astype(np.int8), [0])))
        # runs touching the frame edge are sky / walls, never the phone: drop them before bridging gaps
        runs = [(s0, e0) for s0, e0 in zip(np.nonzero(d == 1)[0], np.nonzero(d == -1)[0]) if s0 > 0 and e0 < h]
        merged = []                                   # bridge short gaps (photos inside a post)
        for s0, e0 in runs:
            if merged and s0 - merged[-1][1] <= gap:
                merged[-1][1], merged[-1][2] = e0, merged[-1][2] + (e0 - s0)
            else:
                merged.append([s0, e0, e0 - s0])
        for s0, e0, lit in merged:
            # tall light block, not glued to the frame edge (sky, wall)
            if e0 - s0 >= need and lit / (e0 - s0) >= 0.5 and s0 > 0 and e0 < h:
                good += 1
                break
    return good >= max(2, int(w * 0.04))


def find_phone(img, sc=6):
    """A telefon képernyője: {'rect': (x0,y0,x1,y1), 'angle': fok} az img koordinátáiban, vagy None."""
    W, H = img.width // sc, img.height // sc
    small = img.resize((W, H), Image.BILINEAR)
    mask = _screen_mask(small)
    px = mask.load()
    seen = bytearray(W * H)
    best = None
    for y in range(H):
        for x in range(W):
            if not px[x, y] or seen[y * W + x]:
                continue
            q = deque([(x, y)]); seen[y * W + x] = 1
            pts = []
            while q:
                cx, cy = q.popleft(); pts.append((cx, cy))
                for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    if 0 <= nx < W and 0 <= ny < H and not seen[ny * W + nx] and px[nx, ny]:
                        seen[ny * W + nx] = 1; q.append((nx, ny))
            n = len(pts)
            if n < W * H * 0.012:
                continue
            xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
            x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
            bw, bh = x1 - x0 + 1, y1 - y0 + 1
            if x0 <= 0 or y0 <= 0 or x1 >= W - 1 or y1 >= H - 1:   # fal / ég a kép szélén
                continue
            if not (W * 0.07 <= bw <= W * 0.4 and bh >= H * 0.28 and 1.1 <= bh / bw <= 3.5):
                continue
            if n / (bw * bh) < 0.35:
                continue
            if best is None or n > best[0]:
                best = (n, x0, y0, x1, y1, pts)
    if not best:
        return None
    n, x0, y0, x1, y1, pts = best
    # dőlésszög a bal és jobb élből (soronként a legszélső pixel)
    left, right = {}, {}
    for x, y in pts:
        if y not in left or x < left[y]:
            left[y] = x
        if y not in right or x > right[y]:
            right[y] = x
    ys = sorted(left)
    mid = ys[len(ys) // 5: len(ys) * 4 // 5]

    def slope(edge):
        if len(mid) < 4:
            return 0.0
        my = sum(mid) / len(mid); mx_ = sum(edge[y] for y in mid) / len(mid)
        num = sum((y - my) * (edge[y] - mx_) for y in mid)
        den = sum((y - my) ** 2 for y in mid) or 1
        return num / den
    import math
    ang = math.degrees(math.atan((slope(left) + slope(right)) / 2))
    rect = (x0 * sc, y0 * sc, (x1 + 1) * sc, (y1 + 1) * sc)
    # a telefon képernyőjén van sötét szöveg (de nem túl sok)
    g = ImageOps.grayscale(img.crop(rect)).resize((120, 200))
    hist = g.histogram()
    dark = sum(hist[:90]) / (120 * 200)
    light = sum(hist[120:]) / (120 * 200)
    if not (0.01 <= dark <= 0.4 and light >= 0.4):
        return None
    return {"rect": rect, "angle": ang}


def straighten(img, ph):
    """A telefon képernyőjének egyenesre forgatott kivágása."""
    x0, y0, x1, y1 = ph["rect"]
    m = int((x1 - x0) * 0.08)
    crop = img.crop((max(0, x0 - m), max(0, y0 - m), min(img.width, x1 + m), min(img.height, y1 + m)))
    if abs(ph["angle"]) > 0.7:
        # pozitív szög: lefelé jobbra dől az él -> az óramutatóval ellentétesen kell forgatni
        crop = crop.rotate(-ph["angle"], resample=Image.BICUBIC, expand=False, fillcolor=(0, 0, 0))
    # finom szöghangolás: a sorok vízszintes vetülete ott a legélesebb, ahol egyenesek a sorok
    g = ImageOps.grayscale(crop)
    g = g.resize((max(1, g.width // 3), max(1, g.height // 3)))
    # csak a belső rész (a keret és a fejléc ne zavarjon)
    g = g.crop((int(g.width * 0.18), int(g.height * 0.12), int(g.width * 0.85), int(g.height * 0.95)))
    g = ImageOps.autocontrast(g, cutoff=2).point(lambda p: 255 if p < 110 else 0)
    best_a, best_v = 0.0, -1
    for a10 in range(-50, 51, 5):
        a = a10 / 10
        rr = g.rotate(a, resample=Image.BILINEAR)
        w = rr.width
        rr = rr.crop((int(w * 0.1), 0, int(w * 0.9), rr.height)); w = rr.width
        rows = [sum(rr.crop((0, y, w, y + 1)).getdata()) for y in range(rr.height)]
        mean = sum(rows) / len(rows)
        v = sum((x - mean) ** 2 for x in rows)
        if v > best_v:
            best_a, best_v = a, v
    if best_a:
        crop = crop.rotate(best_a, resample=Image.BICUBIC, fillcolor=(0, 0, 0))
    # vágás a fehér képernyőre
    sm = _screen_mask(crop.resize((max(1, crop.width // 8), max(1, crop.height // 8))))
    bb = sm.getbbox()
    if bb:
        crop = crop.crop((bb[0] * 8, bb[1] * 8, min(crop.width, bb[2] * 8), min(crop.height, bb[3] * 8)))
    return crop


def remove_images(crop):
    """Képek, logók, színes foltok és a sötét keret kifehérítése: a tesseractot ezek zavarják.
    A vékony betűk megmaradnak (a vastag sötét/színes területek nem)."""
    rgb = crop.convert("RGB")
    W, H = rgb.size
    sc = 2
    sm = rgb.resize((max(1, W // sc), max(1, H // sc)), Image.BILINEAR)
    r, g, b = sm.split()
    mn = ImageChops.darker(ImageChops.darker(r, g), b)
    mx = ImageChops.lighter(ImageChops.lighter(r, g), b)
    # a képernyő fényessége helyenként nagyon eltér (árnyék): helyi háttérhez viszonyítunk
    bg = mn.filter(ImageFilter.MaxFilter(15)).filter(ImageFilter.BoxBlur(10))
    dark = ImageChops.subtract(bg, mn).point(lambda p: 255 if p > 55 else 0)
    color = ImageChops.subtract(mx, mn).point(lambda p: 255 if p > 70 else 0)
    blob = ImageChops.lighter(dark, color)
    # vastag területek: erózió után is megmaradnak (a betűvonal vékony)
    thick = blob.filter(ImageFilter.MinFilter(7)).filter(ImageFilter.MaxFilter(17))
    # képek: a fényes, de nem "papír" színű, mintás területek is (fotók világos részei)

    thick = thick.resize((W, H), Image.NEAREST)
    # a kitöltés a képernyő saját háttérszíne (különben a tesseract "negatív" képnek hiszi)
    hist = ImageOps.grayscale(sm).histogram()
    tot = sum(hist); acc = 0; med = 200
    for i in range(255, -1, -1):
        acc += hist[i]
        if acc >= tot * 0.35:
            med = i
            break
    fill = Image.new("RGB", (W, H), (med, med, med))
    return Image.composite(fill, rgb, thick)


def read_phone(crop, min_conf=50):
    """A (kiegyenesített) telefonképernyő sorai: [(top, bottom, szöveg, conf), ...] fentről lefelé."""
    crop = remove_images(crop)
    g = ImageOps.grayscale(crop)
    s = max(1.0, min(3.0, 1700 / max(1, g.height)))   # ~1700 px magasra nagyítjuk
    g = g.resize((int(g.width * s), int(g.height * s)), Image.BICUBIC)
    g = ImageOps.autocontrast(g, cutoff=1)
    g = ImageOps.expand(g, 30, fill=255)
    words = []
    for row in _tsv(g, 4).splitlines()[1:]:
        c = row.split("\t")
        if len(c) < 12 or not c[11].strip():
            continue
        try:
            conf = float(c[10])
        except ValueError:
            continue
        words.append({"t": c[11].strip(), "conf": conf, "top": (int(c[7]) - 30) / s,
                      "h": int(c[9]) / s, "l": (int(c[6]) - 30) / s, "r": (int(c[6]) + int(c[8]) - 30) / s})
    # sorok: balról jobbra fűzzük a szavakat a szomszédjukhoz (ferde/perspektivikus sorokat is egyben tart)
    words.sort(key=lambda w: w["l"])
    rows = []
    for w in words:
        cy = w["top"] + w["h"] / 2
        best, bd = None, None
        for r in rows:
            last = r["w"][-1]
            lcy = last["top"] + last["h"] / 2
            dx = w["l"] - last["r"]
            dy = abs(cy - lcy)
            if -5 <= dx <= max(60, 3 * last["h"]) and dy < 0.6 * max(last["h"], w["h"]):
                if bd is None or dy < bd:
                    best, bd = r, dy
        if best is None:
            rows.append({"w": [w]})
        else:
            best["w"].append(w)
    rows.sort(key=lambda r: r["w"][0]["top"])
    out = []
    for r in rows:
        ws = r["w"]
        out.append({"top": min(w["top"] for w in ws), "bot": max(w["top"] + w["h"] for w in ws),
                    "l": ws[0]["l"], "r": max(w["r"] for w in ws), "words": ws})
    return out


SHORT = set("i a ok no so to me we he it is in on at of my up be do go hi oh u ur an or if as by us am "
             "ya yo k n w 2 4 hm ha ah uh um ye im el la de y en mi tu te se".split())

TEXTING = {
    "u": "you", "ur": "your", "vry": "very", "thnx": "thanks", "thx": "thanks", "pls": "please",
    "plz": "please", "r": "are", "yr": "your", "b4": "before", "bc": "because", "cuz": "because",
    "im": "I'm", "dont": "don't", "cant": "can't", "wont": "won't", "idk": "I don't know",
    "omg": "oh my god", "tho": "though", "rn": "right now", "ppl": "people",
    "msg": "message", "txt": "text", "ya": "you", "k": "okay", "n": "and", "w": "with",
    "lmk": "let me know", "cmon": "come on", "dnt": "don't", "btw": "by the way", "rly": "really",
    "smth": "something", "sry": "sorry", "nvm": "never mind", "ty": "thank you", "wyd": "what are you doing",
    "hbu": "how about you", "ily": "I love you", "bday": "birthday", "tmrw": "tomorrow", "2nite": "tonight",
    "gtg": "got to go", "brb": "be right back", "np": "no problem", "fr": "for real", "ngl": "not gonna lie",
    "whats": "what's", "thats": "that's", "its": "it's",
}


def normalize_texting(text):
    out = []
    for tok in text.split():
        tok = tok.replace("a-hole", "asshole")
        m = re.match(r"^([\"'(“]*)([A-Za-z0-9']+)([.,!?;:)\"”…]*)$", tok)
        if m and m.group(2).lower() in TEXTING:
            out.append(m.group(1) + TEXTING[m.group(2).lower()] + m.group(3))
        else:
            out.append(tok)
    return " ".join(out)


def _word_ok(w, is_word):
    t = w["t"].replace("|", "I")
    core = t.strip(".,!?;:\"'()…“”‘’-<>")
    if not core or not any(ch.isalnum() for ch in core):
        return False
    if core.startswith("@"):
        return True
    if len(core) == 1 and core.lower() not in ("i", "a", "u", "k", "n", "w", "y", "2", "4") \
            and not core.isdigit():
        return False
    if w["conf"] >= 60:
        return True
    if w["conf"] >= 45 and (is_word(core) or core.lower() in TEXTING):
        return True
    return False


def _join_split_words(words, is_word):
    """A tesseract néha kettévág egy szót ('plan e?!', 'carp et', 'n o'): a szomszédos darabokat
    összevonjuk, ha együtt értelmes szót adnak. Előbb azokat, ahol egyik darab sem szó."""
    def core(t):
        return re.sub(r"^[\"'“(]+|[.,!?;:\"'”)…]+$", "", t)

    def strict(t):
        c = core(t).lower()
        return bool(c) and (len(c) > 1 or c in "ai") and is_word(c) and c not in ("et", "er", "ar", "e")

    def loose(t):
        c = core(t).lower()
        return strict(t) or c in SHORT

    for rule in (lambda a, b: not strict(a) and not strict(b),
                 lambda a, b: not loose(a) or not loose(b)):
        out = []
        i = 0
        while i < len(words):
            if i + 1 < len(words):
                a, b = words[i], words[i + 1]
                ca, cb = core(a["t"]), core(b["t"])
                if ca.isalpha() and cb.isalpha() and is_word((ca + cb).lower()) and rule(a["t"], b["t"]) \
                        and min(len(ca), len(cb)) <= 3:
                    m = dict(a)
                    m["t"] = a["t"] + b["t"].lstrip("\"'“(") if not b["t"].startswith(("\"", "'")) else a["t"] + b["t"]
                    m["t"] = a["t"].rstrip() + b["t"]
                    m["conf"] = max(a["conf"], b["conf"])
                    m["r"] = b["r"]
                    out.append(m)
                    i += 2
                    continue
            out.append(words[i])
            i += 1
        words = out
    return words


def bubbles(crop, lines, is_word):
    """Sorokból blokkok (chat-buborék / komment / bekezdés): [{'y0','y1','en','name','mine'}].
    A legfelső sor a fejléc (név / 'Comments' / 'Back')."""
    x0, y0, x1, y1 = 0, 0, crop.width, crop.height
    img = crop
    header = ""
    header_bottom = 0
    res = []
    cur = None
    for i, ln in enumerate(lines):
        ws = _join_split_words([dict(w, t=w["t"].replace("|", "I")) for w in ln["words"]], is_word)
        toks = [w["t"] for w in ws if _word_ok(w, is_word)]
        toks = [t for t in toks if t.strip(".,!?;:\"'()…“”‘’-<>")]
        if not toks:
            continue
        t, b, lx, rx = ln["top"], ln["bot"], ln["l"], ln["r"]
        if not res and cur is None and t < (y1 - y0) * 0.09 and len(toks) <= 3:
            h = " ".join(x for x in toks if x not in ("<", ">"))
            header = "" if h.lower() in ("back", "< back") else h.lstrip("< ").strip()
            header_bottom = b
            continue
        text = " ".join(toks)
        if text.lower() in ("back", "< back"):
            continue
        is_name = text.startswith("@") and len(toks) <= 2
        gap_lim = max(14, (b - t) * 0.95)
        if cur and not is_name and (t - cur["y1"] < gap_lim):
            cur["en"] += " " + text
            cur["y1"] = b
            cur["lx"] = min(cur["lx"], lx)
            cur["rx"] = max(cur["rx"], rx)
        else:
            cur = {"y0": t, "y1": b, "en": "" if is_name else text, "lx": lx, "rx": rx,
                   "name": toks[0] if is_name else ""}
            res.append(cur)
    for bub in res:
        bub["en"] = bub["en"].strip()
    # a képernyő tetején félig kilógó (levágott) buborék maradéka: kisbetűvel kezdődő töredék
    if res and header and res[0]["y0"] - header_bottom < (y1 - y0) * 0.06:
        first = res[0]["en"]
        m = re.match(r"^([a-z0-9][^.!?]{0,14}?)\s+(?=[A-Z])", first)
        if m and len(m.group(1).split()) <= 3:
            res[0]["en"] = first[m.end():]
    # Theo (saját) üzenetei: kékebb buborék és/vagy jobbra igazítva
    W = x1 - x0

    def blueness(yy0, yy1, xx0, xx1):
        c = img.crop((max(0, int(xx0)), max(0, int(yy0)), min(img.width, int(xx1)), min(img.height, int(yy1))))
        c = c.resize((max(1, c.width // 4), max(1, c.height // 4)))
        pix = [p for p in c.getdata() if sum(p) / 3 > 100]
        if not pix:
            return 0.0
        return sum(p[2] - p[0] for p in pix) / len(pix)
    base = blueness(img.height * 0.1, img.height * 0.95, 0, img.width)
    for bub in res:
        bl = blueness(bub["y0"] - 6, bub["y1"] + 6, bub["lx"] - 10, bub["rx"] + 10)
        right_aligned = bub["rx"] > W * 0.82 and bub["lx"] > W * 0.3
        bub["mine"] = (bl - base) > 9 or (right_aligned and bub["lx"] > W * 0.45)
        bub["en"] = re.sub(r"\s+", " ", bub["en"]).strip()
        bub["en"] = re.sub(r"(\w)- (\w)", r"\1-\2", bub["en"])           # sorvégi elválasztás
        bub["en"] = re.sub(r"\s+\d$", "", bub["en"])                       # emoji-maradék a végén
    def good(b):
        toks = re.findall(r"[^\W\d_][\w'’-]*", b["en"])
        long_ = [t for t in toks if len(t) >= 3]
        alpha = sum(ch.isalpha() for ch in b["en"]) / max(1, len(b["en"].replace(" ", "")))
        return (len(long_) >= 2 or (b.get("name") and len(long_) >= 1)) and alpha >= 0.6
    res = [b for b in res if good(b)]
    return header, res


def find_replies(crop):
    """A válaszlehetőség-gombok (kék, lekerekített gombok fehér felirattal) a képernyőn.
    Vissza: [(l, t, r, b, szöveg), ...] fentről lefelé, balról jobbra."""
    rgb = crop.convert("RGB")
    W, H = rgb.size
    sc = 2
    sm = rgb.resize((max(1, W // sc), max(1, H // sc)), Image.BILINEAR)
    w, h = sm.size
    px = sm.load()
    blue = [[False] * w for _ in range(h)]
    for y in range(h):
        row = blue[y]
        for x in range(w):
            r, g, b = px[x, y]
            row[x] = b > 130 and b - r > 75 and b - g > 50
    # vízszintes kék futamok soronként -> sávok
    runs_by_row = []
    for y in range(h):
        runs, x = [], 0
        row = blue[y]
        while x < w:
            if row[x]:
                s = x
                gap = max(3, int(w * 0.06))      # a fehér betűk megszakítják a kéket
                while x < w and (row[x] or any(row[x + 1:x + gap])):
                    x += 1
                if x - s >= w * 0.12:
                    runs.append((s, x))
            x += 1
        runs_by_row.append(runs)
    # összefüggő téglalapok: egymás alatti, átfedő futamok
    boxes = []
    for y, runs in enumerate(runs_by_row):
        for s, e in runs:
            for bx in boxes:
                if bx[3] >= y - 2 and min(e, bx[2]) - max(s, bx[0]) > 0.5 * min(e - s, bx[2] - bx[0]):
                    bx[0], bx[2], bx[3] = min(bx[0], s), max(bx[2], e), y
                    break
            else:
                boxes.append([s, y, e, y])
    out = []
    for l, t, r, b in boxes:
        bw, bh = r - l, b - t + 1
        if bh < h * 0.025 or bh > h * 0.12 or bw < 2.0 * bh:
            continue
        L, T, R, B = l * sc, t * sc, r * sc, (b + 1) * sc
        pad = int(bh * sc * 0.12)
        g = rgb.crop((L + pad, T + pad, R - pad, B - pad))
        # fehér betű a kéken -> fekete betű fehéren; több küszöbbel, a legbiztosabb olvasat nyer
        rr, gg, bb = g.split()
        mnc = ImageChops.darker(ImageChops.darker(rr, gg), bb)
        best_txt, best_c = "", -1
        for th in (150, 175, 200):
            gi = mnc.point(lambda p, th=th: 0 if p > th else 255)
            s = max(1.0, 64 * max(1, round(gi.height / 46)) / max(1, gi.height))   # soronként ~64 px
            gi = gi.resize((int(gi.width * s), int(gi.height * s)), Image.BICUBIC)
            gi = ImageOps.expand(gi, 20, fill=255)
            ws, cs = [], []
            for row in _tsv(gi, 7 if (B - T) < H * 0.065 else 6).splitlines()[1:]:
                c = row.split("\t")
                if len(c) < 12 or not c[11].strip():
                    continue
                try:
                    cf = float(c[10])
                except ValueError:
                    continue
                if cf < 40:
                    continue
                ws.append(c[11].strip()); cs.append(cf)
            t = re.sub(r"\s+", " ", " ".join(ws)).strip(" |_-—")
            sc_ = (sum(cs) / len(cs)) if cs else 0
            if sum(ch.isalpha() for ch in t) >= 2 and sc_ > best_c:
                best_txt, best_c = t, sc_
        txt = best_txt
        if sum(ch.isalpha() for ch in txt) >= 2:
            out.append((L, T, R, B, txt))
    out.sort(key=lambda o: (o[1] // 20, o[0]))
    return out


# common one-word reply buttons: machine translation gets these wrong out of context
REPLY_FIX = {
    "hu": {"check in": "Érdeklődj, mi újság", "reply": "Válasz", "send": "Küldés", "ignore": "Figyelmen kívül hagy",
           "call": "Hívás", "accept": "Elfogad", "decline": "Elutasít", "yes": "Igen", "no": "Nem", "ok": "Oké",
           "flirt": "Flörtölj", "apologize": "Kérj bocsánatot", "joke": "Viccelődj"},
}


def screen_signature(crop) -> bytes:
    return ImageOps.grayscale(crop).resize((20, 36), Image.BILINEAR).tobytes()


def sig_diff(a, b) -> float:
    if a is None or b is None or len(a) != len(b):
        return 255.0
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)


def read_screen(img, is_word):
    """Full read of a frame: None if no phone, else dict(rect, angle, header, bubbles, replies)."""
    ph = find_phone(img)
    if not ph:
        return None
    crop = straighten(img, ph)
    lines = read_phone(crop)
    header, bubs = bubbles(crop, lines, is_word)
    replies = [r[4] for r in find_replies(crop)]
    return {"rect": ph["rect"], "angle": ph["angle"], "header": header, "bubbles": bubs, "replies": replies,
            "crop": crop}
