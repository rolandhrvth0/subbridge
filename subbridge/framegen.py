"""Frame generation for the Game View (capture card): turns a 30 fps game into smooth 60 fps.

A capture card delivers 60 Hz; a 30 fps console game sends every picture twice (A A B B C C …).
When a NEW picture arrives we show the in-between picture mid(A, B) first, and the real B on the
next (duplicate) slot: A, A½B, B, B½C, C … – one 60 Hz slot (~17 ms) of extra delay, no timers.
Sources that really deliver 30 Hz get the same treatment with a half-interval timer in the view.

Motion: dense optical flow (OpenCV DIS) on a quarter-size grey picture, both directions; each frame
is warped half-way toward the other and the two are blended, preferring the one whose warp agrees
(occlusions). Text overlays are drawn by SubBridge afterwards, so they never smear."""
from __future__ import annotations

import time

import numpy as np

try:
    import cv2
except Exception:  # noqa: BLE001
    cv2 = None


def available() -> bool:
    return cv2 is not None and hasattr(cv2, "DISOpticalFlow_create")


class Interpolator:
    """mid(a, b) for HxWx3 uint8 frames. Not thread-safe; use from one worker thread."""

    def __init__(self, scale: int = 4):
        self.scale = scale
        self.dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_ULTRAFAST)
        self.dis.setUseSpatialPropagation(True)
        self._grid = None
        self._small = None
        self.last_ms = 0.0

    def _prep(self, shape):
        h, w = shape[:2]
        if self._grid is None or self._grid[0] != (h, w):
            sw, sh = max(16, w // self.scale), max(16, h // self.scale)
            base = np.dstack(np.meshgrid(np.arange(sw, dtype=np.float32), np.arange(sh, dtype=np.float32)))
            self._grid = ((h, w), base)
            self._small = (sw, sh)

    def _grey(self, f):
        return cv2.cvtColor(cv2.resize(f, self._small, interpolation=cv2.INTER_AREA), cv2.COLOR_RGB2GRAY)

    def _map(self, flow, w, h):
        """Full-size backward map x - ½·F(x), built on the small grid and scaled up in one go (the
        linear resize keeps it exact for a smooth flow; ~4× cheaper than full-size arithmetic)."""
        base = self._grid[1]
        kx, ky = w / self._small[0], h / self._small[1]
        m = base - 0.5 * flow
        m[..., 0] = m[..., 0] * kx + (kx - 1) / 2
        m[..., 1] = m[..., 1] * ky + (ky - 1) / 2
        return cv2.resize(m, (w, h), interpolation=cv2.INTER_LINEAR)

    def mid(self, a: np.ndarray, b: np.ndarray, ga=None, gb=None) -> np.ndarray:
        t0 = time.perf_counter()
        self._prep(a.shape)
        h, w = a.shape[:2]
        ga = self._grey(a) if ga is None else ga
        gb = self._grey(b) if gb is None else gb
        fab = self.dis.calc(ga, gb, None)            # where each a-pixel goes in b (small pixels)
        fba = self.dis.calc(gb, ga, None)
        # backward warp: mid(x) ~ a(x - ½·F_ab(x)) ~ b(x - ½·F_ba(x))
        wa = cv2.remap(a, self._map(fab, w, h), None, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        wb = cv2.remap(b, self._map(fba, w, h), None, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        out = cv2.addWeighted(wa, 0.5, wb, 0.5, 0)
        self.last_ms = (time.perf_counter() - t0) * 1000
        return out


def is_duplicate(ga: np.ndarray, gb: np.ndarray) -> bool:
    """Same game picture sent twice (capture noise and compression allowed)."""
    d = cv2.absdiff(ga, gb)
    return float(d.mean()) < 0.6 and int(np.percentile(d, 99.5)) < 14


class FrameGen:
    """Feed every captured frame with push(); returns the frames to show now: [] (drop),
    [frame] (show), or [mid, real] (show mid now, real half an interval later – 30 Hz sources)."""

    def __init__(self):
        self.ip = Interpolator()
        self.prev = None           # last unique real frame (rgb, grey)
        self.pending = None        # real frame waiting for its duplicate slot
        self.mode = "auto"         # becomes "dup" (60 Hz with repeats) or "30" (true 30 Hz) or "pass"
        self._t_last = 0.0
        self._intervals: list[float] = []
        self._dups = 0
        self._uniq = 0
        self.stats = {"generated": 0, "passed": 0, "ms": 0.0}

    def _learn(self, dup: bool, now: float):
        if self._t_last:
            self._intervals = (self._intervals + [now - self._t_last])[-30:]
        self._t_last = now
        self._dups += dup
        self._uniq += not dup
        n = self._dups + self._uniq
        if n >= 40:
            med = float(np.median(self._intervals)) if self._intervals else 0.016
            if med > 0.026:
                self.mode = "30"                               # the card itself delivers ~30 Hz
            elif self._dups / n > 0.3:
                self.mode = "dup"                              # 60 Hz with a 30 fps game inside
            else:
                self.mode = "pass"                             # really 60 fps: nothing to add
            self._dups = self._uniq = 0

    def push(self, rgb: np.ndarray) -> list[np.ndarray]:
        now = time.perf_counter()
        self.ip._prep(rgb.shape)
        g = self.ip._grey(rgb)
        if self.prev is None or self.prev[0].shape != rgb.shape:
            self.prev = (rgb, g)
            return [rgb]
        dup = is_duplicate(self.prev[1], g)
        self._learn(dup, now)
        if self.mode == "pass":
            self.prev = (rgb, g)
            self.stats["passed"] += 1
            return [rgb]
        if dup:
            if self.pending is not None:                       # duplicate slot: now the real frame
                out, self.pending = self.pending, None
                return [out]
            return []                                          # nothing new to show
        mid = self.ip.mid(self.prev[0], rgb, self.prev[1], g)
        self.stats["generated"] += 1
        self.stats["ms"] = 0.9 * self.stats["ms"] + 0.1 * self.ip.last_ms
        self.prev = (rgb, g)
        if self.mode == "30":
            return [mid, rgb]
        if self.mode == "dup":
            self.pending = rgb
            return [mid]
        # still learning: show the real frame (no added delay yet)
        return [rgb]
