import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from subbridge.capture.base import CaptureSource, WindowInfo
from subbridge.config import AppSettings, Profile
from subbridge.engine import Callbacks, Engine
from subbridge.paths import resource_dir


def _frame():
    img = Image.new("RGB", (1920, 1080), (70, 90, 70))
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(str(resource_dir() / "assets" / "fonts" / "InterVariable.ttf"), 30)
    d.rectangle((40, 40, 640, 170), fill=(18, 18, 22))
    d.text((64, 62), "Press the button to open the map.", font=font, fill=(240, 240, 240))
    d.text((64, 110), "You can set a waypoint there.", font=font, fill=(240, 240, 240))
    return np.asarray(img)


class Fake(CaptureSource):
    def __init__(self):
        self.f = _frame()

    def list_windows(self):
        return [WindowInfo(7, "game")]

    def source_size(self, kind, ident):
        return 1920, 1080

    def origin(self, kind, ident):
        return 0, 0

    def grab(self, kind, ident, rect=None):
        if rect:
            x, y, w, h = rect
            return self.f[y:y + h, x:x + w]
        return self.f


def test_help_zone_is_read_once_and_covered(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    st = AppSettings()
    p = Profile(name="t", source_kind="window", window_title="game", region=[0.3, 0.8, 0.4, 0.15],
                engine="argos", game_phone=False,
                zones=[{"name": "", "kind": "help", "region": [0.0, 0.0, 0.4, 0.25], "on": True}])
    st.profiles = [p.__dict__]
    st.active_profile = "t"
    subs, ovs = [], []
    eng = Engine(st, Fake(), Callbacks(subtitle=subs.append, overlay=ovs.append))
    eng.start(7)
    t0 = time.time()
    while time.time() - t0 < 20:         # first translation loads the offline model (slow under load)
        time.sleep(0.25)
        if any(m.get("type") == "line" and m.get("zone") for m in subs) and any(ovs):
            time.sleep(1.0)              # … and it must stay one line, not repeat
            break
    eng.shutdown()
    zone = [m for m in subs if m.get("type") == "line" and m.get("zone")]
    assert len(zone) == 1, subs
    assert "open the map" in zone[0]["original"] and "waypoint" in zone[0]["original"]
    covered = [b for o in ovs for b in o]
    assert covered and covered[0]["rect"][0] <= 50 and covered[0]["rect"][2] >= 600
