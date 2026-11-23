"""Frame generation modes: detection/resolution and the repeated-frame filter."""
import sys

import numpy as np

from subbridge import fgmodes
from subbridge.config import Profile


def test_resolve_falls_back():
    fi = fgmodes.FgInfo(fgmodes.Gpu("intel"), "", "", "")
    assert fi.resolve("auto") == "off"
    assert fi.resolve("lsfg") == "off"              # not installed here
    assert fi.resolve("builtin") == "builtin"
    assert "builtin" in fi.choices() and "off" in fi.choices()


def test_resolve_prefers_vendor_tech(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    assert fgmodes.FgInfo(fgmodes.Gpu("amd")).resolve("auto") == "afmf"
    assert fgmodes.FgInfo(fgmodes.Gpu("nvidia")).resolve("auto") == "smooth"
    monkeypatch.setattr(sys, "platform", "linux")
    fi = fgmodes.FgInfo(fgmodes.Gpu("amd"), "/x/layer.json", "/x/Lossless.dll")
    assert fi.resolve("auto") == "lsfg" and fi.resolve("afmf") == "lsfg"


def test_old_bool_setting_migrates():
    assert Profile.from_dict({"framegen": True}).framegen == "auto"
    assert Profile.from_dict({"framegen": False}).framegen == "off"
    assert Profile.from_dict({}).framegen == "auto"


def test_enable_lsfg_writes_own_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("VK_INSTANCE_LAYERS", raising=False)
    (tmp_path / "layer.json").write_text("{}")
    fi = fgmodes.FgInfo(fgmodes.Gpu("amd"), str(tmp_path / "layer.json"), "/games/Lossless.dll", "My GPU")
    assert fgmodes.enable_lsfg(fi)
    import os
    conf = open(os.environ["LSFGVK_CONFIG"]).read()
    assert "dll = '/games/Lossless.dll'" in conf and "gpu = 'My GPU'" in conf and "multiplier = 2" in conf
    assert fgmodes.LSFG_LAYER in os.environ["VK_INSTANCE_LAYERS"]


def test_repeated_frames_are_dropped(qapp_offscreen):
    from PySide6.QtGui import QImage
    from PySide6.QtMultimedia import QVideoFrame
    from subbridge.capture.device import DeviceSession
    rng = np.random.default_rng(0)
    a = (rng.random((360, 640, 4)) * 255).astype(np.uint8)
    b = np.roll(a, 9, axis=1)
    fr = lambda x: QVideoFrame(QImage(x.data, 640, 360, 640 * 4, QImage.Format_RGB32).copy())   # noqa: E731
    s = DeviceSession.__new__(DeviceSession)
    s._last_sig = None
    assert not s._is_repeat(fr(a))
    assert s._is_repeat(fr(a))             # the card's second copy of the same game picture
    assert not s._is_repeat(fr(b))         # a new picture
