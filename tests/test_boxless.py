"""Box-less subtitles (white text straight on a busy picture) – generated images only."""
from pathlib import Path

import pytest

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from subbridge.engine import read_blocks
from subbridge.ocr.preprocess import PrepOptions
from subbridge.ocr.tesseract import TesseractEngine
from subbridge.pipeline.dedup import similarity

FONT = str(Path(__file__).resolve().parents[1] / "subbridge" / "assets" / "fonts" / "InterVariable.ttf")
ocr = TesseractEngine()


def scene(rows, objective=None, seed=0, dark_patch=False, size=30):
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
    f = ImageFont.truetype(FONT, size)
    y = 120
    for t in rows:
        tw = d.textlength(t, font=f)
        x = (w - tw) / 2
        for dx, dy in ((2, 2), (1, 2), (2, 1)):
            d.text((x + dx, y + dy), t, font=f, fill=(20, 20, 20))
        d.text((x, y), t, font=f, fill=(250, 250, 250))
        y += int(size * 1.27)
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


def _driving(shift):
    """Bright streaks rushing past behind a still subtitle (street lights, lane marks)."""
    rng = np.random.default_rng(5)
    w, h = 1920, 290
    img = np.full((h, w, 3), 40, np.uint8)
    for _ in range(140):
        x, y = int(rng.integers(0, w)), int(rng.integers(0, h))
        ln, th = int(rng.integers(8, 30)), int(rng.integers(2, 5))
        x = (x + shift) % (w - 40)
        img[y:y + th, x:x + ln] = 235
    im = Image.fromarray(img)
    d = ImageDraw.Draw(im)
    f = ImageFont.truetype(FONT, 30)
    t = "Keep your eyes on the road, man."
    tw = d.textlength(t, font=f)
    d.text(((w - tw) / 2, 150), t, font=f, fill=(250, 250, 250), stroke_width=2, stroke_fill=(20, 20, 20))
    return np.asarray(im)


def test_moving_background_is_filtered():
    from subbridge.engine import read_lines_ex
    a, b = _driving(0), _driving(37)
    with_prev, *_ = read_lines_ex(b, ocr, PrepOptions(), 60, True, prev=a)
    assert with_prev and similarity(with_prev[0].text, "Keep your eyes on the road, man.") > 0.9, with_prev


@pytest.mark.parametrize("size", [20, 26, 30, 38, 46])      # Small … Large at 1080p
def test_subtitle_sizes(size):
    blocks, _, _ = read_blocks(scene(["You think I'm acting? Come on!"], seed=7, size=size), ocr, PrepOptions(), 60, True)
    assert blocks and similarity(blocks[0].text, "You think I'm acting? Come on!") > 0.9, (size, blocks)
