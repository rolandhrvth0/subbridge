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
                                  QMediaDevices, QVideoFrame, QVideoFrameFormat, QVideoSink)

from .base import CaptureError, CaptureSource


def list_devices() -> list[dict]:
    return [{"id": bytes(d.id()).decode(errors="ignore"), "name": d.description()}
            for d in QMediaDevices.videoInputs()]


def list_audio_outputs() -> list[dict]:
    return [{"id": bytes(d.id()).decode(errors="ignore"), "name": d.description()}
            for d in QMediaDevices.audioOutputs()]


def _audio_output(out_id: str):
    """The chosen speakers/headphones, else the system default (also when the chosen one is unplugged)."""
    return next((d for d in QMediaDevices.audioOutputs() if bytes(d.id()).decode(errors="ignore") == out_id),
                None) if out_id else None


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


def _best_format(dev, wanted: str = "", low_latency: bool = True) -> QCameraFormat | None:
    """Capture cards (e.g. 4K HDMI→USB adapters) offer 4K30 / 1440p60 / 1080p60-120 in MJPEG and often
    a raw YUV mode. Best for subtitles + Game View: 1440p at 60 fps when the card offers it (sharper
    subtitle text and picture; a 30 fps game still gets each picture within 16 ms), else 1080p60.
    60 over 120 (a 30/60 fps console game gains nothing, half the decode work); raw YUV beats MJPEG
    (no decoding delay) at the same size."""
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
        if low_latency:
            # cheap USB 2 cards: 1080p only at 30 fps, 720p at 60 – a frame every 16 ms instead of 33 ms
            # matters more for input lag than the sharper picture (OCR reads 720p subtitles fine)
            return (fps >= 50 and h >= 700,
                    h in (1440, 1080),
                    h == 1440,
                    -abs(h - 1440),
                    -abs(min(fps, 120) - 60),
                    f.pixelFormat().name in _UNCOMPRESSED,
                    r.width())
        return (h in (1440, 1080),               # 1440p / 1080p first
                h == 1440,
                -abs(h - 1440),                  # otherwise the closest size
                fps >= 50,                       # smooth enough for the Game View
                -abs(min(fps, 120) - 60),        # 60 fps over 120 (half the decode work, same OCR)
                f.pixelFormat().name in _UNCOMPRESSED,
                r.width())
    return max(fmts, key=score)


def usb2_limited(dev) -> bool:
    """A 4K-capable card plugged into a USB 2 port only offers small modes (typically 720p30)."""
    fmts = usable_formats(dev)
    return bool(fmts) and max(f.resolution().height() for f in fmts) <= 720


_PF = QVideoFrameFormat.PixelFormat
# byte order in memory of the packed 32-bit formats -> index of R, G, B
_PACKED = {_PF.Format_BGRX8888: (2, 1, 0), _PF.Format_BGRA8888: (2, 1, 0),
           _PF.Format_XRGB8888: (1, 2, 3), _PF.Format_ARGB8888: (1, 2, 3),
           _PF.Format_RGBX8888: (0, 1, 2), _PF.Format_RGBA8888: (0, 1, 2),
           # measured on a JVA11 card (V4L2 BGR0 reported as XBGR8888): memory is B, G, R, X
           _PF.Format_XBGR8888: (2, 1, 0), _PF.Format_ABGR8888: (2, 1, 0)}


def _plane(frame: QVideoFrame, i: int, rows: int) -> np.ndarray:
    bpl = frame.bytesPerLine(i)
    return np.frombuffer(frame.bits(i), np.uint8, count=bpl * rows).reshape(rows, bpl)


def _frame_rgb_cpu(frame: QVideoFrame) -> np.ndarray | None:
    """Raw capture-card formats converted on the CPU. QVideoFrame.toImage() converts YUV with a GPU
    shader and first creates a thread-local OpenGL context; when that fails (bundled Qt + GLX on some
    drivers) Qt calls qFatal and the whole app aborts – no Python exception to catch. So never let raw
    card frames reach toImage(). Returns None for formats not handled here."""
    import cv2
    pf = frame.pixelFormat()
    w, h = frame.width(), frame.height()
    if pf not in (_PF.Format_NV12, _PF.Format_NV21, _PF.Format_YUYV, _PF.Format_UYVY, _PF.Format_YUV420P,
                  _PF.Format_YV12, _PF.Format_Jpeg) and pf not in _PACKED:
        return None
    if not frame.map(QVideoFrame.MapMode.ReadOnly):
        return None
    try:
        if pf == _PF.Format_Jpeg:
            raw = np.frombuffer(bytes(frame.bits(0)[:frame.mappedBytes(0)]), np.uint8)
            bgr = cv2.imdecode(raw, cv2.IMREAD_COLOR)
            return None if bgr is None else cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        if pf in _PACKED:
            px = _plane(frame, 0, h)[:, : w * 4].reshape(h, w, 4)
            return np.ascontiguousarray(px[:, :, list(_PACKED[pf])])
        if pf in (_PF.Format_YUYV, _PF.Format_UYVY):
            px = np.ascontiguousarray(_plane(frame, 0, h)[:, : w * 2]).reshape(h, w, 2)
            code = cv2.COLOR_YUV2RGB_YUYV if pf == _PF.Format_YUYV else cv2.COLOR_YUV2RGB_UYVY
            return cv2.cvtColor(px, code)
        if pf in (_PF.Format_NV12, _PF.Format_NV21):
            y = _plane(frame, 0, h)[:, :w]
            uv = _plane(frame, 1, h // 2)[:, :w]
            code = cv2.COLOR_YUV2RGB_NV12 if pf == _PF.Format_NV12 else cv2.COLOR_YUV2RGB_NV21
            return cv2.cvtColor(np.ascontiguousarray(np.vstack([y, uv])), code)
        # planar 4:2:0 (I420 / YV12)
        y = _plane(frame, 0, h)[:, :w].reshape(-1)
        u = _plane(frame, 1, h // 2)[:, : w // 2].reshape(-1)
        v = _plane(frame, 2, h // 2)[:, : w // 2].reshape(-1)
        code = cv2.COLOR_YUV2RGB_I420 if pf == _PF.Format_YUV420P else cv2.COLOR_YUV2RGB_YV12
        return cv2.cvtColor(np.concatenate([y, u, v]).reshape(h * 3 // 2, w), code)
    except Exception:  # noqa: BLE001
        return None
    finally:
        frame.unmap()


def rgb_to_qimage(rgb: np.ndarray) -> QImage:
    h, w = rgb.shape[:2]
    return QImage(rgb.data, w, h, w * 3, QImage.Format_RGB888).copy()


def frame_to_qimage(frame: QVideoFrame) -> QImage:
    """RGB888 QImage of a frame; CPU conversion first, toImage() only for exotic formats."""
    rgb = _frame_rgb_cpu(frame)
    if rgb is not None:
        return rgb_to_qimage(rgb)
    img = frame.toImage()
    return img if img.isNull() else img.convertToFormat(QImage.Format_RGB888)


def frame_to_rgb(frame: QVideoFrame) -> np.ndarray | None:
    if frame is None or not frame.isValid() or frame.width() <= 0 or frame.height() <= 0:
        return None
    rgb = _frame_rgb_cpu(frame)
    if rgb is not None:
        return rgb
    img = frame.toImage()
    if img.isNull():
        return None
    img = img.convertToFormat(QImage.Format_RGB888)
    w, h, bpl = img.width(), img.height(), img.bytesPerLine()
    return np.frombuffer(img.constBits(), np.uint8, h * bpl).reshape(h, bpl)[:, : w * 3].reshape(h, w, 3).copy()


def picture_range(sample: np.ndarray) -> str:
    """'limited' when the darkest and brightest pixels of a varied picture sit at ~16 and ~235 (video
    levels shown as PC levels: grey blacks, dull whites), 'ok' otherwise, '' when the picture is too flat
    (menu, black screen) to tell."""
    v = np.asarray(sample, np.float32).reshape(-1)
    if v.size < 200:
        return ""
    lo, hi = np.percentile(v, 0.5), np.percentile(v, 99.5)
    if hi - lo < 120:
        return ""
    return "limited" if 10 <= lo <= 24 and 225 <= hi <= 240 else "ok"


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


def _clean_env() -> dict:
    """Environment for system tools started from the PyInstaller build (its bundled libs must not leak)."""
    import os
    env = dict(os.environ)
    for k in ("LD_LIBRARY_PATH", "LD_PRELOAD"):
        orig = env.pop(k + "_ORIG", None)
        if orig is not None:
            env[k] = orig
        elif getattr(__import__("sys"), "frozen", False):
            env.pop(k, None)
    return env


def _die_with_parent():
    """Child process: get SIGTERM when SubBridge exits or crashes (no orphan sound loop)."""
    try:
        import ctypes
        import signal
        ctypes.CDLL("libc.so.6", use_errno=True).prctl(1, signal.SIGTERM)   # PR_SET_PDEATHSIG
    except Exception:  # noqa: BLE001
        pass


class PipeWireLoopback:
    """Linux: card sound -> speakers inside PipeWire itself (pw-loopback, ~20 ms). Qt's QAudioSink with
    small buffers underruns constantly under PipeWire (thousands of xruns = silence), big buffers lag."""

    def __init__(self, in_dev, out_dev=None):
        self.in_id = bytes(in_dev.id()).decode(errors="ignore")
        self.out_id = bytes(out_dev.id()).decode(errors="ignore") if out_dev is not None else ""
        self.proc = None

    @staticmethod
    def available() -> bool:
        import shutil
        import sys
        return sys.platform.startswith("linux") and shutil.which("pw-loopback") is not None

    def start(self) -> bool:
        import subprocess
        cap = f"target.object={self.in_id} node.name=subbridge-card-in node.description=SubBridge"
        play = "node.name=subbridge-card-out node.description=SubBridge media.role=Game"
        if self.out_id:
            play += f" target.object={self.out_id}"
        try:
            self.proc = subprocess.Popen(["pw-loopback", "--latency=20ms", f"--capture-props={cap}",
                                          f"--playback-props={play}"], env=_clean_env(),
                                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL, preexec_fn=_die_with_parent)
        except OSError:
            self.proc = None
            return False
        time.sleep(0.15)
        if self.proc.poll() is not None:              # exited at once: unknown node, no PipeWire
            self.proc = None
            return False
        return True

    def stop(self):
        p, self.proc = self.proc, None
        if p is not None and p.poll() is None:
            p.terminate()
            try:
                p.wait(1.0)
            except Exception:  # noqa: BLE001
                p.kill()


class LowLatencyAudio:
    """Card sound straight to the speakers with ~30 ms buffers (Qt's built-in passthrough buffers far
    more, so the sound lags behind the picture). Old data is dropped rather than queued: lag never grows."""

    def __init__(self, in_dev, out_dev=None):
        self.in_dev = in_dev
        self.out_dev = out_dev
        self.src = self.sink = self.io_in = self.io_out = None

    def start(self) -> bool:
        from PySide6.QtMultimedia import QAudioSink, QAudioSource
        fmt = self.in_dev.preferredFormat()
        out_dev = self.out_dev or QMediaDevices.defaultAudioOutput()
        if not out_dev.isFormatSupported(fmt):
            fmt = out_dev.preferredFormat()
            if not self.in_dev.isFormatSupported(fmt):
                return False
        self.src = QAudioSource(self.in_dev, fmt)
        self.sink = QAudioSink(out_dev, fmt)
        self.src.setBufferSize(max(256, fmt.bytesForDuration(15000)))
        self.sink.setBufferSize(max(512, fmt.bytesForDuration(35000)))
        self.io_out = self.sink.start()
        self.io_in = self.src.start()
        if self.io_in is None or self.io_out is None:
            self.stop()
            return False
        self._frame = max(1, fmt.bytesPerFrame())
        self.io_in.readyRead.connect(self._pump)
        return True

    def _pump(self):
        data = self.io_in.readAll()
        free = self.sink.bytesFree()
        n = len(data)
        if n > free:                                   # speakers behind: keep only the newest sound
            keep = free - free % self._frame
            data = data[n - keep:] if keep > 0 else b""
        if data:
            self.io_out.write(data)

    def stop(self):
        for x in (self.src, self.sink):
            try:
                if x is not None:
                    x.stop()
            except Exception:  # noqa: BLE001
                pass
        self.src = self.sink = self.io_in = self.io_out = None


class DeviceSession(QObject):
    """One open device. Lives in the GUI thread (Qt Multimedia objects must)."""
    frame_ready = Signal()

    def __init__(self, device_id: str, audio_id: str = "", play_audio: bool = False, fmt_key: str = "",
                 low_latency: bool = True, audio_out_id: str = ""):
        super().__init__()
        dev = next((d for d in QMediaDevices.videoInputs() if bytes(d.id()).decode(errors="ignore") == device_id), None)
        if dev is None:
            raise CaptureError("Nem találom a kiválasztott videóeszközt. Be van dugva?", "device_gone")
        self.device_id = device_id
        self.name = dev.description()
        self.camera = QCamera(dev)
        self.low_latency = low_latency
        self._ll_audio = None
        fmt = _best_format(dev, fmt_key, low_latency)
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
        self._dedupe = False              # GPU Game View + driver frame gen: show each game picture once
        self._last_sig = None
        self.sink.videoFrameChanged.connect(self._on_frame)
        self._lock = threading.Lock()
        self._img: QImage | None = None
        self._size: tuple[int, int] | None = None
        self._t = 0.0
        self.error = ""
        self.camera.errorOccurred.connect(lambda _e, msg: setattr(self, "error", msg))
        self._opened = time.time()
        self._last_frame = 0.0             # any frame (also the ones not converted)
        self._fps_n, self._fps_t0, self.fps = 0, time.time(), 0.0
        self._restarts = 0
        self._restart_t = 0.0
        self.audio_in = self.audio_out = None
        self.audio_out_id = audio_out_id
        self.set_audio(audio_id, play_audio)
        self.camera.start()

    # sound passthrough (for capture cards without HDMI passthrough)
    def set_audio(self, audio_id: str, play: bool):
        if self._ll_audio is not None:
            self._ll_audio.stop()
            self._ll_audio = None
        if play and getattr(self, "low_latency", False):
            dev = next((d for d in QMediaDevices.audioInputs() if bytes(d.id()).decode(errors="ignore") == audio_id), None) \
                or guess_audio(self.name)
            if dev is not None:
                self.session.setAudioInput(None)
                self.session.setAudioOutput(None)
                self.audio_in = self.audio_out = None
                out = _audio_output(self.audio_out_id)
                if PipeWireLoopback.available():
                    self._ll_audio = PipeWireLoopback(dev, out)
                    if self._ll_audio.start():
                        return
                self._ll_audio = LowLatencyAudio(dev, out)
                if self._ll_audio.start():
                    return
                self._ll_audio = None
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
        out = _audio_output(self.audio_out_id)
        self.audio_out = QAudioOutput(out) if out is not None else QAudioOutput()
        self.session.setAudioInput(self.audio_in)
        self.session.setAudioOutput(self.audio_out)

    def attach_view(self, video_item_sink: QVideoSink | None, dedupe: bool = False):
        """Mirror frames to a Game View (its QGraphicsVideoItem sink). Only the frame handle is passed on
        (no copy). Rendering straight into the view's sink is not used: those frames can be GPU textures
        that crash when read back for OCR."""
        self._extra_sink = video_item_sink
        self._dedupe = dedupe
        self._last_sig = None

    def _is_repeat(self, frame: QVideoFrame) -> bool:
        """A 60 Hz card sends every picture of a 30 fps game twice. Frame generation (lsfg-vk, AMD AFMF,
        NVIDIA Smooth Motion) needs the real 30 different pictures, not 60 with repeats – compare a sparse
        sample of the first plane (luma for YUV) with the previous frame (~0.1 ms)."""
        if not frame.map(QVideoFrame.MapMode.ReadOnly):
            return False
        try:
            if frame.pixelFormat() == QVideoFrameFormat.PixelFormat.Format_Jpeg:
                # cheap cards send MJPEG: the bytes differ even for the same picture – decode a 1/8 size
                # grey thumbnail (libjpeg DCT scaling, ~1 ms at 1080p) and compare that
                import io
                from PIL import Image
                im = Image.open(io.BytesIO(bytes(frame.bits(0)[:frame.mappedBytes(0)])))
                im.draft("L", (max(1, frame.width() // 8), max(1, frame.height() // 8)))
                sig = np.asarray(im.convert("L"), np.int16)[2:-2, 2:-2]
            else:
                bpl, h = frame.bytesPerLine(0), frame.height()
                buf = np.frombuffer(frame.bits(0), np.uint8, count=bpl * h).reshape(h, bpl)
                sig = buf[8:h - 8:12, 16:bpl - 16:24].astype(np.int16)
        except Exception:  # noqa: BLE001
            return False
        finally:
            frame.unmap()
        last, self._last_sig = self._last_sig, sig
        if last is None or last.shape != sig.shape:
            return False
        d = np.abs(sig - last)
        return float(d.mean()) < 0.7 and int(np.percentile(d, 99.5)) < 14

    def set_frame_callback(self, cb):
        """Frame generation: every frame as an RGB QImage (converted here, while the buffer is valid)."""
        self._fg_cb = cb

    def _on_frame(self, frame: QVideoFrame):
        if not frame.isValid():
            return
        now = time.time()
        self._last_frame = now
        self._restarts = 0
        self._fps_n += 1
        if now - self._fps_t0 >= 2.0:
            self.fps, self._fps_n, self._fps_t0 = self._fps_n / (now - self._fps_t0), 0, now
        if self._extra_sink is not None and not (self._dedupe and self._is_repeat(frame)):
            self._extra_sink.setVideoFrame(frame)
        now = time.time()
        if self._fg_cb is not None:
            img = frame_to_qimage(frame)
            if not img.isNull():
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
            img = frame_to_qimage(frame)
            if not img.isNull():
                with self._lock:
                    self._img, self._t = img, now
                    self._size = (img.width(), img.height())
        self.frame_ready.emit()

    def stalled(self, after: float = 4.0) -> bool:
        """No frame for a while although the device is open: the console went to rest mode, the HDMI
        signal changed resolution (PS5 boot logo → game) or the USB link reset. Many UVC cards then keep
        the stream dead until it is reopened."""
        ref = max(self._last_frame, self._opened, self._restart_t)
        return time.time() - ref > after

    def restart(self) -> bool:
        """Restart the stream in place (keeps the Game View and sinks attached). Backs off after a few
        tries so a switched-off console does not cause a restart every few seconds."""
        now = time.time()
        wait = 4.0 if self._restarts < 3 else 20.0
        if now - self._restart_t < wait:
            return False
        self._restarts += 1
        self._restart_t = now
        self.error = ""
        self._last_sig = None
        if self.camera is None:
            return False
        try:
            self.camera.stop()
            self.camera.start()
        except Exception:  # noqa: BLE001
            return False
        return True

    def signal_info(self) -> dict:
        """What actually arrives from the card (for the settings page): size, measured fps and whether
        the picture looks like limited-range video (16–235) shown as full range – washed-out blacks."""
        with self._lock:
            img = self._img
        live = not self.stalled(3.0)
        info = {"live": live, "fps": round(self.fps) if live else 0, "size": self._size, "format": self.format,
                "range": ""}
        if img is not None and live:
            w, h, bpl = img.width(), img.height(), img.bytesPerLine()
            a = np.frombuffer(img.constBits(), np.uint8, h * bpl).reshape(h, bpl)[::8, : w * 3: 24]
            info["range"] = picture_range(a)
        return info

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
        if self.camera is None:
            return 1920, 1080
        r = self.camera.cameraFormat().resolution()
        return (r.width() or 1920), (r.height() or 1080)

    def close(self):
        if self.camera is None:          # already closed
            return
        self._extra_sink = None
        if self._ll_audio is not None:
            self._ll_audio.stop()
            self._ll_audio = None
        try:
            self.sink.videoFrameChanged.disconnect(self._on_frame)
        except (RuntimeError, TypeError):
            pass
        self.camera.stop()
        self.session.setAudioOutput(None)
        self.session.setAudioInput(None)
        # Release the V4L2 device NOW: a stopped QCamera that is still attached keeps the device open,
        # and a new session on the same card (settings saved, audio changed) then gets no frames at all.
        self.session.setVideoSink(None)
        self.session.setCamera(None)
        cam, self.camera = self.camera, None
        cam.deleteLater()
        try:
            from PySide6.QtCore import QCoreApplication, QEvent
            QCoreApplication.sendPostedEvents(cam, QEvent.DeferredDelete)
        except Exception:  # noqa: BLE001
            pass


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
