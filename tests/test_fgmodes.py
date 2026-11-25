"""Frame generation modes: detection/resolution and the repeated-frame filter."""
import sys

import numpy as np

from subbridge import fgmodes
from subbridge.config import Profile


def test_resolve_falls_back():
    fi = fgmodes.FgInfo(fgmodes.Gpu("intel"), "", "", "")
    assert fi.resolve("auto") == "off"
    assert fi.resolve("lsfg") == "off"              # not installed here
    assert fi.resolve("builtin") != "builtin"          # removed in 1.2.3
    assert "builtin" not in fi.choices() and "off" in fi.choices()


def test_resolve_prefers_vendor_tech(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    assert fgmodes.FgInfo(fgmodes.Gpu("amd")).resolve("auto") == "afmf"
    assert fgmodes.FgInfo(fgmodes.Gpu("nvidia")).resolve("auto") == "smooth"
    monkeypatch.setattr(sys, "platform", "linux")
    dev = fgmodes.FgInfo(fgmodes.Gpu("amd"), "/x/lsfg-vk2/layer.json", "/x/Lossless.dll")
    assert dev.resolve("auto") == "off"             # old dev builds do not start in Qt Quick: opt-in only
    assert dev.resolve("lsfg") == "lsfg" and dev.resolve("afmf") == "off"
    rel = fgmodes.FgInfo(fgmodes.Gpu("amd"), "/o/lsfg-vk-2.0.0/share/vulkan/implicit_layer.d/l.json", "/s/lsfg-vk.dll")
    assert rel.resolve("auto") == "lsfg"            # 2.0 release + its DLL: automatic


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
    rel_dir = tmp_path / "share" / "vulkan" / "implicit_layer.d"
    rel_dir.mkdir(parents=True)
    (rel_dir / "l.json").write_text("{}")
    assert fgmodes.enable_lsfg(fgmodes.FgInfo(fgmodes.Gpu("amd"), str(rel_dir / "l.json"), "/s/lsfg-vk.dll", "My GPU"))
    conf = open(os.environ["LSFGVK_CONFIG"]).read()
    assert "version = 2" in conf and "gpu" not in conf and "pacing" not in conf     # 2.0 release format
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


def test_builtin_profile_migrates_to_auto():
    from subbridge.config import Profile
    assert Profile.from_dict({"name": "x", "framegen": "builtin"}).framegen == "auto"
