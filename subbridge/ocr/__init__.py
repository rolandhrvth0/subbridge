from __future__ import annotations

from .base import OcrEngine, OcrLine


def ocr_engines() -> dict[str, str]:
    """id -> display name of the engines usable on this machine."""
    out = {"auto": "Automatic", "tesseract": "Tesseract"}
    from .rapid import rapid_installed
    if rapid_installed():
        out["rapid"] = "RapidOCR"
    from .winocr import win_ocr_installed
    if win_ocr_installed():
        out["windows"] = "Windows OCR"
    return out


def create_ocr(engine: str, lang: str) -> OcrEngine:
    """'auto' = Windows' own recogniser on Windows (in-process, fast), Tesseract elsewhere. Any engine
    that cannot run here (missing package / language pack) falls back to Tesseract."""
    import sys
    if engine in ("auto", "windows") and sys.platform == "win32":
        from .winocr import WindowsEngine
        e = WindowsEngine(lang)
        if e.available():
            return e
    if engine == "rapid":
        from .rapid import RapidEngine
        e = RapidEngine(lang)
        if e.available():
            return e
    from .tesseract import TesseractEngine
    return TesseractEngine(lang)


__all__ = ["OcrEngine", "OcrLine", "create_ocr", "ocr_engines"]
