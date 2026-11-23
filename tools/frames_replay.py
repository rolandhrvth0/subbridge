"""Replay recorded window frames (build/recN/*_eredeti.jpg, LOCAL ONLY) through the real overlay:
each frame stays on 'screen' for STEP seconds. Reports per frame whether a translation covered it.
  python tools/frames_replay.py 'build/rec9/*_eredeti.jpg' [step]"""
import glob, json, os, sys, tempfile, time
from pathlib import Path
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="sb-fr-")
sys.path.insert(0, str(Path.cwd()))
import numpy as np
from PIL import Image
from subbridge.capture.base import CaptureSource, WindowInfo
from subbridge.config import AppSettings, Profile
from subbridge.engine import Callbacks, Engine
files = sorted(glob.glob(sys.argv[1]))
STEP = float(sys.argv[2]) if len(sys.argv) > 2 else 1.2
frames = [np.asarray(Image.open(f).convert("RGB")) for f in files]
H, W = frames[0].shape[:2]
class Fake(CaptureSource):
    t0 = None
    def list_windows(self): return [WindowInfo(7, "game")]
    def source_size(self, k, i): return W, H
    def origin(self, k, i): return (0, 0)
    def is_foreground(self, k, i): return True
    def grab(self, k, i, rect=None):
        if self.t0 is None: self.t0 = time.time()
        f = frames[min(int((time.time() - self.t0) / STEP), len(frames) - 1)]
        if rect:
            x, y, w, h = rect
            f = f[y:y + h, x:x + w]
        return f
st = AppSettings(); st.online_feed = False
st.profiles = [Profile(name="t", source_kind="window", window_title="game", region=[0.1, 0.70, 0.8, 0.27], engine="argos", game_phone=False).__dict__]
st.active_profile = "t"
cap = Fake(); log = []
def ov(boxes):
    if cap.t0: log.append((time.time() - cap.t0, [" / ".join(t for _s, t in b["lines"]) for b in boxes]))
eng = Engine(st, cap, Callbacks(overlay=ov))
eng.start(7); time.sleep(len(frames) * STEP + 1.0); eng.shutdown()
covered = 0; empties = 0; changes = 0; last = None
for i in range(len(frames)):
    t_end = (i + 1) * STEP - 0.05
    state = [b for t, b in log if t <= t_end]
    cur = state[-1] if state else []
    if any(x.strip() for x in cur): covered += 1
    in_frame = [b for t, b in log if i * STEP <= t < (i + 1) * STEP]
    empties += sum(1 for b in in_frame for x in b if not x.strip())
for t, b in log:
    if b != last: changes += 1; last = b
print(json.dumps({"frames": len(frames), "covered_at_end": covered, "empty_box_emits": empties, "changes": changes}))
