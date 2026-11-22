"""Replay a recorded video through the real engine + overlay in real time and measure how calm the
on-screen translation is (LOCAL ONLY – game footage).

  python tools/overlay_replay.py build/corpus/v1.mp4 --start 2040 --len 80 [--fps 15] [--out build/replay/x]

Prints the timeline of what the overlay shows and a summary:
  shown      distinct translated texts that appeared
  flashes    texts visible for < 1.0 s (the "constantly changing" effect)
  rewrites   a box's text replaced while the same subtitle was still on screen
  max_boxes  most boxes on screen at once
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


Y0 = 0.68                    # only the bottom band is kept in memory (every grab falls inside it)


def load(path, start, length, fps, w=1920, h=1080):
    y0 = int(h * Y0)
    bh = h - y0
    cmd = ["ffmpeg", "-loglevel", "error", "-ss", str(start), "-t", str(length), "-i", path,
           "-vf", f"fps={fps},scale={w}:{h},crop={w}:{bh}:0:{y0}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    n = len(raw) // (w * bh * 3)
    return np.frombuffer(raw[: n * w * bh * 3], np.uint8).reshape(n, bh, w, 3), y0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--start", type=float, default=0)
    ap.add_argument("--len", type=float, default=60)
    ap.add_argument("--fps", type=float, default=15)
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    import os
    import tempfile
    os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="sb-replay-")   # never the real settings
    frames, Y = load(a.video, a.start, a.len, a.fps)
    W, H = frames.shape[2], 1080
    from subbridge.capture.base import CaptureSource, WindowInfo
    from subbridge.config import AppSettings, Profile
    from subbridge.engine import Callbacks, Engine

    class Fake(CaptureSource):
        t0 = None

        def list_windows(self):
            return [WindowInfo(7, "game")]

        def source_size(self, k, i):
            return W, H

        def origin(self, k, i):
            return (0, 0)

        def is_foreground(self, k, i):
            return True

        def grab(self, k, i, rect=None):
            if self.t0 is None:
                self.t0 = time.time()
            f = frames[min(int((time.time() - self.t0) * a.fps), len(frames) - 1)]
            x, y, w, h = rect or (0, 0, W, H)
            if y < Y:
                raise AssertionError(f"grab above the kept band: {rect}")
            return f[y - Y:y - Y + h, x:x + w]

    st = AppSettings()
    st.online_feed = False
    st.profiles = [Profile(name="t", source_kind="window", window_title="game", region=[0.1, 0.70, 0.8, 0.27],
                           engine="argos", game_phone=False).__dict__]
    st.active_profile = "t"
    cap = Fake()
    log = []

    def ov(boxes):
        if cap.t0:
            log.append((time.time() - cap.t0, [(b.get("slot"), tuple(b["rect"]),
                                                " / ".join(f"{s}: {t}" if s else t for s, t in b["lines"]))
                                               for b in boxes]))
    eng = Engine(st, cap, Callbacks(overlay=ov))
    eng.start(7)
    time.sleep(len(frames) / a.fps + 1.0)
    eng.shutdown()

    # timeline + metrics
    last, vis = None, {}
    spans = []                      # (text, t_on, t_off)
    max_boxes = 0
    for t, bx in log:
        texts = {txt for _sl, _r, txt in bx if txt.strip()}
        max_boxes = max(max_boxes, len(texts))
        for txt in texts - set(vis):
            vis[txt] = t
        for txt in set(vis) - texts:
            spans.append((txt, vis.pop(txt), t))
        s = " | ".join(f"[{sl}] y{r[1]} {txt[:70]}" for sl, r, txt in sorted(bx, key=lambda b: b[1][1]))
        if s != last:
            print(f"{a.start + t:7.2f}  {s or '-'}")
            last = s
    end = log[-1][0] if log else 0
    spans += [(txt, t0, end) for txt, t0 in vis.items()]
    flashes = [s for s in spans if s[2] - s[1] < 1.0]
    summary = {"shown": len(spans), "flashes": len(flashes), "max_boxes": max_boxes,
               "emits": len(log), "seconds": round(len(frames) / a.fps, 1)}
    print(json.dumps(summary))
    for f in flashes[:15]:
        print(f"   flash {f[2] - f[1]:.2f}s  {f[0][:80]}")
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out + ".json").write_text(json.dumps({"summary": summary, "spans": spans}, ensure_ascii=False))


if __name__ == "__main__":
    main()
