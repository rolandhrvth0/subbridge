"""Apple-style building blocks for the main window: iOS switch, inset grouped list rows, sidebar buttons and the
game tile. Plain Qt widgets painted by hand – no images, no game artwork (the GTA VI tile is SubBridge's own
synthwave sun, not a publisher logo)."""
from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import (QAbstractButton, QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout,
                               QWidget)


class Switch(QAbstractButton):
    """iOS-style on/off switch with a sliding knob."""

    def __init__(self, parent=None, accent="#ff2d55", off="#d1d1d6"):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(46, 28)
        self._pos = 0.0
        self.accent, self.off = QColor(accent), QColor(off)
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.toggled.connect(self._animate)

    def set_colors(self, accent: str, off: str):
        self.accent, self.off = QColor(accent), QColor(off)
        self.update()

    def _animate(self, on):
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def setChecked(self, on):          # no animation when set from code before the widget is shown
        super().setChecked(on)
        if not self.isVisible():
            self._anim.stop()
            self._pos = 1.0 if on else 0.0

    def get_knob(self):
        return self._pos

    def set_knob(self, v):
        self._pos = v
        self.update()

    knob = Property(float, get_knob, set_knob)

    def sizeHint(self):
        return QSize(46, 28)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(1, 1, self.width() - 2, self.height() - 2)
        t = self._pos
        col = QColor(int(self.off.red() + (self.accent.red() - self.off.red()) * t),
                     int(self.off.green() + (self.accent.green() - self.off.green()) * t),
                     int(self.off.blue() + (self.accent.blue() - self.off.blue()) * t))
        if not self.isEnabled():
            col.setAlpha(110)
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        d = r.height() - 4
        x = r.x() + 2 + (r.width() - d - 4) * t
        p.setBrush(QColor(0, 0, 0, 40))
        p.drawEllipse(QRectF(x, r.y() + 2.6, d, d))
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QRectF(x, r.y() + 2, d, d))


class GroupRow(QFrame):
    """One row of an inset grouped list: icon, title + subtitle, and a switch or a chevron. Compatible with the
    old FeatureTile API (clicked, set_state(state, sub, colors)) so the window logic did not have to change."""
    clicked = Signal()

    def __init__(self, icon_name: str, title: str, kind: str = "switch", parent=None):
        super().__init__(parent)
        self.icon_name, self.kind = icon_name, kind
        self.state = "off"
        self.setCursor(Qt.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(12)
        self.ic = QLabel(objectName="rowIcon")
        self.ic.setFixedSize(30, 30)
        self.ic.setAlignment(Qt.AlignCenter)
        col = QVBoxLayout()
        col.setSpacing(1)
        self.title = QLabel(title, objectName="rowTitle")
        self.sub = QLabel(objectName="rowSub", wordWrap=True)
        col.addWidget(self.title)
        col.addWidget(self.sub)
        lay.addWidget(self.ic)
        lay.addLayout(col, 1)
        self.switch = None
        self.chev = None
        if kind == "switch":
            self.switch = Switch()
            self.switch.clicked.connect(lambda: self.clicked.emit())
            lay.addWidget(self.switch)
        else:
            self.chev = QLabel()
            lay.addWidget(self.chev)

    def set_state(self, state: str, sub: str, colors: dict):
        """state: on | off | disabled | action"""
        from .icons import icon
        self.state = state
        self.sub.setText(sub)
        tint = {"on": colors["accent"], "off": colors["muted"], "disabled": colors["muted"],
                "action": colors["accent"]}[state]
        from .theme import rgba
        self.ic.setStyleSheet(f"background: {rgba(tint, 34)}; border-radius: 8px;")
        self.ic.setPixmap(icon(self.icon_name, tint, 18).pixmap(18, 18))
        if self.switch is not None:
            self.switch.set_colors(colors["accent"], colors["line"] if colors["bg"] < "#8" else "#d1d1d6")
            self.switch.blockSignals(True)
            self.switch.setChecked(state == "on")
            self.switch.blockSignals(False)
            self.switch.setEnabled(state != "disabled")
        if self.chev is not None:
            self.chev.setPixmap(icon("chevron", colors["muted"], 16).pixmap(16, 16))
        self.title.setEnabled(state != "disabled")

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.state != "disabled" and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(e)


class Group(QFrame):
    """Inset grouped list (white rounded card, hairline separators between rows)."""

    def __init__(self, parent=None):
        super().__init__(parent, objectName="group")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 2, 0, 2)
        self.lay.setSpacing(0)
        self._n = 0

    def add(self, w: QWidget):
        if self._n:
            sep = QFrame(objectName="rowSep")
            wrap = QHBoxLayout()
            wrap.setContentsMargins(56, 0, 0, 0)
            wrap.addWidget(sep)
            self.lay.addLayout(wrap)
        self.lay.addWidget(w)
        self._n += 1
        return w


def section(title: str) -> QLabel:
    return QLabel(title, objectName="groupTitle")


class NavButton(QPushButton):
    def __init__(self, icon_name: str, text: str, parent=None):
        super().__init__(text, parent, objectName="navBtn")
        self.icon_name = icon_name
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setIconSize(QSize(18, 18))

    def recolor(self, colors: dict):
        from .icons import icon
        self.setIcon(icon(self.icon_name, colors["accent"] if self.isChecked() else colors["muted"], 18))


_PIX: dict = {}


def _photo(name: str):
    """Licensed stock photo of Miami (Pexels licence, see THIRD_PARTY_LICENSES.md) – no game artwork."""
    from PySide6.QtGui import QPixmap
    from ..paths import resource_dir
    if name not in _PIX:
        _PIX[name] = QPixmap(str(resource_dir() / "assets" / "ui" / f"{name}.jpg"))
    return _PIX[name]


def paint_cover(p: QPainter, r: QRectF, radius: float, name: str):
    """Draw the photo to fill r (cropped, not stretched) with rounded corners."""
    pm = _photo(name)
    path = QPainterPath()
    path.addRoundedRect(r, radius, radius)
    p.save()
    p.setClipPath(path)
    if not pm.isNull():
        s = max(r.width() / pm.width(), r.height() / pm.height())
        w, h = pm.width() * s, pm.height() * s
        p.drawPixmap(QRectF(r.center().x() - w / 2, r.center().y() - h / 2, w, h), pm, QRectF(pm.rect()))
    else:
        p.fillRect(r, QColor("#1c1c1f"))
    p.restore()


def paint_game_art(p: QPainter, r: QRectF, radius: float, big: bool = True):
    """The GTA VI tile: a real photo of Miami at golden hour with clean type on a soft gradient (the game's
    name only, in the app's own font – no publisher logo, font or key art)."""
    paint_cover(p, r, radius, "tile-miami")
    path = QPainterPath()
    path.addRoundedRect(r, radius, radius)
    p.save()
    p.setClipPath(path)
    g = QLinearGradient(r.topLeft(), r.bottomLeft())
    g.setColorAt(0.0, QColor(0, 0, 0, 0))
    g.setColorAt(0.55, QColor(0, 0, 0, 30))
    g.setColorAt(1.0, QColor(0, 0, 0, 170))
    p.fillRect(r, g)
    p.setPen(QColor("#ffffff"))
    f = QFont("Inter Variable")
    f.setPixelSize(max(8, int(r.height() * (0.17 if big else 0.34))))
    f.setWeight(QFont.Black)
    f.setLetterSpacing(QFont.PercentageSpacing, 97)
    p.setFont(f)
    if not big:
        p.drawText(QRectF(r.x(), r.bottom() - r.height() * 0.5, r.width(), r.height() * 0.45), Qt.AlignCenter, "VI")
    p.restore()


class HeroBanner(QFrame):
    """Home page header: wide photo card with a dark gradient, big title, subtitle and the start button."""

    def __init__(self, title: str, sub: str, button: QWidget, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(206)
        self.setMaximumHeight(230)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(32, 26, 30, 26)
        col = QVBoxLayout()
        col.setSpacing(6)
        col.addStretch(1)
        self.title = QLabel(title)
        self.title.setStyleSheet("color: #fff; font-size: 34px; font-weight: 800; letter-spacing: -0.8px; background: transparent;")
        self.sub = QLabel(sub, wordWrap=True)
        self.sub.setMinimumWidth(460)
        self.sub.setMaximumWidth(600)
        self.sub.setStyleSheet("color: rgba(255,255,255,0.86); font-size: 14px; background: transparent;")
        col.addWidget(self.title, 0, Qt.AlignLeft)
        col.addWidget(self.sub, 0, Qt.AlignLeft)
        lay.addLayout(col, 1)
        button.setFixedWidth(190)
        lay.addWidget(button, 0, Qt.AlignBottom)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = QRectF(self.rect())
        paint_cover(p, r, 18, "hero-miami")
        path = QPainterPath()
        path.addRoundedRect(r, 18, 18)
        p.setClipPath(path)
        g = QLinearGradient(r.topLeft(), r.topRight())
        g.setColorAt(0.0, QColor(8, 8, 14, 215))
        g.setColorAt(0.5, QColor(8, 8, 14, 120))
        g.setColorAt(1.0, QColor(8, 8, 14, 20))
        p.fillRect(r, g)
        g2 = QLinearGradient(r.topLeft(), r.bottomLeft())
        g2.setColorAt(0.5, QColor(0, 0, 0, 0))
        g2.setColorAt(1.0, QColor(0, 0, 0, 90))
        p.fillRect(r, g2)


class GameTile(QAbstractButton):
    """Large selectable game card for the game picker."""

    def __init__(self, title: str, sub: str, available: bool = True, parent=None):
        super().__init__(parent)
        self.title_text, self.sub_text, self.available = title, sub, available
        self.setCheckable(True)
        self.setEnabled(available)
        self.setCursor(Qt.PointingHandCursor if available else Qt.ArrowCursor)
        self.setFixedSize(260, 340)
        self.colors = {}

    def paintEvent(self, _):
        c = self.colors or {"surface": "#fff", "line": "#e2e2e7", "text": "#1d1d1f", "muted": "#6e6e73",
                            "accent": "#ff2d55", "surface2": "#f2f2f5"}
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        card = QRectF(2, 2, self.width() - 4, self.height() - 4)
        path = QPainterPath()
        path.addRoundedRect(card, 18, 18)
        p.fillPath(path, QColor(c["surface"]))
        pen = QPen(QColor(c["accent"] if self.isChecked() else c["line"]), 2.5 if self.isChecked() else 1)
        p.setPen(pen)
        p.drawPath(path)
        art = QRectF(card.x() + 12, card.y() + 12, card.width() - 24, card.width() - 24)
        if self.available:
            paint_game_art(p, art, 14)
        else:
            ap = QPainterPath()
            ap.addRoundedRect(art, 14, 14)
            p.fillPath(ap, QColor(c["surface2"]))
            p.setPen(QColor(c["muted"]))
            f = QFont("Inter Variable")
            f.setPixelSize(40)
            f.setWeight(QFont.Light)
            p.setFont(f)
            p.drawText(art, Qt.AlignCenter, "+")
        p.setPen(QColor(c["text"] if self.available else c["muted"]))
        f = QFont("Inter Variable")
        f.setPixelSize(17)
        f.setWeight(QFont.Bold)
        p.setFont(f)
        p.drawText(QRectF(card.x() + 16, art.bottom() + 12, card.width() - 32, 24), Qt.AlignLeft, self.title_text)
        p.setPen(QColor(c["muted"]))
        f.setPixelSize(12.5 if False else 13)
        f.setWeight(QFont.Normal)
        p.setFont(f)
        p.drawText(QRectF(card.x() + 16, art.bottom() + 38, card.width() - 32, 40), Qt.AlignLeft | Qt.TextWordWrap,
                   self.sub_text)


class GameBadge(QWidget):
    """Small rounded GTA VI art for the sidebar chip and the page header."""

    def __init__(self, size: int = 28, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        paint_game_art(p, QRectF(0, 0, self.width(), self.height()), self.width() * 0.24, big=False)


def hline() -> QFrame:
    f = QFrame(objectName="rowSep")
    f.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    return f
