"""Format choice for a typical 4K HDMI→USB capture adapter (4K30 / 1440p60 / 1080p120 MJPEG + raw YUV)."""
from subbridge.capture.device import _best_format, format_key, usb2_limited


class _Size:
    def __init__(self, w, h):
        self.w, self.h = w, h

    def width(self):
        return self.w

    def height(self):
        return self.h


class _Pix:
    def __init__(self, name):
        self.name = name


class _Fmt:
    def __init__(self, w, h, fps, pix):
        self._r, self._fps, self._p = _Size(w, h), fps, _Pix(pix)

    def resolution(self):
        return self._r

    def maxFrameRate(self):
        return self._fps

    def pixelFormat(self):
        return self._p


class _Dev:
    def __init__(self, fmts):
        self.f = fmts

    def videoFormats(self):
        return self.f


CARD = _Dev([_Fmt(3840, 2160, 30, "Format_Jpeg"), _Fmt(2560, 1440, 60, "Format_Jpeg"),
             _Fmt(1920, 1080, 120, "Format_Jpeg"), _Fmt(1920, 1080, 60, "Format_Jpeg"),
             _Fmt(1920, 1080, 60, "Format_NV12"), _Fmt(1280, 720, 60, "Format_YUYV"), _Fmt(2, 1, 1000, "Format_BGRX8888")])


def test_prefers_1440p60():
    assert format_key(_best_format(CARD)) == "2560x1440@60:Jpeg"
    assert format_key(_best_format(CARD, low_latency=False)) == "2560x1440@60:Jpeg"


def test_without_1440p60_takes_1080p60_raw():
    no1440 = _Dev([f for f in CARD.f if f.resolution().height() != 1440] + [_Fmt(2560, 1440, 30, "Format_Jpeg")])
    assert format_key(_best_format(no1440)) == "1920x1080@60:NV12"


def test_manual_choice_wins():
    assert format_key(_best_format(CARD, "3840x2160@30:Jpeg")) == "3840x2160@30:Jpeg"


def test_usb2_detection():
    assert not usb2_limited(CARD)
    assert usb2_limited(_Dev([_Fmt(1280, 720, 30, "Format_Jpeg"), _Fmt(640, 480, 30, "Format_YUYV")]))


def test_picture_range():
    import numpy as np
    from subbridge.capture.device import picture_range
    rng = np.random.default_rng(1)
    limited = rng.integers(16, 236, 5000)
    full = rng.integers(0, 256, 5000)
    assert picture_range(limited) == "limited"
    assert picture_range(full) == "ok"
    assert picture_range(np.full(5000, 20)) == ""          # flat (black screen / menu): can't tell


def test_stall_restart_backoff(monkeypatch):
    import subbridge.capture.device as d
    s = d.DeviceSession.__new__(d.DeviceSession)

    class Cam:
        n = 0

        def stop(self):
            pass

        def start(self):
            Cam.n += 1
    s.camera, s.error, s._last_sig = Cam(), "", None
    t = [1000.0]
    monkeypatch.setattr(d.time, "time", lambda: t[0])
    s._opened, s._last_frame, s._restarts, s._restart_t = 1000.0, 0.0, 0, 0.0
    assert not s.stalled()
    t[0] = 1005.0
    assert s.stalled() and s.restart() and Cam.n == 1
    assert not s.stalled()                    # gives the restarted stream time
    for _ in range(2):
        t[0] += 4.5
        assert s.stalled() and s.restart()
    t[0] += 4.5
    assert s.stalled() and not s.restart()    # backs off after 3 tries (console switched off)
    t[0] += 20
    assert s.restart() and Cam.n == 4
