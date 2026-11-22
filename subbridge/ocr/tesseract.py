from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from ..paths import data_dir, resource_dir
from .base import OcrEngine, OcrLine

_LANG_MAP = {"en": "eng", "de": "deu", "fr": "fra", "es": "spa", "it": "ita", "pt": "por",
             "pl": "pol", "ru": "rus", "ja": "jpn", "ko": "kor", "zh": "chi_sim", "hu": "hun",
             "nl": "nld", "tr": "tur", "cs": "ces", "uk": "ukr"}


def tessdata_dirs() -> list[Path]:
    cands = [data_dir() / "tessdata", resource_dir() / "tessdata"]
    if os.environ.get("TESSDATA_PREFIX"):
        cands.insert(0, Path(os.environ["TESSDATA_PREFIX"]))
    if sys.platform.startswith("linux"):
        cands += [Path("/usr/share/tesseract-ocr/5/tessdata"), Path("/usr/share/tesseract-ocr/4.00/tessdata"),
                  Path("/usr/share/tessdata")]
    elif sys.platform == "win32":
        cands += [Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Tesseract-OCR" / "tessdata"]
    return cands


def tesseract_cmd() -> str | None:
    """The tesseract executable: bundled next to the app, on PATH, or the usual Windows install."""
    exe = "tesseract.exe" if sys.platform == "win32" else "tesseract"
    cands = [resource_dir().parent / "tesseract" / exe]
    if sys.platform == "win32":
        for env in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
            if os.environ.get(env):
                cands += [Path(os.environ[env]) / "Tesseract-OCR" / exe, Path(os.environ[env]) / "Programs" / "Tesseract-OCR" / exe]
    for c in cands:
        if c.exists():
            return str(c)
    return shutil.which("tesseract")


TESSDATA_URL = "https://github.com/tesseract-ocr/tessdata_fast/raw/main/{lang}.traineddata"


def download_tessdata(language: str, progress=None) -> Path:
    """Fetch the (Apache-2.0) fast LSTM model for a language into the user data dir."""
    import urllib.request
    lang = _LANG_MAP.get(language, language)
    d = data_dir() / "tessdata"
    d.mkdir(parents=True, exist_ok=True)
    dst = d / f"{lang}.traineddata"
    tmp = dst.with_suffix(".part")
    req = urllib.request.Request(TESSDATA_URL.format(lang=lang), headers={"User-Agent": "SubBridge"})
    with urllib.request.urlopen(req, timeout=30) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while chunk := r.read(65536):
            f.write(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    if tmp.stat().st_size < 100_000:
        tmp.unlink()
        raise OSError("hibás letöltés")
    tmp.replace(dst)
    return dst


def find_tessdata(lang: str) -> Path | None:
    for d in tessdata_dirs():
        if (d / f"{lang}.traineddata").exists():
            return d
    return None


class TesseractEngine(OcrEngine):
    id = "tesseract"
    name = "Tesseract"

    def __init__(self, language: str = "en"):
        self.lang = _LANG_MAP.get(language, language)
        self.tessdata = find_tessdata(self.lang)
        self._tls = threading.local()
        try:
            import tesserocr  # noqa: F401  (availability check)
            self._inproc = True
        except ImportError:
            self._inproc = False
        self._cmd = None if self._inproc else tesseract_cmd()
        self.last_error = ""

    def available(self) -> bool:
        return self.tessdata is not None and (self._inproc or self._cmd is not None)

    def missing_data(self) -> bool:
        return self.tessdata is None

    def tsv(self, img, psm: int = 6) -> str:
        """Raw Tesseract TSV (with a header line) for any page segmentation mode."""
        return self._tsv(img, psm)

    def _tsv(self, img, psm: int = 6) -> str:
        if self._inproc:
            import tesserocr
            apis = getattr(self._tls, "apis", None)
            if apis is None:
                apis = self._tls.apis = {}
            api = apis.get(psm)
            if api is None:
                api = apis[psm] = tesserocr.PyTessBaseAPI(
                    path=str(self.tessdata) + os.sep, lang=self.lang, psm=psm, oem=tesserocr.OEM.LSTM_ONLY)
            api.SetImage(img)
            api.SetSourceResolution(70)
            # some locales print the confidence with a decimal comma
            return "h\n" + re.sub(r"\t(-?\d+),(\d+)\t", r"\t\1.\2\t", api.GetTSVText(0))
        env = dict(os.environ, TESSDATA_PREFIX=str(self.tessdata))
        flags = 0x08000000 if sys.platform == "win32" else 0          # CREATE_NO_WINDOW
        args = ["-l", self.lang, "--tessdata-dir", str(self.tessdata), "--oem", "1", "--psm", str(psm), "-c", "tessedit_create_tsv=1"]
        if sys.platform == "win32":
            # Windows: hand the image over as a file – piping binary data to stdin is unreliable there
            import tempfile
            fd, path = tempfile.mkstemp(suffix=".bmp", prefix="sb-ocr-")
            os.close(fd)
            try:
                img.save(path, "BMP")
                r = subprocess.run([self._cmd or "tesseract", path, "stdout", *args], capture_output=True,
                                   stdin=subprocess.DEVNULL, timeout=8, env=env, creationflags=flags,
                                   cwd=os.path.dirname(self._cmd) if self._cmd else None)
            finally:
                try:
                    os.remove(path)
                except OSError:
                    pass
        else:
            buf = io.BytesIO()
            img.save(buf, "PNG")
            r = subprocess.run([self._cmd or "tesseract", "stdin", "stdout", *args], input=buf.getvalue(),
                               capture_output=True, timeout=5, env=env, creationflags=flags)
        if r.returncode != 0 or not r.stdout:
            self.last_error = f"rc={r.returncode} " + (r.stderr or b"").decode("utf-8", "ignore")[-400:]
        return r.stdout.decode("utf-8", "ignore")

    def recognize(self, img) -> list[OcrLine]:
        lines: dict[tuple, list[tuple[str, float]]] = {}
        for row in self._tsv(img).splitlines()[1:]:
            c = row.split("\t")
            if len(c) < 12 or not c[11].strip():
                continue
            try:
                conf = float(c[10])
            except ValueError:
                continue
            lines.setdefault((int(c[2]), int(c[3]), int(c[4])), []).append((c[11].strip(), conf))
        out = []
        for key in sorted(lines):
            words = lines[key]
            alpha = [cf for w, cf in words if any(ch.isalpha() for ch in w)]
            if not alpha:
                continue
            out.append(OcrLine(" ".join(w for w, _ in words), sum(alpha) / len(alpha)))
        return out
