"""Synthetic in-game phone: a tilted light screen with chat text on a dark scene."""
from PIL import Image, ImageDraw, ImageFont

from subbridge.gamephone import read_screen
from subbridge.paths import resource_dir
from subbridge.pipeline.textclean import is_word


def _scene():
    font = ImageFont.truetype(str(resource_dir() / "assets" / "fonts" / "InterVariable.ttf"), 30)
    ph = Image.new("RGB", (520, 1000), (236, 236, 240))
    d = ImageDraw.Draw(ph)
    d.text((200, 30), "Nico", font=font, fill=(20, 20, 20))
    y = 140
    for text, mine in [("You got my plane? You better", False), ("be good to her tonight.", False),
                       ("", False), ("Good luck out there", True), ("", False),
                       ("I will smooth this over.", False), ("Do not worry about it.", False)]:
        if text:
            if mine:
                d.rounded_rectangle((180, y - 8, 500, y + 42), 14, fill=(200, 220, 250))
            d.text((200 if mine else 30, y), text, font=font, fill=(20, 20, 20))
        y += 56
    ph = ph.rotate(-4, expand=True, fillcolor=(25, 25, 30))
    scene = Image.new("RGB", (2560, 1440), (25, 25, 30))
    scene.paste(ph, (700, 200))
    return scene


def test_reads_synthetic_phone():
    r = read_screen(_scene(), is_word)
    assert r is not None
    assert r["header"] == "Nico"
    texts = " | ".join(b["en"] for b in r["bubbles"])
    assert "plane" in texts and "smooth this over" in texts
    assert any(b["mine"] and b["en"].startswith("Good") for b in r["bubbles"])


def test_no_phone_in_plain_scene():
    assert read_screen(Image.new("RGB", (1920, 1080), (40, 60, 40)), is_word) is None
