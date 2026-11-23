"""Image preparation for subtitle OCR (game-agnostic).

Most games draw subtitles as light text, either on a dark semi-opaque box or with an outline.
We locate the box when there is one, then binarise to black text on white, which is what
Tesseract reads best."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image


@dataclass
class PrepOptions:
    text_color: str = "light"       # light | dark | white | yellow | any
    threshold: int = 0              # 0 = automatic
    scale: float = 0.0              # 0 = automatic (target ~40 px line height)
    invert: bool = False            # extra manual inversion
    find_box: bool = True           # look for a subtitle box inside the region


def _to_rgb_array(img) -> np.ndarray:
    if isinstance(img, np.ndarray):
        return img[..., :3]
    return np.asarray(img.convert("RGB"))


# ------------------------------------------------------------------ box detection
def _longest_run(flags: np.ndarray, max_gap: int = 4) -> tuple[int, int, int]:
    best = (0, 0, 0)
    start = last = None
    gap = 0
    n = len(flags)
    for x in range(n + 1):
        if x < n and flags[x]:
            if start is None:
                start = x
            last, gap = x, 0
        elif start is not None:
            gap += 1
            if gap > max_gap or x == n:
                if last - start > best[0]:
                    best = (last - start, start, last)
                start = None
    return best


def box_mask(rgb: np.ndarray) -> np.ndarray:
    """Pixels that look like a subtitle box background: dark (but not letterbox-black),
    low saturation and locally flat."""
    a = rgb.astype(np.int16)
    mx, mn = a.max(axis=2), a.min(axis=2)
    dark = (mx >= 10) & (mx <= 80) & ((mx - mn) <= 28)
    g = a.sum(axis=2)
    flat = np.zeros_like(dark)
    dx = np.abs(np.diff(g, axis=1))
    dy = np.abs(np.diff(g, axis=0))
    flat[:-1, :-1] = (dx[:-1, :] <= 12) & (dy[:, :-1] <= 12)
    return dark & flat


def _dilate(mask: np.ndarray, r: int) -> np.ndarray:
    out = mask.copy()
    for d in range(1, r + 1):
        out[:, d:] |= mask[:, :-d]
        out[:, :-d] |= mask[:, d:]
        out[d:, :] |= mask[:-d, :]
        out[:-d, :] |= mask[d:, :]
    return out


def box_color(small: np.ndarray) -> np.ndarray | None:
    """Estimate the subtitle box colour: the most common flat dark colour right next to
    bright text pixels. Dark game scenery rarely touches bright text, the box always does."""
    flat = box_mask(small)
    bright = small.max(axis=2) >= 150
    if bright.sum() < 20:
        return None
    near = _dilate(bright, 2) & flat
    if near.sum() < 30:
        return None
    px = small[near].astype(np.int16)
    # iterate towards the densest colour: start at the median, re-centre on nearby pixels
    c = np.median(px, axis=0)
    for _ in range(3):
        close = (np.abs(px - c) <= 10).all(axis=1)
        if close.sum() < 20:
            return None
        c = px[close].mean(axis=0)
    if close.mean() < 0.3:
        return None                                  # no dominant colour: no box
    return np.round(c).astype(np.int16)


def find_boxes(img, sc: int = 3, min_h: int = 26, max_h: int = 400,
               color: np.ndarray | None = None, tol: int = 10) -> list[tuple[int, int, int, int]]:
    """Return subtitle boxes as (x0, y0, x1, y1), top to bottom. Empty list = no box found."""
    rgb = _to_rgb_array(img)
    H0, W0 = rgb.shape[:2]
    small = rgb[::sc, ::sc]
    if color is None:
        color = box_color(small)
    if color is None:
        return []
    m = (np.abs(small.astype(np.int16) - color.astype(np.int16)) <= tol).all(axis=2)
    H, W = m.shape
    if H < 4 or W < 10:
        return []
    min_w = max(4, 80 // sc)
    rowc = m.sum(axis=1)
    segs = []
    y = 0
    while y < H:
        if rowc[y] < min_w:
            y += 1
            continue
        y0 = y
        while y < H and rowc[y] >= min_w * 0.5:
            y += 1
        segs.append((y0, y))

    boxes = []
    guard = 0
    while segs and guard < 20:
        guard += 1
        y0, y1 = segs.pop(0)
        if (y1 - y0) * sc < min_h:
            continue
        order = sorted(range(y0, y1), key=lambda yy: -rowc[yy])
        top = [yy for yy in order[:6] if rowc[yy] >= rowc[order[0]] * 0.7]
        colok = m[top].sum(axis=0) >= len(top) * 0.5
        ln, x0, x1 = _longest_run(colok)
        if ln * sc < 100:
            continue

        def rowcov(yy):
            return m[yy, x0:x1 + 1].mean()
        ref = top[0]
        by0 = ref
        while by0 > y0 and rowcov(by0 - 1) >= 0.1:
            by0 -= 1
        by1 = ref + 1
        while by1 < y1 and rowcov(by1) >= 0.1:
            by1 += 1
        while by0 < by1 and rowcov(by0) < 0.6:
            by0 += 1
        while by1 > by0 and rowcov(by1 - 1) < 0.6:
            by1 -= 1
        if by0 - y0 >= min_h // sc:
            segs.append((y0, by0))
        if y1 - by1 >= min_h // sc:
            segs.append((by1, y1))
        bh = (by1 - by0) * sc
        if not min_h <= bh <= max_h:
            continue
        # inset a little: the box edge is often lighter and OCR reads it as '|'
        box = (max(0, x0 * sc + 4), by0 * sc, min((x1 + 1) * sc - 4, W0), min(by1 * sc, H0))
        if _has_text(rgb[box[1]:box[3], box[0]:box[2]]):
            boxes.append(box)
    boxes.sort(key=lambda b: b[1])
    return boxes


def _has_text(crop: np.ndarray) -> bool:
    if crop.size == 0:
        return False
    g = crop[::4, ::4].mean(axis=2)
    ratio = (g >= 150).mean()
    return 0.01 <= ratio <= 0.5


# ------------------------------------------------------------------ binarisation
def text_mask(rgb: np.ndarray, opts: PrepOptions, background: float | None = None) -> np.ndarray:
    """Boolean mask of text pixels."""
    a = rgb.astype(np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    lum = (0.299 * r + 0.587 * g + 0.114 * b)
    mx = a.max(axis=2)
    color = opts.text_color
    if color == "dark":
        thr = opts.threshold or _otsu(lum)
        return lum < thr
    if color == "white":
        thr = opts.threshold or 185
        return (lum >= thr) & ((mx - a.min(axis=2)) < 60)
    if color == "yellow":
        thr = opts.threshold or 150
        return (r >= thr) & (g >= thr * 0.85) & (b < g - 40)
    if color == "any":
        thr = opts.threshold or _otsu(lum)
        return lum >= thr if lum.mean() < thr else lum < thr
    # "light": any bright/coloured text (white text + coloured speaker names)
    if opts.threshold:
        thr = opts.threshold
    elif background is not None:
        thr = min(200, background + 65)     # relative to the box colour
    else:
        return glyph_mask(rgb)
    return mx >= thr


def motion_level(rgb: np.ndarray, prev: np.ndarray | None) -> float:
    """How much the picture behind the subtitles moves (mean grey change, 0–255; ~1–3 static, 10+ driving)."""
    if prev is None or prev.shape != rgb.shape:
        return 0.0
    a = rgb[::4, ::4].astype(np.int16).mean(axis=2)
    b = prev[::4, ::4].astype(np.int16).mean(axis=2)
    return float(np.abs(a - b).mean())


def glyph_mask(rgb: np.ndarray, prev: np.ndarray | None = None) -> np.ndarray:
    """Box-less subtitles: white glyphs straight on the game picture. Hysteresis (sure-white seeds grow
    into the anti-aliased stroke edges, so thin letters like i/l/n survive), then connected components
    that are glyph-sized are kept (walls, sky, lamps and HUD icons are not), then only rows where many
    glyphs sit side by side (a text line)."""
    try:
        import cv2
    except Exception:  # noqa: BLE001
        cv2 = None
    a = rgb
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    mn = np.minimum(np.minimum(r, g), b)
    sat = np.maximum(np.maximum(r, g), b) - mn
    mx = mn + sat
    still = None
    if prev is not None and prev.shape == a.shape and motion_level(a, prev) > 6:
        # moving picture (driving, fast camera, drunk wobble): subtitles stand still while everything
        # behind them moves – keep only bright pixels that were bright at the same place a moment ago
        p = prev
        pmx = np.maximum(np.maximum(p[..., 0], p[..., 1]), p[..., 2]).astype(np.int16)
        still = np.abs(mx.astype(np.int16) - pmx) < 40
    white_s, white_w = (mn >= 205) & (sat < 45), (mn >= 150) & (sat < 60)
    # coloured speaker names ("Stranger:" in yellow/blue/…): bright AND clearly coloured
    col_s, col_w = (mx >= 200) & (sat >= 90), (mx >= 150) & (sat >= 70)
    strong, weak = white_s | col_s, white_w | col_w
    if still is not None:
        strong, weak = strong & still, weak & still
    if cv2 is None:                                   # numpy fallback: grow the seeds a few pixels
        m = strong
        for _ in range(3):
            m = _dilate(m, 1) & weak
        return m
    def keep(m_weak, m_strong):
        n, lab, st, _ = cv2.connectedComponentsWithStats(m_weak.astype(np.uint8), connectivity=8)
        ok = np.zeros(n, bool)
        ok[np.unique(lab[m_strong])] = True
        ok[0] = False
        w_, h_, area = st[:, 2], st[:, 3], st[:, 4]
        big = (h_ > max(48, a.shape[1] * 0.03)) | (w_ > max(70, a.shape[1] * 0.04)) | \
              ((w_ * h_ > 400) & (area > 0.85 * w_ * h_))
        tiny = h_ < 2
        return ok & ~big & ~tiny, ok & big, lab

    ok, _big, lab = keep(weak, strong)
    k = ok[lab]
    rows = k.sum(axis=1) > max(8, 0.002 * k.shape[1])
    near = rows | np.roll(rows, 3) | np.roll(rows, -3)
    return k & near[:, None]


def fits_text(rgb: np.ndarray, box) -> bool:
    """A real subtitle box holds its text centred with even margins; a dark patch of the scene that
    happens to contain (part of) a box-less subtitle does not."""
    x0, y0, x1, y1 = box
    c = rgb[y0:y1, x0:x1]
    if c.size == 0:
        return False
    mx = c.max(axis=2)
    bright = mx > min(175, float(np.median(mx)) + 70)        # grey 2nd-speaker lines count too
    cols = np.where(bright.sum(axis=0) >= 2)[0]
    rows = np.where(bright.sum(axis=1) >= 2)[0]
    if len(cols) < 4 or len(rows) < 4:
        return True                      # nothing readable yet (box just appeared): judged later by OCR
    w, h = x1 - x0, y1 - y0
    left, right = cols[0], w - 1 - cols[-1]
    top, bottom = rows[0], h - 1 - rows[-1]
    # real subtitle boxes hug their text: on recordings it fills >= 53 % of the height and >= 88 % of the
    # width; a dark patch of the scene around a box-less line is much larger than the text
    return abs(left - right) <= max(24, 0.12 * w) and abs(top - bottom) <= max(10, 0.4 * h) \
        and (cols[-1] - cols[0]) >= 0.75 * w and (rows[-1] - rows[0]) >= 0.4 * h


def boxless_blocks(rgb: np.ndarray, mask: np.ndarray | None = None, prev: np.ndarray | None = None
                   ) -> list[tuple[int, int, int, int]]:
    """Text blocks (x0, y0, x1, y1) of box-less subtitles, top to bottom: rows of glyphs are grouped
    into blocks (a two-line subtitle stays one block, an objective line below is its own), and in
    every block only the cluster nearest to the centre is kept (subtitles are centred; logos and HUD
    sit at the sides)."""
    k = glyph_mask(rgb, prev) if mask is None else mask
    h, w = k.shape
    prof = k.sum(axis=1)
    # specks (minimap dots, glints) make weak rows that would bridge a subtitle and the objective line
    on = prof > max(8, 0.08 * float(prof.max() if prof.size else 0))
    runs, start = [], None
    for y, v in enumerate(list(on) + [False]):
        if v and start is None:
            start = y
        elif not v and start is not None:
            if runs and start - runs[-1][1] <= 4:      # i-dots / accents above the line
                runs[-1] = (runs[-1][0], y)
            else:
                runs.append((start, y))
            start = None
    runs = [r for r in runs if r[1] - r[0] >= 6]
    if not runs:
        return []
    lh = float(np.median([b - a for a, b in runs]))
    groups = [[runs[0]]]
    for r in runs[1:]:
        if r[0] - groups[-1][-1][1] <= lh * 1.35:      # tight gap: next line of the same subtitle
            groups[-1].append(r)
        else:
            groups.append([r])
    out = []
    for gr in groups:
        y0, y1 = gr[0][0], gr[-1][1]
        if y1 - y0 > lh * 5:                           # 4+ lines tall: scenery, not a subtitle
            continue
        xs = np.where(k[y0:y1].any(axis=0))[0]
        if len(xs) < 3:
            continue
        clusters = np.split(xs, np.where(np.diff(xs) > max(60, lh * 2.5))[0] + 1)
        c = w / 2
        best = max(clusters, key=lambda q: len(q) - abs((q[0] + q[-1]) / 2 - c) * 0.05)
        if best[-1] - best[0] < lh * 1.5 or abs((best[0] + best[-1]) / 2 - c) > w * 0.22:
            continue                                   # too short, or off to the side (logo, HUD, minimap)
        pad = int(lh * 0.45) + 4
        out.append((max(0, int(best[0]) - pad), max(0, y0 - pad), min(w, int(best[-1]) + pad), min(h, y1 + pad)))
    return out


def _otsu(gray: np.ndarray) -> float:
    hist, _ = np.histogram(gray, bins=256, range=(0, 256))
    total = gray.size
    sum_all = np.dot(np.arange(256), hist)
    w_b = sum_b = 0.0
    best, thr = -1.0, 128
    for t in range(256):
        w_b += hist[t]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += t * hist[t]
        m_b, m_f = sum_b / w_b, (sum_all - sum_b) / w_f
        v = w_b * w_f * (m_b - m_f) ** 2
        if v > best:
            best, thr = v, t
    return float(thr)


def binarize(rgb: np.ndarray, opts: PrepOptions, background: float | None = None,
             mask: np.ndarray | None = None) -> Image.Image:
    """Black text on white, scaled for Tesseract, with a white border."""
    if mask is None:
        mask = text_mask(rgb, opts, background)
    if opts.invert:
        mask = ~mask
    out = np.where(mask, 0, 255).astype(np.uint8)
    img = Image.fromarray(out, "L")
    s = opts.scale or _auto_scale(mask)
    if abs(s - 1.0) > 0.05:
        img = img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))), Image.LANCZOS)
        img = img.point(lambda p: 0 if p < 128 else 255)
    pad = Image.new("L", (img.width + 24, img.height + 24), 255)
    pad.paste(img, (12, 12))
    return pad


def _auto_scale(mask: np.ndarray) -> float:
    """Estimate text height from row profile and scale to ~36 px x-height-ish lines."""
    rows = mask.any(axis=1)
    if not rows.any():
        return 1.0
    runs, cur = [], 0
    for v in rows:
        if v:
            cur += 1
        elif cur:
            runs.append(cur)
            cur = 0
    if cur:
        runs.append(cur)
    runs = [r for r in runs if r >= 6]
    if not runs:
        return 1.0
    h = float(np.median(runs))
    return float(np.clip(40.0 / h, 0.5, 3.0))


def prepare_boxes(rgb: np.ndarray, boxes, opts: PrepOptions) -> list[Image.Image]:
    out = []
    for (x0, y0, x1, y1) in boxes:
        crop = rgb[y0:y1, x0:x1]
        bm = box_mask(crop[::2, ::2])
        bg = float(crop[::2, ::2][bm].max(axis=1).mean()) if bm.any() else None
        out.append(binarize(crop, opts, bg))
    return out


def prepare(img, opts: PrepOptions) -> list[Image.Image]:
    """Region image -> list of binarised images ready for OCR (one per subtitle box)."""
    rgb = _to_rgb_array(img)
    if opts.find_box and opts.text_color in ("light", "white", "yellow"):
        boxes = find_boxes(rgb)
        if boxes:
            return prepare_boxes(rgb, boxes, opts)
    return [binarize(rgb, opts)]
