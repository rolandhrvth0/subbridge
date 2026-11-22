"""Box-less subtitles (white text straight on a busy picture) – generated images only."""
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from subbridge.engine import read_blocks
from subbridge.ocr.preprocess import PrepOptions
from subbridge.ocr.tesseract import TesseractEngine
from subbridge.pipeline.dedup import similarity

FONT = str(Path(__file__).resolve().parents[1] / "subbridge" / "assets" / "fonts" / "InterVariable.ttf")
ocr = TesseractEngine()


def scene(rows, objective=None, seed=0, dark_patch=False):
    rng = np.random.default_rng(seed)
    w, h = 1920, 290
    base = (rng.random((h // 40, w // 40, 3)) * 120 + 15).astype(np.uint8)   # muted, blurry scenery
    img = Image.fromarray(base).resize((w, h), Image.BICUBIC).filter(ImageFilter.GaussianBlur(3))
    d = ImageDraw.Draw(img)
    for _ in range(6):                                   # bright lamps / windows
        x, y = int(rng.choice([rng.integers(0, 300), rng.integers(1500, w - 200)])), int(rng.integers(0, h - 80))
        d.rectangle([x, y, x + int(rng.integers(40, 200)), y + int(rng.integers(20, 80))], fill=(240, 240, 235))
    if dark_patch:                                       # a dark area that looks like a subtitle box
        d.rectangle([500, 120, 1500, 260], fill=(12, 10, 14))
    f = ImageFont.truetype(FONT, 30)
    y = 120
    for t in rows:
        tw = d.textlength(t, font=f)
        x = (w - tw) / 2
        for dx, dy in ((2, 2), (1, 2), (2, 1)):
            d.text((x + dx, y + dy), t, font=f, fill=(20, 20, 20))
        d.text((x, y), t, font=f, fill=(250, 250, 250))
        y += 38
    if objective:
        tw = d.textlength(objective, font=f)
        d.text(((w - tw) / 2, y + 30), objective, font=f, fill=(250, 250, 250), stroke_width=1, stroke_fill=(30, 30, 30))
    return np.asarray(img)


def test_two_line_subtitle_and_objective():
    rows = ["I don't wanna listen to another dumb word", "come outta your mouth."]
    blocks, _, _ = read_blocks(scene(rows, "Go to the stairwell"), ocr, PrepOptions(), 60, True)
    texts = [b.text for b in blocks]
    assert similarity(texts[0], " ".join(rows)) > 0.9, texts
    assert any(similarity(t, "Go to the stairwell") > 0.85 for t in texts[1:]), texts


def test_dark_patch_is_not_a_box():
    blocks, _, _ = read_blocks(scene(["Everybody on the ground, now!"], dark_patch=True, seed=2),
                               ocr, PrepOptions(), 60, True)
    assert blocks and similarity(blocks[0].text, "Everybody on the ground, now!") > 0.9, blocks
