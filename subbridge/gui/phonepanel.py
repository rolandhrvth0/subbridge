"""Translated in-game phone, shown as a chat card next to the phone in the picture."""
from __future__ import annotations

from html import escape

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..i18n import tr

CARD, TEXT, MUTED = QColor(250, 250, 252), "#15171c", "#6b7280"
OTHER_BG, MINE_BG, MINE_FG, REPLY = "#eceef2", "#2f6df6", "#ffffff", "#2f6df6"


class _Bubble(QLabel):
    def __init__(self, item: dict, px: int, width: int):
        super().__init__()
        self.setWordWrap(True)
        self.setTextFormat(Qt.RichText)
        f = QFont("Inter Variable")
        f.setPixelSize(px)
        self.setFont(f)
        name = f'<div style="color:{MUTED}; font-size:{int(px * 0.78)}px; font-weight:650">{escape(item["name"])}</div>' \
            if item.get("name") else ""
        self.setText(name + escape(item["text"]))
        pad = max(6, px // 2)
        # as wide as the text needs (up to 84 % of the card): QLabel's word wrap alone wraps far too early
        natural = QFontMetrics(f).horizontalAdvance(item["text"]) + 2 * (pad + 4) + 18
        w = int(min(natural, width * 0.84))
        self.setFixedWidth(w)
        self._w = w
        if item["kind"] == "reply":
            style = f"color:{REPLY}; border:2px solid {REPLY}; background:transparent;"
        elif item["mine"]:
            style = f"color:{MINE_FG}; background:{MINE_BG};"
        else:
            style = f"color:{TEXT}; background:{OTHER_BG};"
        self.setStyleSheet(f"QLabel {{ {style} border-radius:{px}px; padding:{pad}px {pad + 4}px; }}")
        self.ensurePolished()
        self.setMinimumHeight(self.heightForWidth(w) + 2)


class PhonePanel(QWidget):
    """Top-level click-through card (window sources) or a child of the Game View (capture cards)."""

    def __init__(self, parent=None):
        flags = Qt.Widget if parent else (Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                                          | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus
                                          | Qt.X11BypassWindowManagerHint)
        super().__init__(parent, flags)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.lay = QVBoxLayout(self)
        self.setStyleSheet("QLabel { background: transparent; }")      # never inherit the host's style
        self._key = None
        self.hide()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(self.rect().adjusted(1, 1, -1, -1), 18, 18)
        p.fillPath(path, CARD)

    def _clear(self):
        while self.lay.count():
            it = self.lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
            elif it.layout():
                while it.layout().count():
                    w = it.layout().takeAt(0).widget()
                    if w:
                        w.deleteLater()

    def show_state(self, state: dict | None, area: QRect, phone: QRect):
        """area: where the panel may go (screen or Game View); phone: the phone's rect in the same space."""
        if not state or not state.get("items"):        # never an empty white card
            self._key = None
            self.hide()
            return
        width = int(min(area.width() * 0.34, max(phone.width() * 1.3, 380)))
        px = max(13, min(26, phone.height() // 34))
        key = (state["header"], tuple((i["text"], i["kind"]) for i in state["items"]), width, px)
        if key != self._key:
            self._key = key
            self._clear()
            m = max(10, px)
            self.lay.setContentsMargins(m, m, m, m)
            self.lay.setSpacing(max(5, px // 2))
            head = QLabel(f'<span style="color:{MUTED}; font-size:{int(px * 0.75)}px; font-weight:700; '
                          f'letter-spacing:1px">{escape(tr("phone_translated").upper())}</span><br>'
                          f'<span style="color:{TEXT}; font-size:{int(px * 1.15)}px; font-weight:700">'
                          f'{escape(state["header"] or "")}</span>')
            head.setTextFormat(Qt.RichText)
            self.lay.addWidget(head)
            head.show()                     # children added to a visible widget stay hidden otherwise
            for it in state["items"]:
                row = QHBoxLayout()
                b = _Bubble(it, px, width)
                if it["mine"]:
                    row.addStretch(1)
                    row.addWidget(b)
                else:
                    row.addWidget(b)
                    row.addStretch(1)
                self.lay.addLayout(row)
                b.show()
            line = QFrame()
            line.setFixedHeight(0)
            self.lay.addWidget(line)
        self.setFixedWidth(width)
        self.lay.activate()
        need = self.lay.totalHeightForWidth(width) if self.lay.hasHeightForWidth() else self.lay.sizeHint().height()
        h = min(max(need, self.lay.sizeHint().height()), area.height())
        gap = int(area.width() * 0.015)
        x = phone.right() + gap if phone.right() + gap + width <= area.right() else max(area.left(), phone.left() - gap - width)
        y = max(area.top(), min(phone.top(), area.bottom() - h))
        self.setFixedHeight(h)
        self.move(x, y)
        self.show()
        self.raise_()
