from __future__ import annotations

from .base import OcrEngine, OcrLine


def ocr_engines() -> dict[str, str]:
    """id -> display name of the engines usable on this machine."""
    import sys
    out = {"tesseract": "Tesseract"}
    from .rapid import rapid_installed
    if rapid_installed():
        out["rapid"] = "RapidOCR"
    if sys.platform == "win32":
        out["windows"] = "Windows OCR"
    return out


def create_ocr(engine: str, lang: str) -> OcrEngine:
    if engine == "rapid":
        from .rapid import RapidEngine
        e = RapidEngine(lang)
        if e.available():
            return e
    from .tesseract import TesseractEngine
    return TesseractEngine(lang)


__all__ = ["OcrEngine", "OcrLine", "create_ocr", "ocr_engines"]
