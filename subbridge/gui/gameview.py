"""Game View: plays a capture card's picture and sound full screen, with the translation drawn
straight over the game's subtitle boxes. For cards without HDMI passthrough (or to play on the PC)."""
from __future__ import annotations

from html import escape

import threading

import numpy as np
from PySide6.QtCore import QRectF, QSizeF, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPen, QPixmap
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtWidgets import (QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsScene, QGraphicsTextItem,
                               QGraphicsView, QLabel, QVBoxLayout, QWidget)

from ..branding import APP_NAME
from ..i18n import tr

PAD_X, PAD_Y, BLEED = 22, 6, 6


class _SubBox(QGraphicsRectItem):
    def __init__(self, parent):
        super().__init__(parent)
        self.setPen(QPen(Qt.NoPen))
        self.text = QGraphicsTextItem(self)
        self.text.setDefaultTextColor(QColor("#ffffff"))
        self.setZValue(10)
        self.key = None


def _to_np(img: QImage) -> np.ndarray:
    w, h, bpl = img.width(), img.height(), img.bytesPerLine()
    return np.frombuffer(img.constBits(), np.uint8, h * bpl).reshape(h, bpl)[:, : w * 3].reshape(h, w, 3)


def _to_qimage(a: np.ndarray) -> QImage:
    a = np.ascontiguousarray(a)
    h, w = a.shape[:2]
    return QImage(a.data, w, h, w * 3, QImage.Format_RGB888).copy()


class _FrameGenWorker(QThread):
    """Takes the newest captured frame, returns the frames to show (see framegen.FrameGen)."""
    ready = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        from ..framegen import FrameGen
        self.fg = FrameGen()
        self._cv = threading.Condition()
        self._q: list[QImage] = []
        self._stop = False

    def put(self, img: QImage):
        with self._cv:
            self._q.append(img)
            del self._q[:-2]                 # never fall behind: keep the two newest
            self._cv.notify()

    def stop(self):
        with self._cv:
            self._stop = True
            self._cv.notify()
        self.wait(1000)

    def run(self):
        while True:
            with self._cv:
                while not self._q and not self._stop:
                    self._cv.wait(0.5)
                if self._stop:
                    return
                img = self._q.pop(0)
            try:
                out = self.fg.push(_to_np(img).copy())
            except Exception:  # noqa: BLE001  – never take the picture down
                out = [_to_np(img).copy()]
            if out:
                self.ready.emit([_to_qimage(f) for f in out])


class GameView(QWidget):
    def __init__(self, session, on_close=None):
        super().__init__(None, Qt.Window)
        self.session = session
        self.on_close = on_close
        self.setWindowTitle(f"{APP_NAME} – {tr('game_view')}")
        self.resize(1280, 760)
        self.setStyleSheet("background:#000")
        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene, self)
        self.view.setFrameShape(QGraphicsView.NoFrame)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setRenderHints(QPainter.SmoothPixmapTransform | QPainter.Antialiasing | QPainter.TextAntialiasing)
        self.view.setBackgroundBrush(QBrush(Qt.black))
        self.video = QGraphicsVideoItem()
        self.scene.addItem(self.video)
        self.video.nativeSizeChanged.connect(lambda _s: self._fit())
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.view)
        self.hint = QLabel(tr("game_view_hint"), self)
        self.hint.setStyleSheet("background:rgba(0,0,0,170); color:#ddd; padding:8px 14px; border-radius:8px;")
        self.hint.adjustSize()
        QTimer.singleShot(4500, self.hint.hide)
        self.boxes: list[_SubBox] = []
        self.scale = 1.0
        self.setMouseTracking(True)
        self.view.setMouseTracking(True)
        self._cursor = QTimer(self, singleShot=True, interval=2000, timeout=lambda: self.setCursor(Qt.BlankCursor))
        session.attach_view(self.video.videoSink())
        # frame generation (30 fps game -> 60 fps picture); a picture item above the video, below the boxes
        self.fg_item = QGraphicsPixmapItem(self.video)
        self.fg_item.setZValue(1)
        self.fg_item.setTransformationMode(Qt.SmoothTransformation)
        self.fg_item.hide()
        self.fg_worker = None
        self._fg_next = None
        self._fg_timer = QTimer(self, singleShot=True, timeout=self._fg_show_next)
        self._fg_badge = QLabel(self)
        self._fg_badge.setStyleSheet("background:rgba(0,0,0,150); color:#cfd6e4; padding:4px 10px; "
                                     "border-radius:6px; font-size:12px;")
        self._fg_badge.hide()
        self._fg_badge_t = QTimer(self, interval=1000, timeout=self._fg_badge_update)
        from ..framegen import available
        if getattr(session, "framegen_wanted", True) and available() and hasattr(session, "set_frame_callback"):
            self.set_framegen(True)

    # ------------------------------------------------------------------ frame generation
    def set_framegen(self, on: bool):
        on = False      # CPU interpolation removed in 1.2.3 (smeary, laggy); real frame gen = lsfg/AFMF/Smooth Motion
        if on and self.fg_worker is None:
            self.fg_worker = _FrameGenWorker(self)
            self.fg_worker.ready.connect(self._fg_frames)
            self.fg_worker.start()
            self.session.set_frame_callback(self.fg_worker.put)
            self._fg_badge_t.start()
        elif not on and self.fg_worker is not None:
            self.session.set_frame_callback(None)
            self.fg_worker.stop()
            self.fg_worker = None
            self.fg_item.hide()
            self._fg_badge.hide()
            self._fg_badge_t.stop()
        self.session.framegen_wanted = on

    def _fg_frames(self, frames: list):
        self._fg_set(frames[0])
        if len(frames) > 1:                    # true 30 Hz source: real frame half an interval later
            self._fg_next = frames[1]
            self._fg_timer.start(16)

    def _fg_show_next(self):
        if self._fg_next is not None:
            self._fg_set(self._fg_next)
            self._fg_next = None

    def _fg_set(self, img: QImage):
        self.fg_item.setPixmap(QPixmap.fromImage(img))
        fs = self._frame_size()
        if img.width() and abs(img.width() - fs.width()) > 1:
            self.fg_item.setScale(fs.width() / img.width())
        self.fg_item.show()

    def _fg_badge_update(self):
        w = self.fg_worker
        if w is None:
            return
        mode = w.fg.mode
        text = {"dup": tr("fg_on"), "30": tr("fg_on"), "pass": tr("fg_native"), "auto": tr("fg_learning")}[mode]
        if mode in ("dup", "30"):
            text += f"  ·  {w.fg.stats['ms']:.0f} ms"
        self._fg_badge.setText(text)
        self._fg_badge.adjustSize()
        self._fg_badge.move(self.width() - self._fg_badge.width() - 16, 16)
        self._fg_badge.setVisible(not self.isFullScreen() or self.hint.isVisible())

    # ------------------------------------------------------------------ layout
    def _frame_size(self) -> QSizeF:
        ns = self.video.nativeSize()
        return ns if ns.width() > 0 else QSizeF(*self.session.size())

    def _fit(self):
        fs = self._frame_size()
        self.video.setSize(fs)
        self.scene.setSceneRect(QRectF(0, 0, fs.width(), fs.height()))
        self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit()
        self.hint.move((self.width() - self.hint.width()) // 2, 24)

    # ------------------------------------------------------------------ subtitles (frame coordinates)
    def update_boxes(self, boxes: list[dict]):
        while len(self.boxes) < len(boxes):
            self.boxes.append(_SubBox(self.video))
        for i, b in enumerate(self.boxes):
            if i >= len(boxes):
                b.hide()
                b.key = None
                continue
            box = boxes[i]
            x0, y0, x1, y1 = box["rect"]
            x0, y0, x1, y1 = x0 - BLEED, y0 - BLEED / 2, x1 + BLEED, y1 + BLEED / 2
            px = max(13, int(box["px"] * 1.08 * self.scale))
            name = "#%02x%02x%02x" % tuple(box["name"]) if box.get("name") else "#f4d35e"
            rows = [(f'<span style="color:{name}">{escape(sp)}:</span> ' if sp else "") + escape(t)
                    for sp, t in box["lines"] if t]
            font = QFont("Inter Variable")
            font.setPixelSize(px)
            b.text.setFont(font)
            b.text.setHtml(f'<div align="center" style="line-height:118%">{"<br>".join(rows)}</div>')
            b.text.setTextWidth(-1)
            natural = b.text.boundingRect().width() + 2 * PAD_X
            width = min(max(x1 - x0, natural), max(box.get("max_w", x1 - x0), x1 - x0))
            b.text.setTextWidth(width - 2 * PAD_X)
            height = max(y1 - y0, b.text.boundingRect().height() + 2 * PAD_Y)
            cx = (x0 + x1) / 2
            b.setRect(QRectF(cx - width / 2, y1 - height, width, height))
            b.setBrush(QColor(*box["bg"]))
            b.text.setPos(cx - width / 2 + PAD_X, y1 - height + (height - b.text.boundingRect().height()) / 2)
            b.show()

    def show_phone(self, state):
        from PySide6.QtCore import QRect
        from .phonepanel import PhonePanel
        if not hasattr(self, "phone_panel"):
            self.phone_panel = PhonePanel(self.view.viewport())
        if not state or not state.get("items"):        # phone home screen / menus: nothing to translate
            self.phone_panel.show_state(None, QRect(), QRect())
            return
        x0, y0, x1, y1 = state["rect"]
        tl = self.view.mapFromScene(self.video.mapToScene(x0, y0))
        br = self.view.mapFromScene(self.video.mapToScene(x1, y1))
        vr = self.view.mapFromScene(self.scene.sceneRect()).boundingRect()
        self.phone_panel.show_state(state, vr, QRect(tl, br))

    # ------------------------------------------------------------------ controls
    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_F11, Qt.Key_F):
            self.toggle_full()
        elif e.key() == Qt.Key_G:
            self.set_framegen(self.fg_worker is None)
            self._fg_badge.setText(tr("fg_on") if self.fg_worker else tr("fg_off"))
            self._fg_badge.adjustSize()
            self._fg_badge.move(self.width() - self._fg_badge.width() - 16, 16)
            self._fg_badge.show()
            QTimer.singleShot(2500, self._fg_badge_update)
        elif e.key() == Qt.Key_Escape and self.isFullScreen():
            self.showNormal()
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

    def closeEvent(self, e):
        if self.fg_worker is not None:
            self.session.set_frame_callback(None)
            self.fg_worker.stop()
            self.fg_worker = None
        self.session.attach_view(None)
        if self.on_close:
            self.on_close()
        super().closeEvent(e)
