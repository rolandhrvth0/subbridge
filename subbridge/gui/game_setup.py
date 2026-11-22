"""'Set up the subtitles in the game' – animated step shown before the first start.

An animated, game-neutral settings menu walks through the recommended subtitle settings row by row
(the value flips to the right one, a check appears), then a sample subtitle turns into its translation.
Starting is only possible after the user confirms the game is set up like this."""
from __future__ import annotations

import math
import time

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QCheckBox, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..i18n import current_language

# (menu label, wrong value shown first, recommended value, why – hu, why – en)
ROWS = [
    ("Subtitles", "Off", "On",
     "A legteljesebb fokozat: a járókelők és NPC-k beszéde is feliratot kap – azt is lefordítja.",
     "The fullest level: ambient and NPC speech get subtitles too – they are translated as well."),
    ("Closed Captions", "On", "Off",
     "Hangeffektek leírása nélkül csak a beszéd kerül a feliratba.",
     "Without sound descriptions only speech is in the subtitles."),
    ("Size", "Small", "Medium",
     "Közepes méretnél a legpontosabb a felismerés, és nem takar ki sokat a képből.",
     "Medium reads most reliably and doesn't cover much of the picture."),
    ("Speaker Names", "Off", "On",
     "Így tudja, ki beszél – a nevek a telefonon és a képen is színesek lesznek.",
     "So it knows who is speaking – names are coloured on the phone and on screen."),
    ("Background", "None", "Solid",
     "Egyszínű doboz a szöveg mögött: ezt találja meg és takarja le pontosan.",
     "A plain box behind the text: found and covered exactly."),
]
STEP = 1.6          # s per row
FINALE = 3.2        # s for the subtitle demo at the end


def _ease(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return 1 - (1 - t) ** 3


class SetupAnimation(QWidget):
    def __init__(self, accent: str, parent=None):
        super().__init__(parent)
        self.accent = QColor(accent)
        self.t0 = time.monotonic()
        self.setMinimumSize(560, 330)
        self.timer = QTimer(self, interval=16, timeout=self.update)
        self.timer.start()
        self.on_row = None          # callback(row index) when a row becomes active

    def _phase(self):
        total = len(ROWS) * STEP + FINALE
        t = (time.monotonic() - self.t0) % total
        return t, int(t // STEP) if t < len(ROWS) * STEP else len(ROWS)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        t, active = self._phase()
        if self.on_row and active != getattr(self, "_last_row", None):
            self._last_row = active
            self.on_row(active)

        # panel: a neutral, game-like settings screen
        bg = QPainterPath()
        bg.addRoundedRect(QRectF(0, 0, w, h), 14, 14)
        p.fillPath(bg, QColor(28, 22, 44))
        p.setPen(QColor(255, 255, 255, 120))
        f = QFont(self.font())
        f.setPixelSize(12)
        f.setWeight(QFont.DemiBold)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 1.2)
        p.setFont(f)
        p.drawText(QRectF(22, 14, w, 20), Qt.AlignLeft | Qt.AlignVCenter, "SETTINGS  ›  UI  ›  SUBTITLES & CAPTIONS")

        row_h, top = 40, 44
        lf = QFont(self.font())
        lf.setPixelSize(16)
        for i, (label, wrong, right, *_why) in enumerate(ROWS):
            y = top + i * row_h
            r = QRectF(14, y, w - 28, row_h - 4)
            local = t - i * STEP                          # time since this row became active
            is_active = i == active
            done = i < active or (is_active and local > STEP * 0.55)
            if is_active:
                a = _ease(local / 0.25)
                path = QPainterPath()
                path.addRoundedRect(r, 8, 8)
                p.fillPath(path, QColor(255, 255, 255, int(235 * a)))
            fg = QColor(30, 24, 40) if is_active else QColor(255, 255, 255, 225)
            p.setFont(lf)
            p.setPen(fg)
            p.drawText(r.adjusted(14, 0, 0, 0), Qt.AlignLeft | Qt.AlignVCenter, label)

            # value: the wrong one slides out, the right one slides in
            vx = r.right() - 214
            vr = QRectF(vx, r.top(), 120, r.height())
            p.save()
            p.setClipRect(vr)
            if i < active or active == len(ROWS):
                k = 1.0
            elif is_active:
                k = _ease((local - 0.35) / 0.35)
            else:
                k = 0.0
            off = k * r.height()
            p.setPen(fg)
            if k < 1:
                p.drawText(vr.translated(0, -off), Qt.AlignRight | Qt.AlignVCenter, wrong)
            if k > 0:
                p.setPen(self.accent if not is_active else QColor(30, 24, 40))
                p.drawText(vr.translated(0, r.height() - off), Qt.AlignRight | Qt.AlignVCenter, right)
            p.restore()
            # arrows
            p.setPen(QPen(fg, 1.6))
            ax = r.right() - 76
            cy = r.center().y()
            p.drawPolyline([QRectF(ax, cy - 5, 0, 0).topLeft(), QRectF(ax - 5, cy, 0, 0).topLeft(),
                            QRectF(ax, cy + 5, 0, 0).topLeft()])
            p.drawPolyline([QRectF(ax + 14, cy - 5, 0, 0).topLeft(), QRectF(ax + 19, cy, 0, 0).topLeft(),
                            QRectF(ax + 14, cy + 5, 0, 0).topLeft()])
            # check mark
            if done:
                ca = 1.0 if i < active or active == len(ROWS) else _ease((local - STEP * 0.55) / 0.2)
                c = QColor(self.accent)
                c.setAlpha(int(255 * ca))
                p.setPen(QPen(c, 2.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                x0 = r.right() - 22
                path = QPainterPath()
                path.moveTo(x0 - 6, cy)
                path.lineTo(x0 - 2, cy + 4)
                path.lineTo(x0 + 6, cy - 5)
                p.drawPath(path)

        # sample subtitle at the bottom; in the finale it turns into the translation
        sub_y = top + len(ROWS) * row_h + 14
        sf = QFont(self.font())
        sf.setPixelSize(17)
        p.setFont(sf)
        en, hu = "This is a subtitle.", "Ez egy felirat."
        fin = (t - len(ROWS) * STEP) / FINALE if active == len(ROWS) else 0.0
        k = _ease((fin - 0.15) / 0.12) if fin > 0 else 0.0
        text = hu if k > 0.5 else en
        fm = p.fontMetrics()
        tw = max(fm.horizontalAdvance(en), fm.horizontalAdvance(hu)) + 36
        box = QRectF((w - tw) / 2, sub_y, tw, 34)
        path = QPainterPath()
        path.addRoundedRect(box, 3, 3)
        p.fillPath(path, QColor(18, 18, 22, 235))
        alpha = int(255 * (abs(k - 0.5) * 2)) if 0 < k < 1 else 255
        p.setPen(QColor(255, 255, 255, alpha))
        p.drawText(box, Qt.AlignCenter, text)
        if fin > 0.3:
            pulse = 0.5 + 0.5 * math.sin((fin - 0.3) * 8)
            c = QColor(self.accent)
            c.setAlpha(int(90 + 120 * pulse))
            p.setPen(QPen(c, 2))
            p.drawRoundedRect(box.adjusted(-4, -4, 4, 4), 6, 6)


class GameSetupDialog(QDialog):
    def __init__(self, parent=None, accent="#f5b83d"):
        super().__init__(parent)
        hu = current_language() == "hu"
        self.setWindowTitle("Felirat beállítása a játékban" if hu else "Subtitle settings in the game")
        self.setModal(True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(12)
        title = QLabel("Állítsd be így a feliratot a játékban" if hu else "Set up the subtitles in the game like this")
        title.setStyleSheet("font-size: 19px; font-weight: 700;")
        sub = QLabel("A játék menüjében: Beállítások › UI › Subtitles & Captions (vagy hasonló). "
                     "E nélkül a fordítás pontatlan lehet, és kilátszhat az eredeti szöveg."
                     if hu else "In the game menu: Settings › UI › Subtitles & Captions (or similar). "
                     "Without this, translations can be inaccurate and the original may show through.")
        sub.setWordWrap(True)
        sub.setObjectName("muted")
        lay.addWidget(title)
        lay.addWidget(sub)
        self.anim = SetupAnimation(accent)
        lay.addWidget(self.anim, 1)
        self.why = QLabel()
        self.why.setWordWrap(True)
        self.why.setMinimumHeight(40)
        lay.addWidget(self.why)
        self.anim.on_row = self._row

        self.chk = QCheckBox("Beállítottam a játékban" if hu else "I've set up the game like this")
        lay.addWidget(self.chk)
        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel = QPushButton("Mégse" if hu else "Cancel")
        self.ok = QPushButton("Indítás" if hu else "Start")
        self.ok.setObjectName("primary")
        self.ok.setEnabled(False)
        self.ok.setStyleSheet("QPushButton:disabled { background: #3a3f48; color: #8d95a4; border-color: #3a3f48; }")
        self.chk.toggled.connect(self.ok.setEnabled)
        cancel.clicked.connect(self.reject)
        self.ok.clicked.connect(self.accept)
        btns.addWidget(cancel)
        btns.addWidget(self.ok)
        lay.addLayout(btns)
        self.resize(640, 600)

    def _row(self, i: int):
        hu = current_language() == "hu"
        if i < len(ROWS):
            label, _w, right, why_hu, why_en = ROWS[i]
            self.why.setText(f"<b>{label}: {right}</b> – {why_hu if hu else why_en}")
        else:
            self.why.setText("<b>Kész!</b> A SubBridge így pontosan letakarja és lefordítja a feliratot."
                             if hu else "<b>Done!</b> SubBridge can now cover and translate subtitles exactly.")

    def done(self, r):
        self.anim.timer.stop()
        super().done(r)
