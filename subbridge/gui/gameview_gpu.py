"""Game View rendered on the graphics card (Qt Quick + VideoOutput).

Linux: Vulkan, so the lsfg-vk layer (Lossless Scaling frame generation) can double the frames.
Windows: Direct3D 11, which AMD Fluid Motion Frames and NVIDIA Smooth Motion work on (full screen).
Repeated pictures from a 60 Hz card are dropped first (30 fps game -> 30 real pictures), so the
driver generates real in-between frames instead of interpolating a picture with itself."""
from __future__ import annotations

import sys
from html import escape
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtQuick import QQuickView, QQuickWindow, QSGRendererInterface

from .. import fgmodes
from ..branding import APP_NAME
from ..i18n import tr

_API_SET = False


def prepare_graphics(mode: str, low_latency: bool = True) -> str:
    """Choose the graphics API (and load lsfg-vk) before the first Qt Quick window. Returns the
    frame generation mode really in use (lsfg cannot be loaded once Vulkan is running)."""
    global _API_SET
    fi = fgmodes.info()
    mode = fi.resolve(mode)
    if not _API_SET:
        _API_SET = True
        if low_latency and mode != "lsfg":
            # do not wait for the screen refresh before showing a new picture (Vulkan: mailbox where the
            # driver has it – no tearing; lsfg-vk paces its own frames, so it keeps the default)
            from PySide6.QtGui import QSurfaceFormat
            f = QSurfaceFormat.defaultFormat()
            f.setSwapInterval(0)
            QSurfaceFormat.setDefaultFormat(f)
        if sys.platform.startswith("linux"):
            # MangoHud (often enabled for every Vulkan program via MANGOHUD=1) crashes when a Qt Quick Vulkan
            # window is destroyed – that would take SubBridge down when the Game View closes
            import os
            os.environ["DISABLE_MANGOHUD"] = "1"
            if mode == "lsfg" and not fgmodes.enable_lsfg(fi):
                mode = "off"
            QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.Vulkan)
        elif sys.platform == "win32":
            QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.Direct3D11)
        prepare_graphics.loaded_lsfg = mode == "lsfg"
    elif mode == "lsfg" and not getattr(prepare_graphics, "loaded_lsfg", False):
        mode = "off"                     # needs a restart of SubBridge
    return mode


class GpuGameView(QQuickView):
    def __init__(self, session, on_close=None, mode: str = "auto", low_latency: bool = True):
        self.mode = prepare_graphics(mode, low_latency)
        self.low_latency = low_latency
        super().__init__()
        self.session = session
        self.on_close = on_close
        self.scale = 1.0
        self.setTitle(f"{APP_NAME} – {tr('game_view')}")
        self.setColor(Qt.black)
        self.setResizeMode(QQuickView.SizeRootObjectToView)
        self.resize(1280, 760)
        self.setSource(QUrl.fromLocalFile(str(Path(__file__).with_name("gameview_gpu.qml"))))
        self.root = self.rootObject()
        w, h = session.size()
        self.root.setProperty("srcW", w)
        self.root.setProperty("srcH", h)
        video = self.root.findChild(object, "video")
        self.sink = video.property("videoSink") if video is not None else None
        self.fg_worker = None
        if self.mode == "builtin":
            self._start_builtin()
        else:
            # driver / lsfg frame generation needs the game's real pictures without the card's repeats
            session.attach_view(self.sink, dedupe=self.mode in ("lsfg", "afmf", "smooth"))
        self.root.setProperty("hint", tr("game_view_hint_gpu"))
        self.root.setProperty("badge", self._badge_text())
        QTimer.singleShot(6000, lambda: self.root.setProperty("hint", ""))
        QTimer.singleShot(9000, lambda: self.root.setProperty("badge", "") if self.isFullScreen() else None)
        self._cursor = QTimer(self, singleShot=True, interval=2000, timeout=lambda: self.setCursor(Qt.BlankCursor))
        # (the closing signal's QQuickCloseEvent cannot be passed to Python: handle the close event instead)

    # ------------------------------------------------------------------ frame generation
    def _badge_text(self) -> str:
        fmt = getattr(self.session, "format", "") or ""
        src = fmt.split(":")[0].replace("x", "×") if fmt else ""
        parts = [p for p in (src, tr("ll_on") if self.low_latency else "") if p]
        fg = {"lsfg": tr("fg_lsfg_on"), "afmf": tr("fg_afmf_hint"), "smooth": tr("fg_smooth_hint"),
                "builtin": tr("fg_builtin_on"), "off": ""}.get(self.mode, "")
        if fg and self.mode != "off":
            fg += "  ·  " + tr("fg_lag_note")
        return "  ·  ".join(parts + ([fg] if fg else []))

    def _start_builtin(self):
        from PySide6.QtMultimedia import QVideoFrame
        from .gameview import _FrameGenWorker
        self.session.attach_view(None)
        self.fg_worker = _FrameGenWorker()
        self._pending = None
        self._next = QTimer(self, singleShot=True, timeout=self._show_pending)

        def show(frames):
            if self.sink is None:
                return
            self.sink.setVideoFrame(QVideoFrame(frames[0]))
            if len(frames) > 1:
                self._pending = frames[1]
                self._next.start(16)
        self._vf = QVideoFrame
        self.fg_worker.ready.connect(show)
        self.fg_worker.start()
        self.session.set_frame_callback(self.fg_worker.put)

    def _show_pending(self):
        if self._pending is not None and self.sink is not None:
            self.sink.setVideoFrame(self._vf(self._pending))
            self._pending = None

    # ------------------------------------------------------------------ subtitles (picture coordinates)
    def update_boxes(self, boxes: list[dict]):
        out = []
        for box in boxes:
            x0, y0, x1, y1 = box["rect"]
            name = "#%02x%02x%02x" % tuple(box["name"]) if box.get("name") else "#f4d35e"
            rows = [(f'<span style="color:{name}">{escape(sp)}:</span> ' if sp else "") + escape(t)
                    for sp, t in box["lines"] if t]
            if not rows:
                rows = ["&nbsp;"]
            out.append({"x0": x0 - 6, "y0": y0 - 3, "x1": x1 + 6, "y1": y1 + 3, "px": box["px"] * 1.08,
                        "html": "<br>".join(rows), "bg": "#%02x%02x%02x" % tuple(int(v) for v in box["bg"]),
                        "maxw": max(box.get("max_w", x1 - x0), x1 - x0)})
        self.root.setProperty("scaleText", self.scale)
        self.root.setProperty("boxes", out)

    def show_phone(self, state):
        if not state:
            self.root.setProperty("phone", None)
            return
        x0, y0, x1, y1 = state["rect"]
        self.root.setProperty("phone", {"header": state.get("header") or "", "x0": x0, "y0": y0, "x1": x1, "y1": y1,
                                        "items": [{"text": i["text"], "name": i.get("name") or "",
                                                   "mine": bool(i.get("mine")), "kind": i.get("kind", "")}
                                                  for i in state.get("items", [])]})

    # ------------------------------------------------------------------ controls
    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_F11, Qt.Key_F):
            self.toggle_full()
        elif e.key() == Qt.Key_Escape and self.isFullScreen():
            self.showNormal()
        elif e.key() == Qt.Key_G:
            self.root.setProperty("badge", self._badge_text() or tr("fg_off"))
            QTimer.singleShot(4000, lambda: self.root.setProperty("badge", ""))
        else:
            super().keyPressEvent(e)

    def mouseDoubleClickEvent(self, _e):
        self.toggle_full()

    def mouseMoveEvent(self, e):
        self.unsetCursor()
        self._cursor.start()
        super().mouseMoveEvent(e)

    def toggle_full(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def activateWindow(self):
        self.requestActivate()

    def event(self, e):
        from PySide6.QtCore import QEvent
        if e.type() == QEvent.Close:
            self._closing()
        return super().event(e)

    def _closing(self, _ev=None):
        if self.fg_worker is not None:
            self.session.set_frame_callback(None)
            self.fg_worker.stop()
            self.fg_worker = None
        self.session.attach_view(None)
        if self.on_close:
            cb, self.on_close = self.on_close, None
            cb()


def gpu_available() -> bool:
    try:
        return QGuiApplication.platformName() not in ("offscreen", "minimal")
    except Exception:  # noqa: BLE001
        return False
