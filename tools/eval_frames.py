"""Run read_blocks over recorded frames and print what each frame yields (for tuning).
Usage: python tools/eval_frames.py <glob> [step]"""
import glob
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from subbridge.engine import read_blocks  # noqa: E402
from subbridge.ocr.preprocess import PrepOptions  # noqa: E402
from subbridge.ocr.tesseract import TesseractEngine  # noqa: E402

files = sorted(glob.glob(sys.argv[1]))[:: int(sys.argv[2]) if len(sys.argv) > 2 else 1]
ocr = TesseractEngine()
for f in files:
    rgb = np.asarray(Image.open(f).convert("RGB"))
    blocks, boxes, _ = read_blocks(rgb, ocr, PrepOptions(), 60, True)
    if blocks:
        print(Path(f).parent.name[:7], Path(f).name[:11], len(boxes), " || ".join(f"[{b.speaker}] {b.text}" for b in blocks))
