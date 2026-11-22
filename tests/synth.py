"""Generate subtitle-like test images: a game-ish background with a subtitle (with or without box)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT = Path(__file__).resolve().parents[1] / "subbridge" / "assets" / "fonts" / "InterVariable.ttf"


def background(w=1600, h=300, seed=0) -> Image.Image:
    rng = np.random.default_rng(seed)
    base = rng.integers(20, 200, size=(h // 20 + 1, w // 20 + 1, 3)).astype(np.uint8)
    img = Image.fromarray(base).resize((w, h), Image.BICUBIC).filter(ImageFilter.GaussianBlur(6))
    noise = rng.normal(0, 8, size=(h, w, 3))
    return Image.fromarray(np.clip(np.asarray(img) + noise, 0, 255).astype(np.uint8))


def subtitle(lines: list[str], speaker: str | None = None, box=True, size=34, w=1600, h=300, seed=0,
             text_color=(235, 235, 235), name_color=(240, 210, 90), box_color=(32, 31, 43)) -> Image.Image:
    img = background(w, h, seed)
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(str(FONT), size)
    font.set_variation_by_axes([size, 500]) if hasattr(font, "set_variation_by_axes") else None
    rendered = []
    for i, ln in enumerate(lines):
        prefix = f"{speaker}: " if (speaker and i == 0) else ""
        rendered.append((prefix, ln))
    widths = [d.textlength(p + t, font=font) for p, t in rendered]
    lh = int(size * 1.35)
    total_h = lh * len(lines)
    y0 = h - total_h - 40
    if box:
        bw = max(widths) + 40
        d.rectangle([w / 2 - bw / 2, y0 - 12, w / 2 + bw / 2, y0 + total_h + 8], fill=box_color)
    for i, ((p, t), tw) in enumerate(zip(rendered, widths)):
        x = w / 2 - tw / 2
        y = y0 + i * lh
        if not box:   # outlined text
            for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2), (-2, -2), (2, 2), (-2, 2), (2, -2)):
                d.text((x + dx, y + dy), p + t, font=font, fill=(0, 0, 0))
        if p:
            d.text((x, y), p, font=font, fill=name_color)
            x += d.textlength(p, font=font)
        d.text((x, y), t, font=font, fill=text_color)
    return img
