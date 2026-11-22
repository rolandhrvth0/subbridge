"""Game View: plays a capture card's picture and sound full screen, with the translation drawn
straight over the game's subtitle boxes. For cards without HDMI passthrough (or to play on the PC)."""
from __future__ import annotations

from html import escape

from PySide6.QtCore import QRectF, QSizeF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtWidgets import (QGraphicsRectItem, QGraphicsScene, QGraphicsTextItem, QGraphicsView, QLabel,
                               QVBoxLayout, QWidget)

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
        if not state:
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
        self.session.attach_view(None)
        if self.on_close:
            self.on_close()
        super().closeEvent(e)
