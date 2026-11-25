"""Capture-card frames must be converted on the CPU: QVideoFrame.toImage() opens a GL context and Qt
aborts the whole app when that fails (1.2.0 crash with a real JVA11 card)."""
import numpy as np
from PySide6.QtCore import QSize
from PySide6.QtMultimedia import QVideoFrame, QVideoFrameFormat

from subbridge.capture import device

PF = QVideoFrameFormat.PixelFormat


def _frame(pf, planes):
    f = QVideoFrame(QVideoFrameFormat(QSize(64, 32), pf))
    assert f.map(QVideoFrame.MapMode.WriteOnly)
    for i, data in enumerate(planes):
        bpl = f.bytesPerLine(i)
        buf = np.frombuffer(f.bits(i), np.uint8, count=bpl * data.shape[0]).reshape(data.shape[0], bpl)
        buf[:, : data.shape[1]] = data
    f.unmap()
    return f


def _no_toimage(monkeypatch):
    def boom(self):
        raise AssertionError("toImage() must not be used for card formats")
    monkeypatch.setattr(QVideoFrame, "toImage", boom)


def test_nv12_grey_cpu(qapp_offscreen, monkeypatch):
    _no_toimage(monkeypatch)
    y = np.full((32, 64), 126, np.uint8)
    uv = np.full((16, 64), 128, np.uint8)
    rgb = device.frame_to_rgb(_frame(PF.Format_NV12, [y, uv]))
    assert rgb.shape == (32, 64, 3)
    assert abs(int(rgb[..., 0].mean()) - int(rgb[..., 2].mean())) <= 2
    img = device.frame_to_qimage(_frame(PF.Format_NV12, [y, uv]))
    assert img.width() == 64 and img.height() == 32


def test_yuyv_and_packed_cpu(qapp_offscreen, monkeypatch):
    _no_toimage(monkeypatch)
    yuyv = np.tile(np.array([200, 128], np.uint8), (32, 64))
    assert device.frame_to_rgb(_frame(PF.Format_YUYV, [yuyv])).mean() > 150
    px = np.zeros((32, 64, 4), np.uint8)
    px[..., 2] = 255  # memory B,G,R,X -> red
    rgb = device.frame_to_rgb(_frame(PF.Format_XBGR8888, [px.reshape(32, 256)]))
    assert rgb[..., 0].mean() == 255 and rgb[..., 2].mean() == 0


def test_close_releases_camera(qapp_offscreen):
    """Saving settings reopens the card: the old QCamera must be detached, or the new one stays black."""
    from types import SimpleNamespace
    calls = []
    cam = SimpleNamespace(stop=lambda: calls.append("stop"), deleteLater=lambda: calls.append("del"))
    sess_calls = []
    capsess = SimpleNamespace(setAudioOutput=lambda x: None, setAudioInput=lambda x: None,
                              setVideoSink=lambda x: sess_calls.append(("sink", x)),
                              setCamera=lambda x: sess_calls.append(("cam", x)))
    s = device.DeviceSession.__new__(device.DeviceSession)
    s.camera, s.session, s._ll_audio, s._extra_sink = cam, capsess, None, None
    s.sink = SimpleNamespace(videoFrameChanged=SimpleNamespace(disconnect=lambda f: None))
    s._on_frame = lambda f: None
    device.DeviceSession.close(s)
    assert ("cam", None) in sess_calls and "del" in calls and s.camera is None
    device.DeviceSession.close(s)  # second close is a no-op


def test_pipewire_loopback_cmd(monkeypatch):
    import subprocess
    from types import SimpleNamespace
    seen = {}

    class P:
        def __init__(self, cmd, **kw):
            seen["cmd"], seen["env"] = cmd, kw.get("env")
        def poll(self):
            return None
        def terminate(self):
            seen["term"] = True
        def wait(self, t):
            return 0
    monkeypatch.setattr(subprocess, "Popen", P)
    dev = SimpleNamespace(id=lambda: b"alsa_input.card")
    out = SimpleNamespace(id=lambda: b"alsa_output.phones")
    lb = device.PipeWireLoopback(dev, out)
    assert lb.start()
    cmd = " ".join(seen["cmd"])
    assert "target.object=alsa_input.card" in cmd and "target.object=alsa_output.phones" in cmd
    lb.stop()
    assert seen.get("term")
