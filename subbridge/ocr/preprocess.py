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
        # no box: bright text that has a dark outline/shadow right next to it
        bright = mx >= 205
        edge = _dilate(lum < 60, 2)
        m = bright & edge
        # grow back into the full glyph (thick strokes are further from the outline)
        for _ in range(4):
            m = _dilate(m, 1) & bright
        # drop isolated speckles (bright noise next to dark scenery): keep pixels with >=3 neighbours
        n = np.zeros(m.shape, np.int8)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy or dx:
                    n += np.roll(np.roll(m, dy, 0), dx, 1)
        return m & (n >= 3)
    return mx >= thr


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


def binarize(rgb: np.ndarray, opts: PrepOptions, background: float | None = None) -> Image.Image:
    """Black text on white, scaled for Tesseract, with a white border."""
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
