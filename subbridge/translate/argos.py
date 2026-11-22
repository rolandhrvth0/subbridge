"""Offline translation with Argos Translate models (CTranslate2), without the heavy
argostranslate/stanza/torch stack. Models are downloaded once from the public Argos index."""
from __future__ import annotations

import codecs
import json
import re
import shutil
import threading
import urllib.request
import zipfile
from pathlib import Path

from ..paths import data_dir
from .base import TranslationError, Translator, split_sentences

INDEX_URL = "https://raw.githubusercontent.com/argosopentech/argospm-index/main/index.json"


def models_dir() -> Path:
    d = data_dir() / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


def installed_models() -> dict[tuple[str, str], Path]:
    """Best installed model per language pair (a 'precise' model beats the standard Argos one)."""
    out, prio = {}, {}
    for meta in models_dir().glob("*/metadata.json"):
        try:
            m = json.loads(meta.read_text(encoding="utf-8"))
            key, pr = (m["from_code"], m["to_code"]), int(m.get("priority", 0))
            if not (meta.parent / "model" / "model.bin").exists():
                continue
            if key not in out or pr > prio[key]:
                out[key], prio[key] = meta.parent, pr
        except (OSError, ValueError, KeyError):
            continue
    return out


# Precise offline models (OPUS-MT "tc-big", CC-BY 4.0, Helsinki-NLP; converted to CTranslate2 int8) on the
# project site; the checksum below is checked before anything is unpacked.
PRECISE = {("en", "hu"): {"url": "https://rolandhrvth.hu/subbridge/models/opus-big-en_hu-1.zip",
                          "sha256": "f7e5c07fb921103413462eb59a3de85655736f6c23bbe521b6abce9f10e14a5e", "size_mb": 207}}


def precise_installed(src: str, tgt: str) -> bool:
    p = installed_models().get((src, tgt))
    if not p:
        return False
    try:
        return int(json.loads((p / "metadata.json").read_text(encoding="utf-8")).get("priority", 0)) > 0
    except (OSError, ValueError):
        return False


def download_precise(src: str, tgt: str, progress=None) -> Path:
    import hashlib
    info = PRECISE.get((src, tgt))
    if not info:
        raise TranslationError(f"Nincs pontos modell ehhez: {src} → {tgt}")
    tmp = models_dir() / f".dl-precise-{src}-{tgt}.zip"
    h = hashlib.sha256()
    req = urllib.request.Request(info["url"], headers={"User-Agent": "SubBridge"})
    with urllib.request.urlopen(req, timeout=30) as r, open(tmp, "wb") as f:
        if not r.geturl().startswith("https://rolandhrvth.hu/"):
            raise TranslationError("Hibás letöltési cím")
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while chunk := r.read(1 << 16):
            f.write(chunk)
            h.update(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    if h.hexdigest() != info["sha256"]:
        tmp.unlink(missing_ok=True)
        raise TranslationError("A letöltött modell sérült – próbáld újra.")
    with zipfile.ZipFile(tmp) as z:
        root = z.namelist()[0].split("/")[0]
        for name in z.namelist():
            if not str((models_dir() / name).resolve()).startswith(str(models_dir().resolve())):
                raise TranslationError("Hibás modellcsomag")
        dest = models_dir() / root
        if dest.exists():
            shutil.rmtree(dest)
        z.extractall(models_dir())
    tmp.unlink(missing_ok=True)
    return dest


def fetch_index(timeout: float = 15) -> list[dict]:
    req = urllib.request.Request(INDEX_URL, headers={"User-Agent": "SubBridge"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def download_model(source: str, target: str, progress=None) -> Path:
    """Download and unpack the Argos package for source->target. ``progress(done, total)``."""
    pkgs = [p for p in fetch_index() if p.get("from_code") == source and p.get("to_code") == target]
    if not pkgs:
        raise TranslationError(f"Nincs offline modell ehhez: {source} → {target}")
    pkg = max(pkgs, key=lambda p: [int(x) for x in str(p.get("package_version", "0")).split(".")
                                   if x.isdigit()])
    url = pkg["links"][0]
    tmp = models_dir() / f".dl-{source}-{target}.zip"
    req = urllib.request.Request(url, headers={"User-Agent": "SubBridge"})
    with urllib.request.urlopen(req, timeout=30) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while chunk := r.read(1 << 16):
            f.write(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    with zipfile.ZipFile(tmp) as z:
        root = z.namelist()[0].split("/")[0]
        dest = models_dir() / root
        if dest.exists():
            shutil.rmtree(dest)
        for name in z.namelist():                       # safe extraction
            target_path = (models_dir() / name).resolve()
            if not str(target_path).startswith(str(models_dir().resolve())):
                raise TranslationError("Hibás modellcsomag")
        z.extractall(models_dir())
    tmp.unlink(missing_ok=True)
    return dest


class _Model:
    def __init__(self, path: Path, threads: int):
        import ctranslate2
        self.translator = ctranslate2.Translator(str(path / "model"), device="cpu", compute_type="int8",
                                                 intra_threads=threads)
        self.sp = self.bpe = self.tsp = None
        if (path / "source.spm").exists():                 # OPUS-MT / Marian: separate source/target pieces
            import sentencepiece
            self.sp = sentencepiece.SentencePieceProcessor(model_file=str(path / "source.spm"))
            self.tsp = sentencepiece.SentencePieceProcessor(model_file=str(path / "target.spm"))
        elif (path / "sentencepiece.model").exists():
            import sentencepiece
            self.sp = sentencepiece.SentencePieceProcessor(model_file=str(path / "sentencepiece.model"))
        elif (path / "bpe.model").exists():
            from sacremoses import MosesDetokenizer, MosesTokenizer
            from subword_nmt.apply_bpe import BPE
            meta = json.loads((path / "metadata.json").read_text(encoding="utf-8"))
            with codecs.open(str(path / "bpe.model"), encoding="utf-8") as f:
                self.bpe = BPE(f)
            self.mt = MosesTokenizer(meta.get("from_code", "en"))
            self.md = MosesDetokenizer(meta.get("to_code", "en"))
        else:
            raise TranslationError(f"Ismeretlen modellformátum: {path.name}")
        self.lock = threading.Lock()

    def run(self, sentences: list[str]) -> list[str]:
        if self.tsp:
            batch = [self.sp.encode(s, out_type=str) + ["</s>"] for s in sentences]
        elif self.sp:
            batch = [self.sp.encode(s, out_type=str) for s in sentences]
        else:
            batch = [self.bpe.process_line(self.mt.tokenize(s, return_str=True, escape=False)).split()
                     for s in sentences]
        with self.lock:
            res = self.translator.translate_batch(batch, beam_size=3 if self.tsp else 2, max_decoding_length=256)
        out = []
        for r in res:
            toks = r.hypotheses[0]
            if self.tsp:
                out.append(self.tsp.decode_pieces([t for t in toks if t not in ("</s>", "<pad>")]).strip())
            elif self.sp:
                out.append(self.sp.decode(toks).strip())
            else:
                t = " ".join(toks).replace("@@ ", "").replace("@@", "")
                out.append(self.md.detokenize(t.split(), unescape=True))
        # untranslated English contractions come back split ("Don 't")
        return [re.sub(r"(\w) ?('(?:t|s|re|ll|ve|d|m))\b", r"\1\2", o) for o in out]


class ArgosTranslator(Translator):
    id = "argos"
    name = "Offline (Argos)"
    online = False

    def __init__(self, threads: int = 4):
        self.threads = threads
        self._models: dict[tuple[str, str], _Model] = {}
        self._lock = threading.Lock()

    def _model(self, src: str, tgt: str) -> _Model:
        key = (src, tgt)
        with self._lock:
            if key not in self._models:
                path = installed_models().get(key)
                if not path:
                    raise TranslationError(f"Az offline {src}→{tgt} modell nincs letöltve.")
                self._models[key] = _Model(path, self.threads)
            return self._models[key]

    def has_pair(self, src: str, tgt: str) -> bool:
        return (src, tgt) in installed_models() or (
            (src, "en") in installed_models() and ("en", tgt) in installed_models())

    def translate(self, texts, source, target, context=None):
        if (source, target) not in installed_models() and source != "en" and target != "en":
            # pivot through English
            mid = self.translate(texts, source, "en")
            return self.translate(mid, "en", target)
        m = self._model(source, target)
        out = []
        for text in texts:
            sents = split_sentences(text)
            out.append(" ".join(m.run(sents)))
        return out

    def warmup(self):
        for (s, t) in list(installed_models()):
            try:
                self._model(s, t).run(["Hello."])
            except Exception:
                pass
