"""Fallback backend (other platforms): whole screens only, via mss."""
from __future__ import annotations

import numpy as np

from .base import CaptureError, CaptureSource


class MssCapture(CaptureSource):
    def __init__(self):
        try:
            import mss
        except ImportError as e:
            raise CaptureError("A képernyőrögzítéshez az mss csomag kell.", "generic") from e
        self._mss = mss.mss()

    def list_screens(self):
        return [(m["left"], m["top"], m["width"], m["height"]) for m in self._mss.monitors[1:]]

    def source_size(self, kind, ident):
        _, _, w, h = self.list_screens()[int(ident)]
        return w, h

    def grab(self, kind, ident, rect=None):
        if kind != "screen":
            raise CaptureError("Ezen a rendszeren csak teljes képernyő választható.", "generic")
        sx, sy, sw, sh = self.list_screens()[int(ident)]
        x, y, w, h = rect or (0, 0, sw, sh)
        shot = self._mss.grab({"left": sx + x, "top": sy + y, "width": w, "height": h})
        return np.asarray(shot)[..., 2::-1].copy()
