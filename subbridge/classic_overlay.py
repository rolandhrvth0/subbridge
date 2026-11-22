"""PC overlay logic ported from the author's earlier translator (the behaviour players liked):

* every subtitle box lives on its own: own cover window ("slot"), matched frame to frame by vertical
  overlap – with several speakers each box keeps its place and translation, nothing swaps or jumps;
* a new / changed box is covered at once (empty box), the translation fades in after;
* young boxes are re-read every 0.3 s for 2.5 s so a half-faded first read does not stick;
* a box pushed up by a new speaker keeps its translation (same text → same entry, just moved);
* after the original disappears the translation stays 0.8 s, and is shown at least 2 s;
* translation: memory first; online engine gets 0.22 s, otherwise the offline result shows at once and
  the online one replaces it when it arrives.

Runs inside the engine thread on the frames the engine already grabs (no second capture)."""
from __future__ import annotations

import logging
import time
from concurrent.futures import TimeoutError as FutTimeout
from dataclasses import dataclass, field

import numpy as np

from .ocr.preprocess import binarize, box_color, find_boxes, prepare_boxes
from .pipeline.dedup import similarity
from .pipeline.textclean import clean, has_real_text, is_dialogue, normalise_for_compare, split_lines

MAX_BOXES = 4
HOLD = 0.8          # s the translation stays after the original disappeared
MIN_SHOW = 2.0      # s a translation is shown at least
YOUNG = 2.5         # s after a new text during which it is re-read …
YOUNG_EVERY = 0.3   # … this often
log = logging.getLogger(__name__)
STALE_COLOR = 4.0   # s without any box before the remembered box colour is re-checked
ONLINE_WAIT = 0.3   # s the online translator may take; then the offline result shows and stays (no swapping)


def _sig(rgb: np.ndarray, box) -> np.ndarray:
    """Text pattern of a box (bright glyph pixels on a 12×96 grid): immune to video noise in the box
    background. Same text ≈ 0–5, different text > 20."""
    x0, y0, x1, y1 = box
    ys = np.linspace(y0, max(y0, y1 - 1), 12).astype(int)
    xs = np.linspace(x0, max(x0, x1 - 1), 96).astype(int)
    return (rgb[ys][:, xs].max(axis=2) > 140).astype(np.float32) * 100


def _has_box(strip: np.ndarray, color) -> bool:
    """Old probe: >= ~18 consecutive rows where a third of the strip has the subtitle-box colour."""
    c = np.asarray(color, np.int16)
    m = (np.abs(strip[::1, ::2].astype(np.int16) - c) <= 10).all(axis=2)
    rows = m.mean(axis=1) >= 0.35
    need = max(10, strip.shape[0] // 28)
    run = best = 0
    for v in rows:
        run = run + 1 if v else 0
        best = max(best, run)
    return best >= need


def _grown(box, rect, tol: int = 10) -> bool:
    """True if box reaches past rect on any side (by more than tol px)."""
    return (box[0] < rect[0] - tol or box[2] > rect[2] + tol
            or box[1] < rect[1] - tol or box[3] > rect[3] + tol)


def _bars_w(rgb: np.ndarray) -> int:
    """Width of the black side bars (a 16:9 picture on an ultrawide / 16:10 screen): columns that are
    black in every sampled row, taken from the narrower side so an off-centre dark area never counts."""
    w = rgb.shape[1]
    q = int(w * 0.25)                                       # bars never take more than a quarter per side
    if q < 1:
        return 0
    edges = np.concatenate([rgb[::6, :q], rgb[::6, w - q:]], axis=1)
    dark = edges.max(axis=(0, 2)) < 10
    if dark.all():                                          # fade to black: nothing to measure
        return 0
    left, right = int(np.argmin(dark[:q])) if not dark[:q].all() else q, \
        int(np.argmin(dark[q:][::-1])) if not dark[q:].all() else q
    return min(left, right)


def _text_boxes(rgb: np.ndarray, source_w: int) -> list[tuple[int, int, int, int]]:
    """Subtitles without a background box: find the white text lines in the middle of the band and
    return one box around the lowest group of lines (the overlay then draws its own box there).
    `source_w` is the width of the game picture (without side bars), centred in the band."""
    h, w = rgb.shape[:2]
    cx0, cx1 = max(0, int(w / 2 - source_w * 0.3)), min(w, int(w / 2 + source_w * 0.3))
    c = rgb[:, cx0:cx1]
    r, g, b = c[..., 0], c[..., 1], c[..., 2]              # per-channel uint8 ops: ~3x faster than int16 + axis=2
    mn = np.minimum(np.minimum(r, g), b)
    mx = np.maximum(np.maximum(r, g), b)
    mask = (mn > 185) & ((mx - mn) < 45)                   # white-ish glyph pixels (mx >= mn: no uint8 wrap)
    rows = mask.mean(axis=1) > 0.004
    runs, start = [], None
    for y, v in enumerate(list(rows) + [False]):
        if v and start is None:
            start = y
        elif not v and start is not None:
            if runs and start - runs[-1][1] <= 6:           # glyph gaps inside one line
                runs[-1] = (runs[-1][0], y)
            else:
                runs.append((start, y))
            start = None
    runs = [r for r in runs if 10 <= r[1] - r[0] <= 160]
    if not runs:
        return []
    lh = float(np.median([b - a for a, b in runs]))
    group = [runs[-1]]                                      # lowest line + the lines right above it
    for r in reversed(runs[:-1]):
        if group[0][0] - r[1] <= lh * 1.2:
            group.insert(0, r)
        else:
            break
    y0, y1 = group[0][0], group[-1][1]
    cols = np.where(mask[y0:y1].any(axis=0))[0]
    if len(cols) < 3 or cols[-1] - cols[0] < w * 0.04:
        return []
    dens = float(mask[y0:y1, cols[0]:cols[-1] + 1].mean())
    if not 0.04 <= dens <= 0.45:                            # text is sparse; a white wall / sky is not
        return []
    px, py = int(lh * 0.8), int(lh * 0.35)
    x0, x1 = max(0, cx0 + int(cols[0]) - px), min(w, cx0 + int(cols[-1]) + px)
    box = (x0, max(0, y0 - py), x1, min(h, y1 + py))
    if abs((box[0] + box[2]) / 2 - w / 2) > source_w * 0.14:
        return []
    return [box]


def _sig_diff(a, b) -> float:
    if a is None or b is None or a.shape != b.shape:
        return 255.0
    return float(np.abs(a - b).mean())


@dataclass
class Entry:
    rect: tuple
    slot: int
    en: str = ""                                   # what was read (normalised compare base)
    lines: list = field(default_factory=list)     # [(speaker, english)]
    hu: list = field(default_factory=list)        # [(speaker, translation)]
    sig: np.ndarray | None = None
    name_rgb: tuple | None = None
    last_seen: float = 0.0
    shown_at: float = 0.0
    last_ocr: float = 0.0
    gen: int = 0
    alive: bool = True
    px: int = 0
    requested: int = -1                           # gen whose translation was requested


class ClassicOverlay:
    def __init__(self, engine, emit):
        self.eng = engine
        self.emit_cb = emit
        self.entries: list[Entry] = []
        self.ctx: list[str] = []
        self._geo = (0, 0, 1, 1, 1)          # origin x/y of the region, region w, source w, …
        self.color = self._load_color()
        self.line_hs: list[int] = []         # heights of one-line subtitle boxes seen (font size reference)
        self.px_hist: list[int] = []         # font sizes used recently (keeps the size steady)
        self._pw_hist: list[tuple[float, int]] = []
        self.stats = dict(ticks=0, no_window=0, not_front=0, read=0, boxes=0, emits=0, errors=0)
        self._stat_t0 = time.time()
        self._last_err_log = 0.0
        self._last_box_t = time.time()       # last time a subtitle box was found
        self._relearn = None                 # box colour being re-learnt (kept once a subtitle is read)
        from concurrent.futures import ThreadPoolExecutor
        self.pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ovtr")   # never queues behind others

    # ------------------------------------------------------------------ own loop (like the old translator)
    def run(self):
        """70 ms ticks. A narrow centre strip (subtitles are always centred) tells in ~1 ms whether a box
        is there and whether it changed; the full subtitle band is read only then."""
        from .capture import CaptureError
        from .ocr import create_ocr
        from .ocr.preprocess import PrepOptions
        eng = self.eng
        p = eng.profile
        ocr = create_ocr(p.ocr_engine, p.source_lang)
        if not ocr.available():
            return
        opts = PrepOptions(text_color=p.text_color, threshold=p.threshold, scale=p.scale,
                           invert=p.invert, find_box=True)
        min_conf = p.min_confidence if ocr.id == "tesseract" else min(p.min_confidence, 50)
        kind = p.source_kind or "screen"
        last_psig, last_full = None, 0.0

        def warm():                         # load the offline model now, not on the first subtitle
            try:
                if eng._argos.has_pair(p.source_lang, p.target_lang):
                    eng._argos.translate(["Hello there."], p.source_lang, p.target_lang)
                primary = eng._primary()
                if primary is not None:
                    primary.warmup()
            except Exception:  # noqa: BLE001
                pass
        self.pool.submit(warm)
        while not eng._stop.wait(0.05):
            try:
                self._stat_tick()
                now = time.time()
                try:
                    ident = eng.resolve_window() if kind == "window" else (p.device_id if kind == "device" else p.screen_index)
                    if ident is None or not eng.capture.is_foreground(kind, ident):
                        self.stats["not_front" if ident is not None else "no_window"] += 1
                        self.clear()
                        continue
                    sw, sh = eng.capture.source_size(kind, ident)
                    _fx, fy, _fw, fh = p.region
                    band = (0, int(fy * sh), sw, max(8, int(fh * sh)))           # full width: never cut a subtitle
                    sw_strip = max(40, int(sw * 0.06))
                    probe = eng.capture.grab(kind, ident, (sw // 2 - sw_strip // 2, band[1], sw_strip, band[3]))
                except (CaptureError, NotImplementedError):
                    self.clear()
                    continue
                if self.color is None and now - last_full < 0.3:
                    continue                    # box colour not known yet: full search, but not on every tick
                stale = now - self._last_box_t > STALE_COLOR and now - last_full >= 0.5
                if self.color is not None and not _has_box(probe, self.color) and not stale:
                    last_psig = None
                    if self.entries:
                        self.process(None, None, band, sw, True, ocr, opts, min_conf, p.source_lang, self.color)
                    continue
                # text pattern of the strip (bright glyph pixels): a new sentence of similar length still
                # changes it, video noise in the box does not
                psig = (probe[::2, ::2].max(axis=2) > 140).astype(np.float32) * 100
                if (last_psig is not None and last_psig.shape == psig.shape
                        and float(np.abs(psig - last_psig).mean()) < 1.5 and now - last_full < 0.25):
                    continue
                last_psig, last_full = psig, now
                try:
                    origin = eng.capture.origin(kind, ident)
                    rgb = eng.capture.grab(kind, ident, band)
                except (CaptureError, NotImplementedError):
                    continue
                self.stats["read"] += 1
                self.process(rgb, origin, band, sw, True, ocr, opts, min_conf, p.source_lang, self.color)
            except Exception:  # noqa: BLE001  – never let the overlay thread die silently
                self.stats["errors"] += 1
                if time.time() - self._last_err_log > 30:
                    self._last_err_log = time.time()
                    log.exception("overlay loop error")
                try:
                    self.clear()
                except Exception:  # noqa: BLE001
                    pass
        self.clear()

    # ------------------------------------------------------------------ main step
    def process(self, rgb, origin, region, source_w, active, ocr, opts, min_conf, lang, color_hint):
        now = time.time()
        if rgb is not None:
            # game picture width: an ultrawide screen shows the 16:9 picture between black bars. The widest
            # picture of the last 20 s is used, so a dark scene can never make it narrower than it is.
            pw = source_w - 2 * _bars_w(rgb) if rgb.shape[1] == source_w else source_w
            self._pw_hist = [(t, v) for t, v in self._pw_hist if now - t < 20] + [(now, pw)]
        pic_w = max((v for _t, v in self._pw_hist), default=source_w)
        if origin is not None:
            self._geo = (origin[0] + region[0], origin[1] + region[1], region[2], pic_w)
        if not active:
            if self.entries:
                self.entries = []
                self._emit()
            return
        if rgb is None:                              # no box in the probe: only the hold / hide logic
            color, boxes, textbox = self.color, [], False
        else:
            if color_hint is not None:
                color = color_hint
            else:                           # learn from the centre (where subtitles are), not the neon at the sides
                w = rgb.shape[1]
                color = box_color(rgb[::3, int(w * 0.3):int(w * 0.7):3])
            def centred(bs):
                # subtitles are centred; notifications / map labels / menus at the sides are not
                return [b for b in bs if abs((b[0] + b[2]) / 2 - source_w / 2) <= pic_w * 0.14][:MAX_BOXES]
            boxes = centred(find_boxes(rgb, color=color)) if color is not None else []
            textbox = False
            if not boxes and color_hint is not None and now - self._last_box_t > STALE_COLOR:
                # the remembered box colour finds nothing for a while (another game, a semi-transparent
                # background, learnt at a bad moment): try the colour of this picture; it is only kept
                # once a subtitle is really read in such a box
                w = rgb.shape[1]
                fresh = box_color(rgb[::3, int(w * 0.3):int(w * 0.7):3])
                if fresh is not None:
                    found = centred(find_boxes(rgb, color=fresh))
                    if found:
                        color, boxes = fresh, found
                        self._relearn = fresh
            if not boxes:
                # no box at all (outlined / semi-transparent subtitles): cover the text itself
                boxes = _text_boxes(rgb, pic_w)
                textbox = bool(boxes)
        used: set[int] = set()          # entries settled this frame
        pending: set[int] = set()       # entries matched by position but whose box must be read
        todo = []
        changed = False
        self.stats["boxes"] += len(boxes)
        if boxes:
            self._last_box_t = now
        for box in boxes:
            sig = _sig(rgb, box)
            # same picture as a known box (it only moved, e.g. pushed up by a new speaker): carry it over
            # instantly with its translation – no OCR, no blank moment
            mv = next((x for x in self.entries if id(x) not in used | pending and x.en and x.sig is not None
                       and abs((box[2] - box[0]) - (x.rect[2] - x.rect[0])) <= 8
                       and abs((box[3] - box[1]) - (x.rect[3] - x.rect[1])) <= 6
                       and _sig_diff(sig, x.sig) < 8), None)
            if mv is not None and (abs(box[1] - mv.rect[1]) > 10 or abs(box[3] - mv.rect[3]) > 10):
                used.add(id(mv))
                mv.last_seen, mv.rect = now, box
                changed = True
                continue
            e = self._match(box, used | pending)
            if e is not None:
                young = e.en and now - e.shown_at < YOUNG and now - e.last_ocr > YOUNG_EVERY
                # the box grew (longer line, another speaker cut in): never "the same box" – the old,
                # smaller cover would leave the new English around it visible
                grown = _grown(box, e.rect)
                if _sig_diff(sig, e.sig) < 7 and e.en and not young and not grown:
                    used.add(id(e))                     # same box, same content: no OCR
                    e.last_seen = now
                    if abs(box[1] - e.rect[1]) > 10 or abs(box[3] - e.rect[3]) > 10:
                        e.rect = box
                        changed = True
                    continue
                pending.add(id(e))
                if e.hu and _sig_diff(sig, e.sig) >= 22:       # clearly new text, not video noise
                    e.hu = []                       # new text in this box: the old translation goes at once
                    e.requested = -1
                    changed = True
                if grown:                           # cover the whole new box NOW, before the OCR
                    e.rect = box
                    if e.hu:
                        e.hu = []
                        e.requested = -1
                    changed = True
            todo.append((e, box, sig))

        # cover new boxes and blank changed ones NOW, before the (slower) OCR
        prov: dict[int, Entry] = {}
        for ti, (e, box, _sg) in enumerate(todo):
            if e is None and not textbox:                # box-less text: cover only once it is read
                slot = self._free_slot()
                if slot is not None:
                    pe = Entry(box, slot, last_seen=now)
                    self.entries.append(pe)
                    prov[ti] = pe
                    changed = True
        if changed:
            self._emit()
            changed = False

        reads = []
        for ti, (e, box, sig) in enumerate(todo):
            lines = self._read(rgb, box, ocr, opts, min_conf, lang, textbox)
            if not lines and ti in prov:                 # nothing readable after all
                self.entries.remove(prov.pop(ti))
                changed = True
                continue
            if not lines and e is not None and id(e) not in used:
                used.add(id(e))                          # unreadable this frame: the box stays covered
                e.last_seen = now
                continue
            if lines and not textbox and (self.color is None or self._relearn is not None):
                self.color = color          # learn the box colour only from a box that held a subtitle
                self._save_color(color)     # …and remember it: next start covers from the first frame
                self._relearn = None
            if lines:
                reads.append((e, box, sig, lines, " ".join(f"{sp}: {t}" if sp else t for sp, t in lines), ti))
        # a box pushed up by a new speaker carries its text along: it gets its old entry back first,
        # before the new box below claims that entry by position (no duplicate text, no swap)
        claimed: dict[int, Entry] = {}
        for i, r in enumerate(reads):
            for x in self.entries:
                if x.en and x not in prov.values() and id(x) not in used and all(c is not x for c in claimed.values()) \
                        and similarity(r[4], x.en) >= 0.85:
                    claimed[i] = x
                    break
        for i, (e, box, sig, lines, text, ti) in enumerate(reads):
            if i in claimed:
                e = claimed[i]
                if ti in prov:                          # the provisional cover is not needed
                    self.entries.remove(prov.pop(ti))
            elif e is not None and (id(e) in used or any(c is e for c in claimed.values())):
                e = None                                # its entry moved away with its own text
            if e is None and ti in prov:
                e = prov.pop(ti)
            if e is None:
                slot = self._free_slot()
                if slot is None:
                    continue
                e = Entry(box, slot)
                self.entries.append(e)
                changed = True                          # empty box at once: the original never flashes up
            used.add(id(e))
            if e.rect != box:
                changed = True
            e.last_seen = now
            e.rect, e.sig, e.last_ocr = box, sig, now
            ne, no = normalise_for_compare(text), normalise_for_compare(e.en)
            grew = e.en and len(ne) > len(no) + 2 and ne.startswith(no[: max(4, len(no) - 3)])
            if e.en and not grew and (ne in no or similarity(text, e.en) >= 0.85):
                continue                            # OCR noise / partial read: keep the old one
            x0, y0, x1, y1 = box
            from .engine import name_color
            crop = rgb[y0:y1, x0:x1]
            if len(lines) == 1 and len(text) > 12:
                self.line_hs = (self.line_hs + [y1 - y0])[-15:]
            e.en, e.lines, e.shown_at = text, lines, time.time()
            e.name_rgb = name_color(crop)
            one = float(np.percentile(self.line_hs, 25)) if self.line_hs else None
            e.px = self._steady_px(self._px(y1 - y0, one))
            e.gen += 1
            e.hu = []                               # the old translation must not sit on the new text
            changed = True
            ctx = list(self.ctx[-3:])
            self.ctx = (self.ctx + [t for _, t in lines])[-6:]
            e.requested = e.gen
            self.pool.submit(self._translate_entry, e, e.gen, lines, ctx)

        keep = []
        active_entries = [x for x in self.entries if id(x) in used]
        for e in self.entries:
            # an old translation must not cover another box that is on screen now
            if id(e) not in used and any(min(e.rect[3], u.rect[3]) - max(e.rect[1], u.rect[1]) > 0
                                         for u in active_entries):
                e.alive = False
                changed = True
                continue
            if id(e) in used or now - e.last_seen <= HOLD or (e.en and now - e.shown_at <= MIN_SHOW):
                keep.append(e)
            else:
                e.alive = False
                changed = True
        self.entries = keep
        for e in keep:                  # a text without its translation (moved / re-read box): ask again
            if e.en and not e.hu and e.requested != e.gen and e.lines:
                e.requested = e.gen
                self.pool.submit(self._translate_entry, e, e.gen, e.lines, list(self.ctx[-3:]))
        if changed:
            self._emit()

    def _stat_tick(self):
        """Every 30 s one line in subbridge.log: lets us see from a user's log where the overlay stops."""
        self.stats["ticks"] += 1
        if time.time() - self._stat_t0 >= 30:
            g = self._geo
            log.info("overlay: %s color=%s geo=%s entries=%d", dict(self.stats),
                     None if self.color is None else [int(v) for v in self.color], g[:4], len(self.entries))
            self.stats = dict.fromkeys(self.stats, 0)
            self._stat_t0 = time.time()

    def clear(self):
        if self.entries:
            self.entries = []
            self._emit()

    # ------------------------------------------------------------------ box colour memory
    def _color_file(self):
        from .paths import config_dir
        return config_dir() / "box_colors.json"

    def _load_color(self):
        import json
        try:
            d = json.loads(self._color_file().read_text())
            c = d.get(self.eng.profile.name)
            return np.array(c, dtype=np.int16) if c else None
        except (OSError, ValueError, AttributeError):
            return None

    def _save_color(self, color):
        import json
        try:
            f = self._color_file()
            d = json.loads(f.read_text()) if f.exists() else {}
            d[self.eng.profile.name] = [int(v) for v in color]
            f.write_text(json.dumps(d))
        except (OSError, ValueError):
            pass

    # ------------------------------------------------------------------ helpers
    def _match(self, box, used):
        best, best_ov = None, 0
        for e in self.entries:
            if id(e) in used:
                continue
            ov = min(box[3], e.rect[3]) - max(box[1], e.rect[1])
            h = min(box[3] - box[1], e.rect[3] - e.rect[1])
            if h > 0 and ov / h > 0.5 and ov > best_ov:
                best, best_ov = e, ov
        return best

    def _free_slot(self):
        taken = {e.slot for e in self.entries}
        return next((i for i in range(MAX_BOXES) if i not in taken), None)

    @staticmethod
    def _read(rgb, box, ocr, opts, min_conf, lang, textbox=False):
        if textbox:                                   # no box behind the text: plain text binarisation
            x0, y0, x1, y1 = box
            im = binarize(rgb[y0:y1, x0:x1], opts)
        else:
            im = prepare_boxes(rgb, [box], opts)[0]
        text = clean(" ".join(ln.text for ln in ocr.recognize(im) if ln.confidence >= min_conf))
        out = []
        for ln in split_lines(text, True, lang):
            # text inside a subtitle box is a subtitle: cover it even if it is only names ("Chester!");
            # the dialogue filter is for box-less HUD text
            if is_dialogue(ln, lang) or (has_real_text(ln.text, 3) and (ln.speaker or len(ln.text) >= 6)):
                out.append((ln.speaker, ln.text))
        return out

    # ------------------------------------------------------------------ translation (pool thread)
    def _translate_entry(self, e: Entry, gen: int, lines, ctx):
        from .translate.textprep import textprep
        tp = textprep()

        def show(hu_lines):
            hu_lines = [(tp.speaker(sp, tgt), t) for sp, t in hu_lines]     # "Hoodlum" -> "Huligán"
            if e.gen != gen or not e.alive or hu_lines == e.hu:
                return
            e.hu = hu_lines
            self._emit()

        eng = self.eng
        p = eng.profile
        src, tgt = p.source_lang, p.target_lang
        primary = eng._primary()
        from .translate.glossary import Glossary
        glossary = Glossary.from_list(p.glossary)
        # 1) memory
        if primary is not None:
            hit = [eng.cache.get(primary.id, src, tgt, tp.prep(t, src)) for _, t in lines]
            if all(h is not None for h in hit):
                show([(sp, tp.post_fix(h, tgt)) for (sp, _), h in zip(lines, hit)])
                return
        if primary is None:
            show([(sp, eng.translate(t, ctx)[0]) for sp, t in lines])
            return
        # 2) online engine gets a short head start, offline shows meanwhile, online replaces it
        t0 = time.time()
        futs = [eng._net.submit(eng._translate_text, primary, t, src, tgt, glossary, ctx) for _, t in lines]
        try:
            show([(sp, f.result(timeout=max(0.05, ONLINE_WAIT - (time.time() - t0))))
                  for (sp, _), f in zip(lines, futs)])
            return
        except FutTimeout:
            pass
        except Exception:  # noqa: BLE001
            pass
        if e.gen == gen and eng._argos.has_pair(src, tgt):
            try:
                if all(f.done() and not f.exception() for f in futs):
                    show([(sp, f.result()) for (sp, _), f in zip(lines, futs)])
                    return
                show([(sp, eng._translate_text(eng._argos, t, src, tgt, glossary, ctx)) for sp, t in lines])
                return                        # what is on screen stays (no swapping); the cache gets the
            except Exception:  # noqa: BLE001  # online result for the next time
                pass
        try:
            show([(sp, f.result(timeout=4)) for (sp, _), f in zip(lines, futs)])
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------ output
    def _steady_px(self, px: int) -> int:
        """The game uses one subtitle size: a box measured badly (cut off, two lines read as one) must not
        give giant or tiny text. Keep within ±20 % of the recent median."""
        hist = self.px_hist
        if len(hist) >= 3:
            med = float(np.median(hist))
            px = int(min(max(px, med * 0.8), med * 1.2))
        self.px_hist = (hist + [px])[-12:]
        return px

    @staticmethod
    def _px(box_h: int, one_line_h: float | None) -> int:
        line_h = one_line_h or 62.0
        lines = max(1, round(box_h / line_h))
        font = max(16, box_h / lines * 0.64)
        return int(font / 1.08)                 # the overlay scales by 1.08

    def _emit(self):
        gx, gy, region_w, source_w = self._geo
        # font like the game's: one text line ≈ 0.55 of a one-line box (the old translator's rule)
        one = float(np.percentile(self.line_hs, 25)) if self.line_hs else None   # wrapped 2-line boxes are taller
        out = []
        for e in self.entries:
            if not e.alive:
                continue
            x0, y0, x1, y1 = e.rect
            out.append({"slot": e.slot, "rect": (gx + x0, gy + y0, gx + x1, gy + y1),
                        "bg": tuple(int(v) for v in self.color) if self.color is not None else (24, 24, 30),
                        "name": e.name_rgb, "px": e.px or self._px(y1 - y0, one),
                        "lines": [(sp, t) for sp, t in e.hu] or [(None, "")],
                        # the game wraps long subtitles: about half the picture width at most
                        "max_w": int(source_w * 0.5 / 0.62)})
        self.stats["emits"] += 1
        self.emit_cb(out)


