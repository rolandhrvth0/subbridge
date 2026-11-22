"""Windows' built-in text recogniser (Windows.Media.Ocr via WinRT). In-process and fast (tens of ms per
subtitle box) – no tesseract.exe start-up per read. Used by default on Windows when it can read the
source language; otherwise SubBridge falls back to Tesseract."""
from __future__ import annotations

import asyncio
import sys
import threading

import numpy as np

from .base import OcrEngine, OcrLine

_LANGS = {"en": ["en-US", "en-GB", "en"], "de": ["de-DE"], "fr": ["fr-FR"], "es": ["es-ES"],
          "it": ["it-IT"], "pt": ["pt-PT", "pt-BR"], "pl": ["pl-PL"], "nl": ["nl-NL"], "hu": ["hu-HU"]}
# Windows OCR packs for these read English text well too (same Latin alphabet, English words in the
# dictionary are rare but the letters come out right); used only when no English pack is installed
_LATIN = ("en", "de", "fr", "es", "it", "pt", "nl", "pl", "hu", "cs", "sk", "ro", "sv", "da", "nb", "fi")


def win_ocr_installed() -> bool:
    if sys.platform != "win32":
        return False
    try:
        from winrt.windows.media.ocr import OcrEngine as _E  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


class WindowsEngine(OcrEngine):
    id = "windows"
    name = "Windows OCR"

    def __init__(self, lang: str = "en"):
        self.lang = lang
        self._tls = threading.local()
        self._engine = None
        self.lang_tag = ""
        self.last_error = ""
        if win_ocr_installed():
            try:
                self._engine = self._create(lang)
            except Exception as e:  # noqa: BLE001
                self.last_error = repr(e)

    def _create(self, lang: str):
        from winrt.windows.globalization import Language
        from winrt.windows.media.ocr import OcrEngine as WE
        for tag in _LANGS.get(lang, [lang]):
            try:
                lg = Language(tag)
                if WE.is_language_supported(lg):
                    e = WE.try_create_from_language(lg)
                    if e is not None:
                        self.lang_tag = tag
                        return e
            except Exception:  # noqa: BLE001
                continue
        if lang in _LATIN:                           # e.g. Hungarian Windows without the English pack
            for lg in WE.available_recognizer_languages:
                if lg.language_tag.split("-")[0].lower() in _LATIN:
                    e = WE.try_create_from_language(lg)
                    if e is not None:
                        self.lang_tag = lg.language_tag
                        return e
        return None

    def available(self) -> bool:
        return self._engine is not None

    def _loop(self):
        lp = getattr(self._tls, "loop", None)
        if lp is None or lp.is_closed():
            lp = self._tls.loop = asyncio.new_event_loop()
        return lp

    @staticmethod
    def _bitmap(img):
        from winrt.windows.graphics.imaging import BitmapAlphaMode, BitmapPixelFormat, SoftwareBitmap
        from winrt.windows.storage.streams import DataWriter
        a = np.asarray(img.convert("RGB") if hasattr(img, "convert") else img)
        if a.ndim == 2:
            a = np.stack([a] * 3, axis=2)
        h, w = a.shape[:2]
        bgra = np.empty((h, w, 4), np.uint8)
        bgra[..., 0], bgra[..., 1], bgra[..., 2], bgra[..., 3] = a[..., 2], a[..., 1], a[..., 0], 255
        dw = DataWriter()
        dw.write_bytes(bgra.tobytes())
        return SoftwareBitmap.create_copy_from_buffer(dw.detach_buffer(), BitmapPixelFormat.BGRA8, w, h,
                                                      BitmapAlphaMode.PREMULTIPLIED)

    def _max_dim(self) -> int:
        if not hasattr(self, "_mx"):
            self._mx = 2600
            try:                                     # a static property of the OcrEngine class
                from winrt.windows.media.ocr import OcrEngine as WE
                self._mx = int(WE.max_image_dimension) or 2600
            except Exception:  # noqa: BLE001
                pass
        return self._mx

    def recognize(self, img) -> list[OcrLine]:
        if self._engine is None:
            return []
        a = np.asarray(img)
        h, w = a.shape[:2]
        mx = self._max_dim()
        if max(h, w) > mx:                           # Windows OCR refuses larger images
            from PIL import Image
            k = mx / max(h, w)
            img = Image.fromarray(a).resize((max(1, int(w * k)), max(1, int(h * k))))
        elif h < 40:                                 # tiny text reads better a bit larger
            from PIL import Image
            img = Image.fromarray(a).resize((w * 2, h * 2))
        try:
            res = self._loop().run_until_complete(self._engine.recognize_async(self._bitmap(img)))
        except Exception as e:  # noqa: BLE001
            self.last_error = repr(e)
            return []
        out = []
        for ln in res.lines:
            t = " ".join(wd.text for wd in ln.words).strip()
            if t and any(ch.isalpha() for ch in t):
                # Windows OCR gives no confidence; it drops what it cannot read, so treat lines as sure
                out.append(OcrLine(t, 90.0))
        return out
