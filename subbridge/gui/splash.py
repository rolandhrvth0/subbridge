"""Start-up animation: logo, name, who made it – while the main window is being built."""
from __future__ import annotations

import math
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QGuiApplication, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import QWidget

from ..branding import APP_NAME, VERSION
from ..paths import resource_dir

AUTHOR = "Roland Horváth"
SITE = "rolandhrvth.hu"
ACCENT = QColor("#ff4f87")


def _ease(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return 1 - (1 - t) ** 3


class Splash(QWidget):
    W, H = 560, 340

    def __init__(self, lang: str = "hu"):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.SplashScreen)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(self.W, self.H)
        self.lang = lang
        self.logo = QPixmap(str(resource_dir() / "server" / "web" / "icon-192.png"))
        self.t0 = time.monotonic()
        self.status = ""
        self._fade = 1.0
        self.timer = QTimer(self, interval=16, timeout=self.update)
        self.timer.start()
        scr = QGuiApplication.primaryScreen().availableGeometry()
        self.move(scr.center().x() - self.W // 2, scr.center().y() - self.H // 2)

    def set_status(self, text: str):
        self.status = text
        self.repaint()

    def elapsed(self) -> float:
        return time.monotonic() - self.t0

    def finish(self, then, min_s: float = 2.3):
        """Close after the intro has played at least `min_s` seconds (fade out), then call `then`."""
        wait = max(0, int((min_s - self.elapsed()) * 1000))

        def fade():
            self._fade -= 0.09
            if self._fade <= 0:
                self.timer.stop()
                self.close()
                then()
                return
            self.setWindowOpacity(self._fade)
            QTimer.singleShot(16, fade)
        QTimer.singleShot(wait, fade)

    def paintEvent(self, _):
        t = self.elapsed()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        w, h = self.width(), self.height()
        r = QRectF(8, 8, w - 16, h - 16)
        # card with a soft shadow
        for i in range(8, 0, -1):
            sh = QPainterPath()
            sh.addRoundedRect(r.adjusted(-i, -i + 3, i, i + 3), 22 + i, 22 + i)
            p.fillPath(sh, QColor(0, 0, 0, 7))
        card = QPainterPath()
        card.addRoundedRect(r, 20, 20)
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0, QColor("#1b1f27"))
        g.setColorAt(1, QColor("#0f1115"))
        p.fillPath(card, g)
        p.save()
        p.setClipPath(card)
        # slow accent glow drifting behind the logo
        cx = w / 2 + math.sin(t * 1.3) * 30
        rg = QRadialGradient(QPointF(cx, 100), 230)
        for stop, alpha in ((0, 70), (0.45, 22), (1, 0)):
            c = QColor(ACCENT)
            c.setAlpha(int(alpha * _ease(t / 0.6)))
            rg.setColorAt(stop, c)
        p.fillRect(r, rg)
        p.restore()
        p.setPen(QPen(QColor(255, 255, 255, 22), 1))
        p.drawPath(card)

        # logo: pops in
        k = _ease(t / 0.55)
        size = 76 * (0.6 + 0.4 * k)
        p.setOpacity(k)
        p.drawPixmap(QRectF(w / 2 - size / 2, 92 - size / 2, size, size).toRect(), self.logo)
        p.setOpacity(1)

        # name: letters slide up one after another
        f = QFont("Inter Variable")
        f.setPixelSize(34)
        f.setWeight(QFont.Bold)
        p.setFont(f)
        fm = p.fontMetrics()
        x = w / 2 - fm.horizontalAdvance(APP_NAME) / 2
        for i, ch in enumerate(APP_NAME):
            a = _ease((t - 0.35 - i * 0.045) / 0.35)
            p.setPen(QColor(255, 255, 255, int(255 * a)))
            p.drawText(QPointF(x, 172 + (1 - a) * 14), ch)
            x += fm.horizontalAdvance(ch)

        # tagline
        f2 = QFont("Inter Variable")
        f2.setPixelSize(14)
        p.setFont(f2)
        a = _ease((t - 0.85) / 0.4)
        p.setPen(QColor(236, 238, 242, int(170 * a)))
        tag = "Élő játékfelirat-fordító" if self.lang == "hu" else "Live game subtitle translator"
        p.drawText(QRectF(0, 182, w, 22), Qt.AlignCenter, tag)

        # progress line: indeterminate sweep
        bar = QRectF(w / 2 - 110, 226, 220, 3)
        track = QPainterPath()
        track.addRoundedRect(bar, 1.5, 1.5)
        p.fillPath(track, QColor(255, 255, 255, 26))
        seg = 70
        pos = (t * 160) % (bar.width() + seg) - seg
        p.save()
        p.setClipPath(track)
        sg = QLinearGradient(bar.left() + pos, 0, bar.left() + pos + seg, 0)
        c0 = QColor(ACCENT)
        c0.setAlpha(0)
        sg.setColorAt(0, c0)
        sg.setColorAt(0.5, ACCENT)
        sg.setColorAt(1, c0)
        p.fillRect(QRectF(bar.left() + pos, bar.top(), seg, bar.height()), sg)
        p.restore()
        if self.status:
            f3 = QFont("Inter Variable")
            f3.setPixelSize(11)
            p.setFont(f3)
            p.setPen(QColor(141, 149, 164))
            p.drawText(QRectF(0, 234, w, 20), Qt.AlignCenter, self.status)

        # credits
        a = _ease((t - 1.1) / 0.5)
        f4 = QFont("Inter Variable")
        f4.setPixelSize(12)
        p.setFont(f4)
        p.setPen(QColor(141, 149, 164, int(255 * a)))
        made = "Készítette" if self.lang == "hu" else "Made by"
        p.drawText(QRectF(28, h - 52, w - 56, 20), Qt.AlignLeft | Qt.AlignVCenter, f"{made}: {AUTHOR}")
        p.drawText(QRectF(28, h - 52, w - 56, 20), Qt.AlignRight | Qt.AlignVCenter, f"{SITE}  ·  v{VERSION}")
        f5 = QFont("Inter Variable")
        f5.setPixelSize(11)
        p.setFont(f5)
        p.setPen(QColor(141, 149, 164, int(150 * a)))
        lic = "Ingyenes és nyílt forráskódú (MIT)" if self.lang == "hu" else "Free and open source (MIT)"
        p.drawText(QRectF(28, h - 34, w - 56, 16), Qt.AlignLeft | Qt.AlignVCenter, lic)
