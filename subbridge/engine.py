"""Capture → OCR → dialogue lines → tracker → conversation → translate → broadcast."""
from __future__ import annotations

import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutTimeout
from dataclasses import dataclass, field

import numpy as np

from .capture import CaptureError, CaptureSource
from .config import AppSettings, Profile
from .ocr.preprocess import (PrepOptions, binarize, box_color, boxless_blocks, find_boxes, fits_text, glyph_mask,
                             prepare_boxes)
from .ocr import create_ocr
from .paths import config_dir
from .pipeline.textclean import Line, is_dialogue, normalise_for_compare, split_lines
from .pipeline.dedup import similarity
from .pipeline.tracker import LineTracker
from .translate import TranslationError, create_translator
from .translate.registry import engine_key
from .translate.argos import ArgosTranslator, installed_models
from .translate.cache import TranslationCache
from .translate.glossary import Glossary

log = logging.getLogger(__name__)

PRIMARY_WAIT = 2.5          # seconds to wait for an online translator before using the offline one
MERGE_WINDOW = 8.0          # seconds: an unfinished sentence may be continued by the same speaker


@dataclass
class Callbacks:
    status: callable = lambda state, message="", code="": None     # running|waiting|error|stopped
    preview: callable = lambda img, boxes: None
    subtitle: callable = lambda msg: None
    stats: callable = lambda d: None
    overlay: callable = lambda boxes: None          # in-game overlay state, see Engine._emit_overlay
    phone: callable = lambda state: None            # in-game phone: dict or None, see Engine._phone_loop


@dataclass
class Entry:
    """One bubble in the conversation (may hold several merged subtitle lines)."""
    id: int
    speaker: str | None
    note: str | None
    parts: list[str] = field(default_factory=list)
    t_first: float = 0.0
    t_last: float = 0.0
    version: int = 0
    text_hu: str = ""
    engine: str = ""

    @property
    def original(self) -> str:
        return " ".join(self.parts)


def read_lines(rgb: np.ndarray, ocr, opts: PrepOptions, min_conf: int, speaker: bool, lang: str = "en",
               color_hint=None) -> tuple[list[Line], list, object]:
    """One frame → dialogue lines (top to bottom). Returns (lines, boxes, box_color)."""
    lines, boxes, color, _ = read_lines_ex(rgb, ocr, opts, min_conf, speaker, lang, color_hint)
    return lines, boxes, color


def read_lines_ex(rgb, ocr, opts: PrepOptions, min_conf: int, speaker: bool, lang: str = "en", color_hint=None,
                  boxed_only: bool = False, prev=None, prefer_textless: bool = False):
    """Like read_lines, plus the index of the box every line came from (-1: no box mode).
    boxed_only: the game is known to draw subtitle boxes – no box means no subtitle, skip the costly
    whole-region OCR (that fallback is for outlined, box-less subtitles)."""
    boxes, color = [], None
    if opts.find_box and opts.text_color in ("light", "white", "yellow"):
        if color_hint is not None:
            boxes = find_boxes(rgb, color=color_hint)
            color = color_hint if boxes else None
        if not boxes:
            color = box_color(rgb[::3, ::3])
            boxes = find_boxes(rgb, color=color) if color is not None else []
    # a "box" that does not hold its text like a subtitle box is a dark patch of the scene; in a game whose
    # subtitles are box-less any box is (prefer_textless)
    boxes = [] if prefer_textless else [b for b in boxes if fits_text(rgb, b)]
    if not boxes and boxed_only:
        return [], [], color, []

    def ocr_images(images, from_boxes):
        out, idx = [], []
        for bi, im in enumerate(images):
            text = " ".join(ln.text for ln in ocr.recognize(im) if ln.confidence >= min_conf)
            for ln in split_lines(text, speaker, lang):
                if is_dialogue(ln, lang):
                    out.append(ln)
                    idx.append(bi if from_boxes else -1)
        return out, idx

    boxless = opts.text_color == "light" and not opts.threshold
    if boxes:
        lines, line_box = ocr_images(prepare_boxes(rgb, boxes, opts), True)
        if lines or boxed_only or not boxless:
            return lines, boxes, color, line_box
        boxes, color = [], None          # a dark patch of the scene looked like a box: read it box-less
    if boxless:
        # box-less subtitles: OCR each centred text block on its own (subtitle, objective line …)
        gm = glyph_mask(rgb, prev)          # prev: earlier picture, filters a moving background
        images = [binarize(rgb[y0:y1, x0:x1], opts, mask=gm[y0:y1, x0:x1])
                  for x0, y0, x1, y1 in boxless_blocks(rgb, gm)]
    else:
        images = [binarize(rgb, opts)]
    lines, line_box = ocr_images(images, False)
    return lines, boxes, color, line_box


def _boxes_signature(rgb: np.ndarray, boxes) -> list:
    """Position + a 6×48 grey thumbnail of every subtitle box (cheap, ~0.1 ms per box)."""
    out = []
    for (x0, y0, x1, y1) in boxes:
        ys = np.linspace(y0, max(y0, y1 - 1), 6).astype(int)
        xs = np.linspace(x0, max(x0, x1 - 1), 48).astype(int)
        out.append(((x0, y0, x1, y1), rgb[ys][:, xs].mean(axis=2)))
    return out


def _same_boxes(a: list, b: list) -> bool:
    if len(a) != len(b):
        return False
    for (ra, ta), (rb, tb) in zip(a, b):
        if max(abs(u - v) for u, v in zip(ra, rb)) > 4 or float(np.abs(ta - tb).mean()) > 6:
            return False
    return True


def text_line_height(crop: np.ndarray) -> int:
    """Height of one text row in a subtitle box (bright glyph rows), for sizing the overlay font."""
    bright = crop.max(axis=2) > 190
    on = bright.sum(axis=1) > max(2, crop.shape[1] * 0.01)
    runs, n = [], 0
    for v in on:
        if v:
            n += 1
        elif n:
            runs.append(n)
            n = 0
    if n:
        runs.append(n)
    runs = [r for r in runs if r >= 6]
    return int(np.median(runs)) if runs else max(12, crop.shape[0] // 2)


def name_color(crop: np.ndarray):
    """Colour of the speaker name (the first coloured glyphs in the box), or None."""
    part = crop[::2, : max(2, crop.shape[1] // 3):2].reshape(-1, 3).astype(int)
    mx, mn = part.max(axis=1), part.min(axis=1)
    sel = part[(mx > 140) & (mx - mn > 45)]
    if len(sel) < 8:
        return None
    return tuple(int(v) for v in sel.mean(axis=0))


# kept for tests / tools written against the first version
def read_blocks(rgb, ocr, opts, min_conf, speaker, color_hint=None):
    return read_lines(rgb, ocr, opts, min_conf, speaker, "en", color_hint)


class SpeakerNames:
    """Keeps speaker names consistent: a name cut off by a fade-in or the region edge ("Loca", "Strang")
    is replaced by the full name seen before ("Local", "Stranger")."""

    def __init__(self):
        self.counts: dict[str, int] = {}

    def fix(self, name: str | None, final: bool = False) -> str | None:
        if not name:
            return name
        if not final:
            self.counts[name] = self.counts.get(name, 0) + 1
        low = name.lower()
        own = self.counts.get(name, 0)

        def pick(rel, factor):
            best, best_n = None, own
            for known, n in self.counts.items():
                k = known.lower()
                if k == low or n < 2 or not rel(k):
                    continue
                # only map to a clearly more frequent reading ("Local" vs "Locals" are both real speakers)
                if n > best_n and n >= factor * own:
                    best, best_n = known, n
            return best

        best = pick(lambda k: len(low) >= 3 and (k.startswith(low) or k.endswith(low) or low.endswith(" " + k)), 1)
        if best is None:
            best = pick(lambda k: abs(len(k) - len(low)) <= 2 and similarity(k, low) >= 0.6, 2)
        return best or name


_CONTRACTION = re.compile(r"(\w) ('(?:t|s|re|ll|ve|d|m))\b")


def _unfinished(text: str) -> bool:
    return not re.search(r"[.!?…\"')\]\-–—]$", text.strip())     # "my car-" = interrupted, not unfinished


class Engine:
    def __init__(self, settings: AppSettings, capture: CaptureSource, cb: Callbacks):
        self.settings = settings
        self.capture = capture
        self.cb = cb
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="tr")
        self._net = ThreadPoolExecutor(max_workers=2, thread_name_prefix="net")
        self.cache = TranslationCache(config_dir() / "translation_cache.json")
        self._argos = ArgosTranslator()
        self._translator = None
        self._translator_key = None
        self._lock = threading.Lock()
        self.window_id: int | None = None
        self.profile: Profile = settings.profile()
        self._entries: dict[int, Entry] = {}
        self._track_to_entry: dict[int, int] = {}
        self._last_entry: Entry | None = None
        self._entry_ids = 0
        self._visible: list[int] = []
        self._track_hu: dict[int, tuple[str, str | None, str]] = {}   # track -> (english, speaker, translation)
        self._ov_geom: list[dict] = []
        self._ov_sent = None
        self._zone_geom: list[dict] = []
        self._classic_boxes: list[dict] = []        # PC overlay boxes from ClassicOverlay
        self._quick: dict[str, tuple] = {}         # first-read translations for the overlay (norm -> (src, speaker, hu))
        self._ov_px: list[int] = []          # recent text heights: the game's font size is constant

    # ---------------------------------------------------------------- control
    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self, window_id: int | None = None):
        self.stop()
        self.profile = self.settings.profile()
        self.window_id = window_id
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="engine", daemon=True)
        self._thread.start()
        if any(z.get("on", True) for z in self.profile.zones):
            self._zone_thread = threading.Thread(target=self._zones_loop, name="zones", daemon=True)
            self._zone_thread.start()
        if self.profile.game_phone:
            self._phone_thread = threading.Thread(target=self._phone_loop, name="phone", daemon=True)
            self._phone_thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        self._thread = None
        for attr in ("_phone_thread", "_zone_thread"):
            t = getattr(self, attr, None)
            if t:
                t.join(timeout=3)
            setattr(self, attr, None)

    def shutdown(self):
        self.stop()
        self._pool.shutdown(wait=False, cancel_futures=True)
        self._net.shutdown(wait=False, cancel_futures=True)
        self.cache.save()

    # ---------------------------------------------------------------- source
    def resolve_window(self) -> int | None:
        p = self.profile
        if p.source_kind != "window":
            return None
        wins = self.capture.list_windows()
        if self.window_id and any(w.id == self.window_id for w in wins):
            return self.window_id
        if p.window_title:
            for w in wins:
                if w.title == p.window_title:
                    return w.id
            low = p.window_title.lower()
            for w in wins:
                if low in w.title.lower() or w.title.lower() in low:
                    return w.id
        return None

    def region_rect(self, ident, full_width: bool = False) -> tuple[int, int, int, int]:
        """full_width: the game draws subtitle boxes – search them across the whole width (a long
        subtitle must never be cut by the selected area; only boxes are read, so side HUD text is no issue)."""
        kind = self.profile.source_kind or "screen"
        sw, sh = self.capture.source_size(kind, ident)
        fx, fy, fw, fh = self.profile.region
        if full_width:
            fx, fw = 0.0, 1.0
        return int(fx * sw), int(fy * sh), max(8, int(fw * sw)), max(8, int(fh * sh))

    # ---------------------------------------------------------------- translation
    def _primary(self):
        p = self.profile
        g = Glossary.from_list(p.glossary)
        key = (p.engine, engine_key(p.engine, self.settings.__dict__), tuple(g.keep_terms()))
        if self._translator_key != key:
            self._translator = None
            if p.engine != "argos":
                try:
                    self._translator = create_translator(p.engine, self.settings.__dict__, g.keep_terms())
                    self._net.submit(self._translator.warmup)
                except TranslationError as e:
                    self.cb.status("running", str(e), "translator")
            self._translator_key = key
        return self._translator

    def _translate_text(self, engine, text: str, src: str, tgt: str, glossary: Glossary, ctx) -> str:
        from .translate.textprep import textprep
        tp = textprep()
        text = tp.prep(text, src)                        # slang -> plain English (feed packs)
        cached = self.cache.get(engine.id, src, tgt, text)
        if cached is not None:
            return tp.post_fix(_CONTRACTION.sub(r"\1\2", cached), tgt)   # entries cached by older versions
        t = glossary.before(text)
        mapping = {}
        if engine.id != "deepl":
            t, mapping = glossary.protect(t)
        out = engine.translate([t], src, tgt, context=ctx)[0]
        out = glossary.after(Glossary.restore(out, mapping))
        self.cache.put(engine.id, src, tgt, text, out)
        return tp.post_fix(out, tgt)                     # fixes and the offensive-word safety net

    @staticmethod
    def _names_only(text: str) -> bool:
        """'Chester! Shanese!' – only names (capitalised words that are no English words): nothing to
        translate, and machine translation tends to drop or mangle them."""
        from .pipeline.textclean import is_word
        toks = re.findall(r"[A-Za-z][A-Za-z'’-]*", text)
        common = {"hey", "hi", "yes", "no", "yeah", "ok", "okay", "mom", "dad", "man", "go", "come", "stop", "wait",
                  "help", "run", "please", "sorry", "thanks", "what", "why", "who", "where", "oh", "shit", "fuck",
                  "damn", "babe", "baby", "honey", "dude", "bro", "sir", "boss", "look", "listen", "hello", "bye"}
        return (bool(toks) and len(toks) <= 4 and all(t[0].isupper() for t in toks)
                and any(not is_word(t.lower()) for t in toks) and not any(t.lower() in common for t in toks))

    def translate(self, text: str, ctx: list[str]) -> tuple[str, str]:
        """One translation per text, no visible swapping: the online engine gets PRIMARY_WAIT seconds,
        the offline engine is only used when it fails or is too slow."""
        p = self.profile
        src, tgt = p.source_lang, p.target_lang
        if src == tgt or self._names_only(text):
            return text, "none"
        from .translate.corrections import corrections
        own = corrections().get(text, tgt)              # the user's own fix always wins
        if own:
            return own, "own"
        glossary = Glossary.from_list(p.glossary)
        primary = self._primary()
        if primary is not None:
            fut = self._net.submit(self._translate_text, primary, text, src, tgt, glossary, ctx)
            try:
                return fut.result(timeout=PRIMARY_WAIT), primary.id
            except TranslationError as e:
                self.cb.status("running", str(e), "translator")
            except FutTimeout:
                log.warning("online translator too slow, using offline")
            except Exception as e:  # noqa: BLE001
                log.warning("online translator failed: %s", e)
        if self._argos.has_pair(src, tgt):
            try:
                return self._translate_text(self._argos, text, src, tgt, glossary, ctx), "argos"
            except TranslationError as e:
                self.cb.status("running", str(e), "no_model")
        return text, "none"

    def _context(self, before: Entry) -> list[str]:
        ids = sorted(i for i in self._entries if i < before.id)[-3:]
        return [self._entries[i].original for i in ids]

    def _publish_entry(self, e: Entry, action: str, version: int, t_seen: float):
        ctx = self._context(e)
        hu, engine = self.translate(e.original, ctx)
        with self._lock:
            if version != e.version:
                return                                   # a newer version is on its way
            e.text_hu, e.engine = hu, engine
        self.cb.subtitle({
            "type": "line", "id": e.id, "action": action, "speaker": e.speaker, "note": e.note,
            "text": hu, "original": e.original, "lang": self.profile.target_lang, "engine": engine,
            "latency_ms": int((time.time() - t_seen) * 1000), "ts": time.time()})
        self._overlay_texts(e, hu)

    # ---------------------------------------------------------------- in-game overlay
    def _overlay_texts(self, e: Entry, hu: str):
        """The overlay replaces each English box with its own translation: a merged entry's later
        parts are translated on their own (cached, so usually free)."""
        parts = dict(getattr(e, "_part_index", {}))
        for tid, idx in parts.items():
            if idx >= len(e.parts):
                continue
            src = e.parts[idx]
            if len(e.parts) == 1:
                self._track_hu[tid] = (src, e.speaker, hu)
            elif self.profile.overlay and self._track_hu.get(tid, ("",))[0] != src:
                ctx = [p for p in e.parts[:idx]][-2:]
                self._track_hu[tid] = (src, e.speaker, self.translate(src, ctx)[0])
        if len(self._track_hu) > 400:
            for k in sorted(k for k in self._track_hu if k > 0)[:200]:
                self._track_hu.pop(k, None)
        self._emit_overlay()

    def _emit_overlay(self):
        with self._lock:
            out = []
            out.extend(self._classic_boxes)
            for g in self._ov_geom + self._zone_geom:
                lines = []
                for t in g["tracks"]:
                    v = self._quick.get(t[2:]) if isinstance(t, str) else self._track_hu.get(t)
                    if v is None and isinstance(t, str):
                        v = (None, None, "")                     # translation on its way: cover the original now
                    if v is not None:
                        lines.append((v[1], v[2]))
                if lines:
                    out.append({"rect": g["rect"], "bg": g["bg"], "name": g["name"], "px": g["px"],
                                "max_w": g["max_w"], "lines": lines, "slot": 10 + len(out)})
            key = [(b.get("slot"), tuple(b["rect"]), tuple(b["lines"])) for b in out]
            if key == self._ov_sent:
                return
            self._ov_sent = key
        self.cb.overlay(out)

    def _quick_translate(self, ln: Line, norm: str):
        """The overlay shows a line on its very first read (like a human would): translate it right away;
        the cache makes the later, confirmed version free and identical."""
        if norm in self._quick or len(norm) < 3:
            return
        self._quick[norm] = (ln.text, ln.speaker, "")
        if len(self._quick) > 300:
            for k in list(self._quick)[:150]:
                self._quick.pop(k, None)

        def run():
            try:
                hu = self.translate(ln.text, [])[0]
            except Exception:  # noqa: BLE001
                return
            self._quick[norm] = (ln.text, ln.speaker, hu)
            self._emit_overlay()
        self._pool.submit(run)

    def _cover_now(self, rgb, boxes, color, ident, rect):
        """Boxes not covered yet get an empty cover box immediately (text follows after OCR)."""
        p = self.profile
        try:
            if not self.capture.is_foreground(p.source_kind, ident):
                return
            ox, oy = self.capture.origin(p.source_kind, ident)
        except (CaptureError, NotImplementedError):
            return
        gx, gy = ox + rect[0], oy + rect[1]
        add = []
        for i, (x0, y0, x1, y1) in enumerate(boxes):
            r = (gx + x0, gy + y0, gx + x1, gy + y1)
            crop = rgb[y0:y1, x0:x1]
            px = int(np.median(self._ov_px)) if self._ov_px else text_line_height(crop)
            add.append({"rect": r, "bg": tuple(int(v) for v in color), "name": name_color(crop), "px": px,
                        "tracks": [f"q:__cover{i}"], "max_w": rect[2]})
        if not add:
            return
        with self._lock:
            # a cover replaces an old box at about the same place (the next subtitle), keeps the others
            keep = [g for g in self._ov_geom if not any(abs(g["rect"][3] - a["rect"][3]) < 30
                                                        and abs(g["rect"][1] - a["rect"][1]) < 60 for a in add)]
            self._ov_geom = keep + add
        self._emit_overlay()

    def _update_overlay(self, rgb, boxes, color, line_box, track_ids, ident, rect, active: bool, lines=None):
        p = self.profile
        geom = []
        if active and boxes:
            try:
                ox, oy = self.capture.origin(p.source_kind, ident)
            except (CaptureError, NotImplementedError):
                ox = oy = None
            if ox is not None:
                for bi, (x0, y0, x1, y1) in enumerate(boxes):
                    tracks = []
                    for i, (t, b) in enumerate(zip(track_ids, line_box)):
                        if b != bi:
                            continue
                        if t:
                            tracks.append(t)
                        elif lines is not None and i < len(lines):
                            norm = normalise_for_compare(lines[i].text)
                            self._quick_translate(lines[i], norm)
                            tracks.append("q:" + norm)
                    if not tracks:
                        continue
                    crop = rgb[y0:y1, x0:x1]
                    gx, gy = ox + rect[0], oy + rect[1]
                    self._ov_px = (self._ov_px + [text_line_height(crop)])[-25:]
                    px = int(np.median(self._ov_px))
                    geom.append({"rect": (gx + x0, gy + y0, gx + x1, gy + y1),
                                 "bg": tuple(int(v) for v in color) if color is not None else (20, 20, 20),
                                 "name": name_color(crop), "px": px, "tracks": tracks,
                                 "max_w": rect[2]})
        with self._lock:
            old = self._ov_geom
            same = len(old) == len(geom) and all(
                a["tracks"] == b["tracks"] and max(abs(u - v) for u, v in zip(a["rect"], b["rect"])) <= 3
                for a, b in zip(old, geom))
            if same:
                return
            self._ov_geom = geom
        self._emit_overlay()

    # ---------------------------------------------------------------- conversation
    def _on_event(self, kind: str, track_id: int, line: Line, t_seen: float):
        with self._lock:
            now = time.time()
            if kind == "update" and track_id in self._track_to_entry:
                e = self._entries[self._track_to_entry[track_id]]
                # replace this track's part inside the (possibly merged) entry
                idx = getattr(e, "_part_index", {}).get(track_id, len(e.parts) - 1)
                e.parts[idx] = line.text
                e.speaker = e.speaker or line.speaker
                e.note = e.note or line.note
                action = "update"
            else:
                last = self._last_entry
                if (last and last.parts and _unfinished(last.parts[-1]) and now - last.t_last < MERGE_WINDOW
                        and (last.speaker or "").lower() == (line.speaker or "").lower()):
                    e = last                                      # "Head down to the harbor," + "and wait for me..."
                    e.parts.append(line.text)
                    action = "update"
                else:
                    self._entry_ids += 1
                    e = Entry(self._entry_ids, line.speaker, line.note, [line.text], now)
                    self._entries[e.id] = e
                    action = "new"
                    if len(self._entries) > 200:
                        for k in sorted(self._entries)[:100]:
                            self._entries.pop(k, None)
                if not hasattr(e, "_part_index"):
                    e._part_index = {}
                e._part_index[track_id] = len(e.parts) - 1
                self._track_to_entry[track_id] = e.id
                self._last_entry = e
            e.t_last = now
            e.version += 1
            version = e.version
        self._pool.submit(self._publish_entry, e, action, version, t_seen)

    def _publish_visible(self, track_ids: list[int]):
        ids = sorted({self._track_to_entry[t] for t in track_ids if t in self._track_to_entry})
        if ids != self._visible:
            self._visible = ids
            self.cb.subtitle({"type": "visible", "ids": ids})

    # ---------------------------------------------------------------- main loop
    def _loop(self):
        p = self.profile
        ocr = create_ocr(p.ocr_engine, p.source_lang)
        if not ocr.available():
            if getattr(ocr, "missing_data", lambda: False)():
                self.cb.status("error", "Hiányzik a szövegfelismerő nyelvi adata.", "no_ocr_data")
            else:
                self.cb.status("error", "A Tesseract OCR nincs telepítve.", "no_ocr")
            return
        min_conf = p.min_confidence if ocr.id == "tesseract" else min(p.min_confidence, 50)
        opts = PrepOptions(text_color=p.text_color, threshold=p.threshold, scale=p.scale,
                           invert=p.invert, find_box=p.find_box)
        tracker = LineTracker(stable_frames=p.stable_frames, similarity_threshold=min(p.similarity, 0.85))
        names = SpeakerNames()
        color_hint = None
        first_seen: dict[str, float] = {}
        black_frames = 0
        last_preview = 0.0
        state = ""
        if p.engine == "argos" and not installed_models().get((p.source_lang, p.target_lang)):
            self.cb.status("running", "Az offline fordítómodell nincs letöltve.", "no_model")
        frames, t_stat, ocr_ms = 0, time.time(), 0.0
        prev_rgb = None
        hits_box: list[float] = []     # subtitles read in boxes / box-less in the last minute (majority decides)
        hits_txt: list[float] = []
        empty_frames = 0
        last_sig, last_ocr = None, 0.0
        tick = max(p.interval_ms, 150) / 1000         # phone feed; the PC overlay has its own 70 ms loop
        # screen capture would read our own overlay; devices draw it in the Game View
        overlay_ok = p.overlay and p.source_kind in ("window", "device")
        classic = None
        if overlay_ok:
            # the PC overlay runs its own light loop (old translator's design); this loop only feeds
            # the phone / conversation and may be slower
            from .classic_overlay import ClassicOverlay
            self._classic = ClassicOverlay(self, self._set_classic)
            threading.Thread(target=self._classic.run, name="overlay", daemon=True).start()
        ov_live = self._classic if overlay_ok else None     # for the live status line
        overlay_ok = False          # the per-track overlay below is replaced by ClassicOverlay
        while not self._stop.is_set():
            t0 = time.time()
            try:
                if p.source_kind == "window":
                    ident = self.resolve_window()
                    if ident is None:
                        raise CaptureError("Nem találom a kiválasztott ablakot. Fut a program?", "window_gone")
                elif p.source_kind == "device":
                    ident = p.device_id
                else:
                    ident = p.screen_index
                rect = self.region_rect(ident, full_width=color_hint is not None and opts.find_box)
                rgb = self.capture.grab(p.source_kind or "screen", ident, rect)
            except CaptureError as e:
                if classic:
                    classic.clear()
                self._clear_overlay()
                if state != e.code:
                    self.cb.status("waiting", str(e), e.code)
                    state = e.code
                self._stop.wait(1.0)
                continue
            if rgb.max() < 6:
                black_frames += 1
                if black_frames == 8:
                    self.cb.status("waiting", "A kép teljesen fekete.", "black")
                    state = "black"
            else:
                black_frames = 0
                if state:
                    self.cb.status("running", "", "")
                    state = ""
            # cheap change detection: OCR only when the subtitle area changed, a line still waits for its
            # confirming read, or every interval_ms at the latest; the loop itself ticks every <=100 ms
            if color_hint is not None and opts.find_box:
                # the game draws subtitle boxes: watch only what is inside them (the scene behind keeps moving)
                quick_boxes = find_boxes(rgb, color=color_hint)
                sig = _boxes_signature(rgb, quick_boxes)
                changed = last_sig is None or not _same_boxes(sig, last_sig)
                if changed and overlay_ok and quick_boxes:
                    # cover new / changed boxes right now, before OCR: the original never flashes up
                    prev = last_sig if isinstance(last_sig, list) else []
                    fresh = [b for b, sg in zip(quick_boxes, sig) if not any(_same_boxes([sg], [o]) for o in prev)]
                    if fresh:
                        self._cover_now(rgb, fresh, color_hint, ident, rect)
            else:
                sig = rgb[::8, ::8].astype(np.int16)
                changed = last_sig is None or not isinstance(last_sig, np.ndarray) or last_sig.shape != sig.shape \
                    or float(np.abs(sig - last_sig).mean()) > 1.2
            pending = any(t is None for t in tracker.last_ids)
            if not changed and not pending and t0 - last_ocr < max(p.interval_ms / 1000, 0.6):
                self._stop.wait(max(0.0, tick - (time.time() - t0)))
                continue
            last_sig, last_ocr = sig, t0
            t1 = time.time()
            hits_box[:] = [t for t in hits_box if t0 - t < 60]
            hits_txt[:] = [t for t in hits_txt if t0 - t < 60]
            lines, boxes, color, line_box = read_lines_ex(
                rgb, ocr, opts, min_conf, p.split_speaker, p.source_lang, color_hint,
                boxed_only=len(hits_box) >= 3 and not hits_txt, prev=prev_rgb,
                prefer_textless=len(hits_txt) >= 6 and len(hits_txt) > 3 * len(hits_box))
            prev_rgb = rgb
            if boxes and lines:
                hits_box.append(t0)
            elif lines:
                hits_txt.append(t0)
            ocr_ms += (time.time() - t1) * 1000
            if color is not None:
                color_hint = color
            for ln in lines:
                ln.speaker = names.fix(ln.speaker)
                first_seen.setdefault(ln.text[:24], t0)
            for ev in tracker.feed(lines, t0):
                ev.line.speaker = names.fix(ev.line.speaker, final=True)
                self._on_event(ev.kind, ev.id, ev.line, first_seen.pop(ev.line.text[:24], t0))
            if overlay_ok:
                active = self.capture.is_foreground(p.source_kind, ident)
                has = active and bool(lines)
                empty_frames = 0 if has else empty_frames + 1
                if has or empty_frames >= 2:          # one missed read must not make the overlay blink
                    self._update_overlay(rgb, boxes, color, line_box, tracker.last_ids, ident, rect, active, lines)
            if len(first_seen) > 300:
                first_seen.clear()
            self._publish_visible(tracker.visible_ids())
            now = time.time()
            if now - last_preview > 0.2:
                self.cb.preview(rgb, boxes)
                last_preview = now
            frames += 1
            if now - t_stat > 2:
                self.cb.stats({"fps": frames / (now - t_stat), "ocr_ms": ocr_ms / max(frames, 1),
                               "overlay": ov_live.health() if ov_live is not None else None})
                frames, t_stat, ocr_ms = 0, now, 0.0
            self._stop.wait(max(0.0, tick - (time.time() - t0)))
        if classic:
            classic.clear()
        self._clear_overlay()
        self.cb.status("stopped")

    def _set_classic(self, boxes: list[dict]):
        with self._lock:
            self._classic_boxes = boxes
            self._ov_sent = None                    # always forward ClassicOverlay updates
        self._emit_overlay()

    # ---------------------------------------------------------------- extra zones
    def _zones_loop(self):
        """Help boxes, objectives, notifications …: each zone is read on its own, a text is sent once it
        was read the same way twice, and (with the overlay on) its box is covered with the translation."""
        from .pipeline.textclean import clean, has_real_text, normalise_for_compare
        p = self.profile
        zones = [z for z in p.zones if z.get("on", True) and len(z.get("region", [])) == 4]
        ocr = create_ocr(p.ocr_engine, p.source_lang)
        if not ocr.available():
            return
        opts = PrepOptions(text_color="any" if p.text_color == "dark" else p.text_color, find_box=True)
        state = [{"cand": "", "n": 0, "sent": "", "id": None} for _ in zones]
        overlay_ok = p.overlay and p.source_kind in ("window", "device")
        while not self._stop.wait(0.45):
            try:
                ident = self.resolve_window() if p.source_kind == "window" else (
                    p.device_id if p.source_kind == "device" else p.screen_index)
                if ident is None:
                    continue
                sw, sh = self.capture.source_size(p.source_kind or "screen", ident)
                active = self.capture.is_foreground(p.source_kind or "screen", ident)
                origin = self.capture.origin(p.source_kind or "screen", ident) if overlay_ok else (0, 0)
            except (CaptureError, NotImplementedError):
                continue
            geom = []
            for zi, (z, stt) in enumerate(zip(zones, state)):
                fx, fy, fw, fh = z["region"]
                rect = (int(fx * sw), int(fy * sh), max(8, int(fw * sw)), max(8, int(fh * sh)))
                try:
                    rgb = self.capture.grab(p.source_kind or "screen", ident, rect)
                except CaptureError:
                    continue
                color = box_color(rgb[::3, ::3])
                boxes = find_boxes(rgb, color=color) if color is not None else []
                images = prepare_boxes(rgb, boxes, opts) if boxes else [binarize(rgb, opts)]
                text = clean(" ".join(ln.text for im in images for ln in ocr.recognize(im)
                                      if ln.confidence >= p.min_confidence))
                if not has_real_text(text, 4):
                    stt["cand"], stt["n"] = "", 0
                    continue
                norm = normalise_for_compare(text)
                if norm == normalise_for_compare(stt["cand"]):
                    stt["n"] += 1
                else:
                    stt["cand"], stt["n"] = text, 1
                tid = -(zi + 1)
                if stt["n"] == 2 and norm != normalise_for_compare(stt["sent"]):
                    stt["sent"] = text
                    self._publish_zone(z, text, tid)
                if overlay_ok and active and boxes and stt["sent"] and \
                        similarity(normalise_for_compare(stt["sent"]), norm) > 0.8:
                    x0 = min(b[0] for b in boxes)
                    y0 = min(b[1] for b in boxes)
                    x1 = max(b[2] for b in boxes)
                    y1 = max(b[3] for b in boxes)
                    gx, gy = origin[0] + rect[0], origin[1] + rect[1]
                    geom.append({"rect": (gx + x0, gy + y0, gx + x1, gy + y1),
                                 "bg": tuple(int(v) for v in color), "name": None,
                                 "px": text_line_height(rgb[y0:y1, x0:x1]), "tracks": [tid],
                                 "max_w": rect[2]})
            with self._lock:
                changed = [(g["tracks"], g["rect"]) for g in geom] != [(g["tracks"], g["rect"]) for g in self._zone_geom]
                self._zone_geom = geom
            if changed:
                self._emit_overlay()
        with self._lock:
            self._zone_geom = []
        self._emit_overlay()

    def _publish_zone(self, zone: dict, text: str, tid: int):
        def run():
            t0 = time.time()
            hu, engine = self.translate(text, [])
            self._track_hu[tid] = (text, None, hu)
            with self._lock:
                self._entry_ids += 1
                eid = self._entry_ids
            self.cb.subtitle({"type": "line", "id": eid, "action": "new", "speaker": None, "note": None,
                              "zone": zone.get("kind", "other"), "zone_name": zone.get("name", ""),
                              "text": hu, "original": text, "lang": self.profile.target_lang, "engine": engine,
                              "latency_ms": int((time.time() - t0) * 1000), "ts": time.time()})
            self._emit_overlay()
        self._pool.submit(run)

    # ---------------------------------------------------------------- in-game phone
    def _phone_text(self, en: str, ctx: list[str], reply: bool = False) -> str:
        from .gamephone import REPLY_FIX, normalize_texting
        p = self.profile
        if reply:
            fix = REPLY_FIX.get(p.target_lang, {}).get(en.lower().strip(" .!?"))
            if fix:
                return fix
            ctx = ["Text message reply option."] + ctx
        return self.translate(normalize_texting(en), ctx)[0]

    def _phone_loop(self):
        """Every ~0.6 s look for a phone in the whole picture; read and translate it when it changed."""
        from .gamephone import find_phone, screen_signature, sig_diff, straighten, read_phone, bubbles, find_replies
        from .pipeline.textclean import is_word
        from PIL import Image
        p = self.profile
        last_sig, last_read, shown, gone_since = None, 0.0, None, None
        while not self._stop.wait(0.6):
            try:
                ident = self.resolve_window() if p.source_kind == "window" else (
                    p.device_id if p.source_kind == "device" else p.screen_index)
                if ident is None:
                    continue
                if p.source_kind == "window" and not self.capture.is_foreground("window", ident):
                    raise CaptureError("background", "bg")
                rgb = self.capture.grab(p.source_kind or "screen", ident)
            except CaptureError:
                if shown is not None:
                    shown = None
                    self.cb.phone(None)
                continue
            from .gamephone import quick_check
            ph = find_phone(Image.fromarray(rgb)) if quick_check(rgb) else None
            img = Image.fromarray(rgb) if ph else None
            now = time.time()
            if not ph:
                gone_since = gone_since or now
                if shown is not None and now - gone_since > 0.6:
                    shown, last_sig = None, None
                    self.cb.phone(None)
                continue
            gone_since = None
            crop = straighten(img, ph)
            sig = screen_signature(crop)
            if shown is not None and sig_diff(sig, last_sig) < 9 and now - last_read < 2.0:
                continue
            last_sig, last_read = sig, now
            header, bubs = bubbles(crop, read_phone(crop), is_word)
            replies = [r[4] for r in find_replies(crop)]
            ctx: list[str] = []
            items = []
            futs = []
            for b in bubs:
                futs.append(self._pool.submit(self._phone_text, b["en"], list(ctx[-3:])))
                ctx.append(b["en"])
            for b, f in zip(bubs, futs):
                items.append({"kind": "msg", "mine": bool(b["mine"]), "name": b.get("name", ""),
                              "en": b["en"], "text": f.result()})
            for r in replies:
                items.append({"kind": "reply", "mine": True, "name": "", "en": r,
                              "text": self._phone_text(r, ctx[-4:], reply=True)})
            if not items:
                continue
            try:
                ox, oy = self.capture.origin(p.source_kind or "screen", ident)
            except (CaptureError, NotImplementedError):
                ox, oy = 0, 0
            x0, y0, x1, y1 = ph["rect"]
            state = {"type": "phone", "header": header, "items": items,
                     "rect": (ox + x0, oy + y0, ox + x1, oy + y1), "frame": (ox, oy, rgb.shape[1], rgb.shape[0])}
            key = (header, tuple((i["en"], i["text"]) for i in items))
            if shown != key:
                shown = key
                self.cb.phone(state)
        if shown is not None:
            self.cb.phone(None)

    def _clear_overlay(self):
        with self._lock:
            had = bool(self._ov_geom) or bool(self._ov_sent)
            self._ov_geom = []
        if had:
            self._emit_overlay()
