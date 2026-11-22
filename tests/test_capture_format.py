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


def test_prefers_1080p60_raw():
    f = _best_format(CARD)
    assert format_key(f) == "1920x1080@60:NV12"


def test_manual_choice_wins():
    assert format_key(_best_format(CARD, "3840x2160@30:Jpeg")) == "3840x2160@30:Jpeg"


def test_usb2_detection():
    assert not usb2_limited(CARD)
    assert usb2_limited(_Dev([_Fmt(1280, 720, 30, "Format_Jpeg"), _Fmt(640, 480, 30, "Format_YUYV")]))
