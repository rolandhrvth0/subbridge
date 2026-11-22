"""End-to-end OCR on generated subtitle images (no game assets needed)."""
import numpy as np
import pytest

from subbridge.engine import read_blocks
from subbridge.ocr.preprocess import PrepOptions, find_boxes
from subbridge.ocr.tesseract import TesseractEngine
from subbridge.pipeline.dedup import similarity

from .synth import subtitle

ocr = TesseractEngine("en")
pytestmark = pytest.mark.skipif(not ocr.available(), reason="tesseract not installed")

CASES = [
    (["Get in the car, we're late."], "Lena", True),
    (["You mean the guy ripping him off", "and shooting up all his connections?"], "Theo", True),
    (["I don't know who you think you are."], None, True),
    (["Keep your head down and follow me."], None, False),       # outlined text, no box
    (["Hey! What are you doing here?"], "Stranger", False),
]


@pytest.mark.parametrize("lines,speaker,box", CASES)
def test_reads_generated_subtitle(lines, speaker, box):
    img = np.asarray(subtitle(lines, speaker, box=box, seed=3))
    blocks, _, _ = read_blocks(img, ocr, PrepOptions(), 50, True)
    assert blocks, "nothing recognised"
    got = " ".join(b.text for b in blocks)
    assert similarity(got, " ".join(lines)) > 0.9, got
    if speaker:
        assert blocks[0].speaker == speaker


def test_box_found_on_generated_image():
    img = np.asarray(subtitle(["Box detection test line."], "Name"))
    assert len(find_boxes(img)) == 1


def test_two_speakers_two_boxes():
    a = np.asarray(subtitle(["First speaker line here."], "Anna", h=200, seed=1))
    b = np.asarray(subtitle(["Second speaker answers now."], "Bela", h=200, seed=2))
    img = np.vstack([a, b])
    blocks, boxes, _ = read_blocks(img, ocr, PrepOptions(), 50, True)
    assert len(boxes) == 2
    assert [b.speaker for b in blocks] == ["Anna", "Bela"]


def test_empty_scene_gives_nothing():
    from .synth import background
    blocks, _, _ = read_blocks(np.asarray(background(seed=5)), ocr, PrepOptions(), 60, True)
    assert blocks == []
