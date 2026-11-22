"""RapidOCR (PaddleOCR models on ONNX Runtime). Optional: used only when the package is installed.
Slower than Tesseract on the CPU, but more robust on stylised or low-contrast fonts."""
from __future__ import annotations

import re
import threading
import unicodedata

import numpy as np

from .base import OcrEngine, OcrLine


def rapid_installed() -> bool:
    try:
        import rapidocr_onnxruntime  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


class RapidEngine(OcrEngine):
    id = "rapid"
    name = "RapidOCR"

    def __init__(self, lang: str = "en"):
        self.lang = lang
        self._eng = None
        self._lock = threading.Lock()

    def available(self) -> bool:
        # the bundled models are latin/chinese; fine for English and most European languages
        return rapid_installed()

    def _engine(self):
        if self._eng is None:
            from rapidocr_onnxruntime import RapidOCR
            self._eng = RapidOCR(params={"Global.print_verbose": False})
        return self._eng

    @staticmethod
    def _rows(a: np.ndarray) -> list[tuple[int, int]]:
        """Split a binarised image (dark text on light) into text rows by horizontal projection."""
        ink = (a.min(axis=2) if a.ndim == 3 else a) < 128
        prof = ink.sum(axis=1)
        on = prof > max(2, ink.shape[1] * 0.004)
        rows, start = [], None
        for y, v in enumerate(on):
            if v and start is None:
                start = y
            elif not v and start is not None:
                rows.append((start, y))
                start = None
        if start is not None:
            rows.append((start, len(on)))
        # merge fragments (i dots, accents) into the row they belong to; drop specks
        merged: list[list[int]] = []
        for y0, y1 in rows:
            if merged and (y0 - merged[-1][1] < 4 or y1 - y0 < 6):
                merged[-1][1] = y1
            else:
                merged.append([y0, y1])
        out: list[tuple[int, int]] = []
        for y0, y1 in merged:
            if y1 - y0 >= 8:
                out += RapidEngine._split_tall(prof, y0, y1)
        return out

    @staticmethod
    def _split_tall(prof: np.ndarray, y0: int, y1: int, depth: int = 0) -> list[tuple[int, int]]:
        """Two text lines touching each other (descenders/ascenders): cut at the weakest row in the middle."""
        hgt = y1 - y0
        if depth > 2 or hgt < 40 or (y1 - y0) < 1:
            return [(y0, y1)]
        seg = prof[y0:y1].astype(float)
        lo, hi = int(hgt * 0.3), int(hgt * 0.7)
        cut = lo + int(np.argmin(seg[lo:hi]))
        body = np.median(seg[seg > 0]) if (seg > 0).any() else 0
        if body and seg[cut] < body * 0.22:
            return RapidEngine._split_tall(prof, y0, y0 + cut, depth + 1) + \
                RapidEngine._split_tall(prof, y0 + cut, y1, depth + 1)
        return [(y0, y1)]

    def recognize(self, img) -> list[OcrLine]:
        a = np.asarray(img.convert("RGB")) if hasattr(img, "convert") else np.asarray(img)
        if a.ndim == 2:
            a = np.stack([a] * 3, axis=-1)
        h = a.shape[0]
        out = []
        with self._lock:
            eng = self._engine()
            for y0, y1 in self._rows(a):
                pad = max(4, (y1 - y0) // 4)
                crop = np.ascontiguousarray(a[max(0, y0 - pad):min(h, y1 + pad)])
                res, _ = eng(crop, use_det=False, use_cls=False)
                for t, sc in res or []:
                    if str(t).strip():
                        txt = re.sub(r"(?<=[A-Za-z]):(?=[A-Za-z])", ": ", unicodedata.normalize("NFKC", str(t)).strip())
                        out.append(OcrLine(txt, float(sc) * 100))
        return out
