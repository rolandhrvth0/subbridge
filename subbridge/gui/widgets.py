from __future__ import annotations

import numpy as np
import qrcode
from PySide6.QtCore import QPoint, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QPen
from PySide6.QtWidgets import QDialog, QFrame, QLabel, QVBoxLayout, QWidget

from ..i18n import tr


def np_to_qimage(rgb: np.ndarray) -> QImage:
    rgb = np.ascontiguousarray(rgb[..., :3])
    h, w = rgb.shape[:2]
    return QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()


class Card(QFrame):
    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(20, 16, 20, 18)
        self.lay.setSpacing(10)
        if title:
            self.title = QLabel(title.upper())                 # small caps-like section label
            self.title.setObjectName("cardTitle")
            f = self.title.font()
            f.setLetterSpacing(QFont.AbsoluteSpacing, 0.9)
            self.title.setFont(f)
            self.lay.addWidget(self.title)


class QrWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._m = None
        self.setMinimumSize(190, 190)

    def set_data(self, data: str):
        q = qrcode.QRCode(border=0, error_correction=qrcode.constants.ERROR_CORRECT_M)
        q.add_data(data)
        q.make(fit=True)
        self._m = q.get_matrix()
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        side = min(self.width(), self.height())
        x0, y0 = (self.width() - side) / 2, (self.height() - side) / 2
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#ffffff"))
        p.drawRoundedRect(QRectF(x0, y0, side, side), 12, 12)
        if not self._m:
            return
        n = len(self._m)
        pad = 14
        cell = (side - 2 * pad) / n
        p.setRenderHint(QPainter.Antialiasing, False)
        p.setBrush(QColor("#111317"))
        for r, row in enumerate(self._m):
            for c, v in enumerate(row):
                if v:
                    p.drawRect(QRectF(x0 + pad + c * cell, y0 + pad + r * cell, cell + 0.3, cell + 0.3))


class PreviewWidget(QLabel):
    """Shows the captured region with detected subtitle boxes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("preview")
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(120)
        self._img: QImage | None = None
        self._boxes = []

    def set_frame(self, rgb: np.ndarray, boxes):
        self._img = np_to_qimage(rgb)
        self._boxes = boxes or []
        self.update()

    def clear_frame(self, text=""):
        self._img = None
        self.setText(text)
        self.update()

    def paintEvent(self, e):
        if self._img is None:
            return super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        iw, ih = self._img.width(), self._img.height()
        s = min(self.width() / iw, self.height() / ih)
        w, h = iw * s, ih * s
        x, y = (self.width() - w) / 2, (self.height() - h) / 2
        p.drawImage(QRectF(x, y, w, h), self._img)
        p.setPen(QPen(QColor("#ff4f87"), 2))
        p.setBrush(Qt.NoBrush)
        for (x0, y0, x1, y1) in self._boxes:
            p.drawRoundedRect(QRectF(x + x0 * s, y + y0 * s, (x1 - x0) * s, (y1 - y0) * s), 4, 4)


class RegionSelector(QDialog):
    """Full-screen overlay showing a still of the source; the user drags a rectangle.
    ``result_region`` holds (x, y, w, h) fractions of the source after accept()."""

    def __init__(self, rgb: np.ndarray, initial=None, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Dialog)
        self.setCursor(Qt.CrossCursor)
        self.img = np_to_qimage(rgb)
        self._a: QPoint | None = None
        self._b: QPoint | None = None
        self.result_region = None
        self._initial = initial
        screen = QGuiApplication.screenAt(self.cursor().pos()) or QGuiApplication.primaryScreen()
        self.setGeometry(screen.geometry())

    def showEvent(self, e):
        super().showEvent(e)
        self.showFullScreen()
        if self._initial:
            r = self._img_rect()
            fx, fy, fw, fh = self._initial
            self._a = QPoint(int(r.x() + fx * r.width()), int(r.y() + fy * r.height()))
            self._b = QPoint(int(self._a.x() + fw * r.width()), int(self._a.y() + fh * r.height()))

    def _img_rect(self) -> QRectF:
        iw, ih = self.img.width(), self.img.height()
        s = min(self.width() / iw, (self.height() - 90) / ih, 1.0 if iw <= self.width() else 10)
        w, h = iw * s, ih * s
        return QRectF((self.width() - w) / 2, 70 + (self.height() - 90 - h) / 2, w, h)

    def _sel(self) -> QRect | None:
        if self._a is None or self._b is None:
            return None
        return QRect(self._a, self._b).normalized().intersected(self._img_rect().toRect())

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(12, 13, 16))
        r = self._img_rect()
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.drawImage(r, self.img)
        sel = self._sel()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 140))
        if sel and sel.width() > 2:
            for part in (QRectF(r.x(), r.y(), r.width(), sel.top() - r.y()),
                         QRectF(r.x(), sel.bottom(), r.width(), r.bottom() - sel.bottom()),
                         QRectF(r.x(), sel.top(), sel.left() - r.x(), sel.height()),
                         QRectF(sel.right(), sel.top(), r.right() - sel.right(), sel.height())):
                p.drawRect(part)
            p.setPen(QPen(QColor("#ff4f87"), 2))
            p.setBrush(Qt.NoBrush)
            p.drawRect(sel)
            sx = self.img.width() / r.width()
            label = f"{int(sel.width() * sx)} × {int(sel.height() * sx)}"
            p.setPen(QColor("#ffffff"))
            p.setFont(QFont("Inter", 11, QFont.DemiBold))
            p.drawText(sel.x(), sel.y() - 8, label)
        else:
            p.drawRect(r)
        # instruction bar
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(25, 28, 33, 235))
        bar = QRectF(self.width() / 2 - 380, 14, 760, 44)
        p.drawRoundedRect(bar, 12, 12)
        p.setPen(QColor("#eceef2"))
        p.setFont(QFont("Inter", 11))
        p.drawText(bar, Qt.AlignCenter, tr("region_hint") + "   Enter = OK")

    def mousePressEvent(self, e):
        self._a = self._b = e.position().toPoint()
        self.update()

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton:
            self._b = e.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, e):
        self._b = e.position().toPoint()
        self.update()
        sel = self._sel()
        if sel and sel.width() > 20 and sel.height() > 10:
            self._finish()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.reject()
        elif e.key() in (Qt.Key_Return, Qt.Key_Enter) and self._sel():
            self._finish()

    def _finish(self):
        sel, r = self._sel(), self._img_rect()
        self.result_region = [(sel.x() - r.x()) / r.width(), (sel.y() - r.y()) / r.height(),
                              sel.width() / r.width(), sel.height() / r.height()]
        self.accept()


class FeatureTile(QFrame):
    """Big, friendly on/off (or action) tile for the main features."""
    clicked = Signal()

    def __init__(self, icon_name: str, title: str, parent=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QHBoxLayout
        self.setObjectName("tile")
        self.setCursor(Qt.PointingHandCursor)
        self.icon_name = icon_name
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(12)
        self.ic = QLabel()
        self.ic.setFixedSize(34, 34)
        self.ic.setAlignment(Qt.AlignCenter)
        self.ic.setObjectName("tileIcon")
        col = QVBoxLayout()
        col.setSpacing(1)
        self.title = QLabel(title, objectName="tileTitle")
        self.sub = QLabel(objectName="tileSub", wordWrap=True)
        col.addWidget(self.title)
        col.addWidget(self.sub)
        lay.addWidget(self.ic)
        lay.addLayout(col, 1)
        self.state = "off"

    def set_state(self, state: str, sub: str, colors: dict):
        """state: on | off | disabled | action"""
        from .icons import icon
        self.state = state
        self.setProperty("state", state)
        self.sub.setText(sub)
        col = colors["accent_ink"] if state == "on" else colors["muted"] if state == "disabled" else colors["accent"]
        self.ic.setPixmap(icon(self.icon_name, col, 20).pixmap(20, 20))
        self.style().unpolish(self)
        self.style().polish(self)
        for w in (self.ic, self.title, self.sub):
            w.style().unpolish(w)
            w.style().polish(w)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.state != "disabled" and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(e)
