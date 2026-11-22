"""Capture cards and other video devices (UVC: Elgato, generic HDMI→USB dongles, webcams, OBS virtual
camera …) through Qt Multimedia, which uses V4L2 on Linux and Media Foundation on Windows.

The device is opened once and shared: the engine reads the newest frame on demand, and the Game View
window (for cards without HDMI passthrough) shows the same stream with sound."""
from __future__ import annotations

import threading
import time

import numpy as np
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage
from PySide6.QtMultimedia import (QAudioInput, QAudioOutput, QCamera, QCameraFormat, QMediaCaptureSession,
                                  QMediaDevices, QVideoFrame, QVideoSink)

from .base import CaptureError, CaptureSource


def list_devices() -> list[dict]:
    return [{"id": bytes(d.id()).decode(errors="ignore"), "name": d.description()}
            for d in QMediaDevices.videoInputs()]


def list_audio_inputs() -> list[dict]:
    return [{"id": bytes(d.id()).decode(errors="ignore"), "name": d.description()}
            for d in QMediaDevices.audioInputs()]


_UNCOMPRESSED = {"Format_YUYV", "Format_UYVY", "Format_NV12", "Format_NV21", "Format_YUV420P", "Format_P010"}


def usable_formats(dev) -> list[QCameraFormat]:
    # loopback devices advertise 2×1 / 8192² placeholder ranges
    return [f for f in dev.videoFormats() if 160 <= f.resolution().width() <= 7680
            and 120 <= f.resolution().height() <= 4320]


def format_key(f: QCameraFormat) -> str:
    r = f.resolution()
    return f"{r.width()}x{r.height()}@{round(f.maxFrameRate())}:{f.pixelFormat().name.replace('Format_', '')}"


def _best_format(dev, wanted: str = "") -> QCameraFormat | None:
    """Capture cards (e.g. 4K HDMI→USB adapters) offer 4K30 / 1440p60 / 1080p60-120 in MJPEG and often
    a raw YUV mode. Best for subtitles + Game View: 1080p at ~60 fps (sharp enough for OCR, smooth, light
    on USB and CPU); raw YUV beats MJPEG (no decoding delay) when the card offers it at that size."""
    fmts = usable_formats(dev)
    if not fmts:
        return None
    if wanted:
        for f in fmts:
            if format_key(f) == wanted:
                return f

    def score(f):
        r = f.resolution()
        h, fps = r.height(), f.maxFrameRate()
        return (h == 1080,                       # 1080p first
                -abs(h - 1080),                  # otherwise the closest size
                fps >= 50,                       # smooth enough for the Game View
                -abs(min(fps, 120) - 60),        # 60 fps over 120 (half the decode work, same OCR)
                f.pixelFormat().name in _UNCOMPRESSED,
                r.width())
    return max(fmts, key=score)


def usb2_limited(dev) -> bool:
    """A 4K-capable card plugged into a USB 2 port only offers small modes (typically 720p30)."""
    fmts = usable_formats(dev)
    return bool(fmts) and max(f.resolution().height() for f in fmts) <= 720


def frame_to_rgb(frame: QVideoFrame) -> np.ndarray | None:
    if frame is None or not frame.isValid() or frame.width() <= 0 or frame.height() <= 0:
        return None
    img = frame.toImage()
    if img.isNull():
        return None
    img = img.convertToFormat(QImage.Format_RGB888)
    w, h, bpl = img.width(), img.height(), img.bytesPerLine()
    return np.frombuffer(img.constBits(), np.uint8, h * bpl).reshape(h, bpl)[:, : w * 3].reshape(h, w, 3).copy()


def guess_audio(video_name: str):
    """The card's own sound input (UVC cards add a USB audio device with a matching name)."""
    ins = list(QMediaDevices.audioInputs())
    key = video_name.split(":")[0].strip().lower()
    words = [w for w in key.replace("-", " ").split() if len(w) >= 3]
    for d in ins:                                   # same name ("j5create JVA11" / "j5create JVA11 Analog Stereo")
        if key and key in d.description().lower():
            return d
    best, hits = None, 0
    for d in ins:                                   # most shared words ("jva11", "capture", "usb3 video")
        n = sum(w in d.description().lower() for w in words)
        if n > hits:
            best, hits = d, n
    if best is not None:
        return best
    for d in ins:                                   # generic capture-card audio names
        if any(k in d.description().lower() for k in ("capture", "hdmi", "uvc", "video", "cam link", "usb3")):
            return d
    return None


class DeviceSession(QObject):
    """One open device. Lives in the GUI thread (Qt Multimedia objects must)."""
    frame_ready = Signal()

    def __init__(self, device_id: str, audio_id: str = "", play_audio: bool = False, fmt_key: str = ""):
        super().__init__()
        dev = next((d for d in QMediaDevices.videoInputs() if bytes(d.id()).decode(errors="ignore") == device_id), None)
        if dev is None:
            raise CaptureError("Nem találom a kiválasztott videóeszközt. Be van dugva?", "device_gone")
        self.device_id = device_id
        self.name = dev.description()
        self.camera = QCamera(dev)
        fmt = _best_format(dev, fmt_key)
        self.format = format_key(fmt) if fmt is not None else ""
        self.usb2 = usb2_limited(dev)
        self.formats = [format_key(f) for f in usable_formats(dev)]
        self.audio_id = audio_id
        if fmt is not None:
            self.camera.setCameraFormat(fmt)
        self.session = QMediaCaptureSession()
        self.session.setCamera(self.camera)
        self.sink = QVideoSink()
        self.session.setVideoSink(self.sink)
        self._extra_sink = None
        self._fg_cb = None
        self.sink.videoFrameChanged.connect(self._on_frame)
        self._lock = threading.Lock()
        self._img: QImage | None = None
        self._size: tuple[int, int] | None = None
        self._t = 0.0
        self.error = ""
        self.camera.errorOccurred.connect(lambda _e, msg: setattr(self, "error", msg))
        self.audio_in = self.audio_out = None
        self.set_audio(audio_id, play_audio)
        self.camera.start()

    # sound passthrough (for capture cards without HDMI passthrough)
    def set_audio(self, audio_id: str, play: bool):
        if not play:
            self.session.setAudioInput(None)
            self.session.setAudioOutput(None)
            self.audio_in = self.audio_out = None
            return
        dev = next((d for d in QMediaDevices.audioInputs() if bytes(d.id()).decode(errors="ignore") == audio_id), None)
        if dev is None:
            dev = guess_audio(self.name)
        if dev is None:
            return
        self.audio_in = QAudioInput(dev)
        self.audio_out = QAudioOutput()
        self.session.setAudioInput(self.audio_in)
        self.session.setAudioOutput(self.audio_out)

    def attach_view(self, video_item_sink: QVideoSink | None):
        """Mirror frames to a Game View (its QGraphicsVideoItem sink). Only the frame handle is passed on
        (no copy). Rendering straight into the view's sink is not used: those frames can be GPU textures
        that crash when read back for OCR."""
        self._extra_sink = video_item_sink

    def set_frame_callback(self, cb):
        """Frame generation: every frame as an RGB QImage (converted here, while the buffer is valid)."""
        self._fg_cb = cb

    def _on_frame(self, frame: QVideoFrame):
        if not frame.isValid():
            return
        if self._extra_sink is not None:
            self._extra_sink.setVideoFrame(frame)
        now = time.time()
        if self._fg_cb is not None:
            img = frame.toImage()
            if not img.isNull():
                img = img.convertToFormat(QImage.Format_RGB888)
                self._fg_cb(img)
                if now - self._t >= 0.09:
                    with self._lock:
                        self._img, self._t = img, now
                        self._size = (img.width(), img.height())
                self.frame_ready.emit()
                return
        # Convert right here, while the driver buffer is guaranteed valid, at most ~10×/s (OCR needs 4–8):
        # reading a kept QVideoFrame later from another moment/thread can crash on recycled V4L2 buffers.
        if now - self._t >= 0.09:
            img = frame.toImage()
            if not img.isNull():
                img = img.convertToFormat(QImage.Format_RGB888)
                with self._lock:
                    self._img, self._t = img, now
                    self._size = (img.width(), img.height())
        self.frame_ready.emit()

    def latest(self) -> np.ndarray:
        with self._lock:
            img, t = self._img, self._t
        if img is None or time.time() - t > 3:
            if self.error:
                raise CaptureError(f"A videóeszköz hibát jelzett: {self.error}", "device_error")
            raise CaptureError("Nem érkezik kép a videóeszközről. Be van kapcsolva a konzol?", "no_signal")
        w, h, bpl = img.width(), img.height(), img.bytesPerLine()
        return np.frombuffer(img.constBits(), np.uint8, h * bpl).reshape(h, bpl)[:, : w * 3].reshape(h, w, 3).copy()

    def size(self) -> tuple[int, int]:
        with self._lock:
            sz = self._size
        if sz:
            return sz
        r = self.camera.cameraFormat().resolution()
        return (r.width() or 1920), (r.height() or 1080)

    def close(self):
        self._extra_sink = None
        try:
            self.sink.videoFrameChanged.disconnect(self._on_frame)
        except (RuntimeError, TypeError):
            pass
        self.camera.stop()
        self.session.setAudioOutput(None)
        self.session.setAudioInput(None)


class DeviceCapture(CaptureSource):
    """CaptureSource for kind == "device"; ident = device id. Open sessions are created by the GUI."""

    def __init__(self):
        self.sessions: dict[str, DeviceSession] = {}

    def session(self, ident) -> DeviceSession:
        s = self.sessions.get(str(ident))
        if s is None:
            raise CaptureError("A videóeszköz nincs megnyitva.", "device_gone")
        return s

    def source_size(self, kind, ident):
        return self.session(ident).size()

    def origin(self, kind, ident):
        return 0, 0                      # overlay coordinates are frame coordinates (Game View)

    def grab(self, kind, ident, rect=None):
        rgb = self.session(ident).latest()
        if rect:
            x, y, w, h = rect
            rgb = rgb[max(0, y):y + h, max(0, x):x + w]
        return rgb


class MultiCapture(CaptureSource):
    """Routes screen/window sources to the platform backend and "device" to the video devices."""

    def __init__(self, platform: CaptureSource, devices: DeviceCapture):
        self.platform, self.devices = platform, devices

    def _b(self, kind):
        return self.devices if kind == "device" else self.platform

    def list_windows(self):
        return self.platform.list_windows()

    def list_screens(self):
        return self.platform.list_screens()

    def source_size(self, kind, ident):
        return self._b(kind).source_size(kind, ident)

    def grab(self, kind, ident, rect=None):
        return self._b(kind).grab(kind, ident, rect)

    def origin(self, kind, ident):
        return self._b(kind).origin(kind, ident)

    def is_foreground(self, kind, ident):
        return self._b(kind).is_foreground(kind, ident)
