"""In-game overlay: a click-through box drawn exactly over the game's own subtitle box, in the same
colour, with the translation inside.

Design rules (what makes it feel like the game's own subtitles):
  * the original is covered the instant a subtitle box appears – the English never flashes up;
  * the box does not jitter: small detection wobble is ignored, real size changes glide (120 ms);
  * the translation fades in (180 ms), the box fades out when the subtitle is gone (160 ms);
  * text wraps like the game does (about the original box width, at most ~60 % of the region),
    speaker name in the game's own colour.

The engine reads the game *window's* own pixels, so this overlay never ends up in its input."""
from __future__ import annotations

from html import escape

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRect, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QPainter
from PySide6.QtWidgets import QGraphicsOpacityEffect, QLabel, QWidget

PAD_X, PAD_Y, BLEED = 22, 3, 4
JITTER = 10           # px of detection wobble that never moves the box


def overlay_font_family() -> str:
    fams = set(QFontDatabase.families())
    for f in ("Figtree", "Inter Variable", "Inter"):
        if f in fams:
            return f
    return QFont().defaultFamily()


class OverlayBox(QWidget):
    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus
                         | Qt.X11BypassWindowManagerHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.bg = QColor(20, 20, 20)
        self.family = overlay_font_family()
        self.label = QLabel(self, textFormat=Qt.RichText, wordWrap=True, alignment=Qt.AlignCenter)
        self.label.setStyleSheet("background: transparent;")
        self.fx = QGraphicsOpacityEffect(self.label)
        self.label.setGraphicsEffect(self.fx)
        self.text_anim = QPropertyAnimation(self.fx, b"opacity", self, duration=120)
        self.text_anim.setEasingCurve(QEasingCurve.Linear)
        self.geo_anim = QPropertyAnimation(self, b"geometry", self, duration=120)
        self.geo_anim.setEasingCurve(QEasingCurve.OutCubic)
        self.geo_anim.valueChanged.connect(lambda _v: self._layout_label())
        self.fade = QPropertyAnimation(self, b"windowOpacity", self, duration=110)
        self.fade.setEasingCurve(QEasingCurve.InQuad)
        self.fade.finished.connect(self._faded)
        self._key = None
        self._target: QRect | None = None
        self._hiding = False

    # ------------------------------------------------------------------ painting
    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), self.bg)          # fully opaque: nothing of the original shows through

    def _layout_label(self):
        self.label.setGeometry(PAD_X, 0, max(10, self.width() - 2 * PAD_X), self.height())

    # ------------------------------------------------------------------ show / hide
    def show_box(self, box: dict, max_w: int, scale: float, dpr: float):
        x0, y0, x1, y1 = (v / dpr for v in box["rect"])
        x0, y0, x1, y1 = x0 - BLEED, y0 - BLEED / 2, x1 + BLEED, y1 + BLEED / 2
        px = max(13, int(box["px"] / dpr * 1.08 * scale))
        name = "#%02x%02x%02x" % tuple(box["name"]) if box.get("name") else "#f4d35e"
        rows = [(f'<span style="color:{name}">{escape(sp)}:</span> ' if sp else "") + escape(t)
                for sp, t in box["lines"] if t]           # no text yet: the box alone already hides the original
        html = (f'<div style="color:#ffffff; font-size:{px}px; font-weight:500; line-height:108%">'
                + "<br>".join(rows) + "</div>") if rows else ""
        self.bg = QColor(*box["bg"])
        font = QFont(self.family)
        font.setPixelSize(px)
        font.setWeight(QFont.Medium)
        self.label.setFont(font)

        # width: like the game – about the original box, wrapping onto a second line rather than
        # stretching across the screen; never narrower than the box it covers
        box_w = x1 - x0
        region_w = max(max_w / dpr, box_w)
        width, height = box_w, y1 - y0
        if html:
            # measure with the label itself (what is drawn), never with a separate document
            self.label.setWordWrap(False)
            self.label.setText(html)
            natural = self.label.sizeHint().width() + 2 * PAD_X + 4
            wrap_w = max(box_w, min(region_w, region_w * 0.62))
            width = min(max(box_w, natural), wrap_w)
            self.label.setWordWrap(True)
            need = self.label.heightForWidth(int(width - 2 * PAD_X)) + 2 * PAD_Y
            height = max(y1 - y0, need)
        cx = (x0 + x1) / 2
        target = QRect(int(cx - width / 2), int(y1 - height), int(width), int(height))   # bottom-aligned

        first = not self.isVisible() or self._hiding
        if first:
            self.fade.stop()
            self._hiding = False
            self.setWindowOpacity(1.0)
            self.geo_anim.stop()
            self.setGeometry(target)
            self._target = target
        elif self._target is not None and (target.left() < self._target.left() - 8 or target.right() > self._target.right() + 8
                                           or target.top() < self._target.top() - 8
                                           or target.bottom() > self._target.bottom() + 8):
            # the original grew (longer line, second line): the cover follows at once – never let it show
            self.geo_anim.stop()
            self.setGeometry(target.united(self._target) if tuple(box["lines"]) == self._key else target)
            self._target = self.geometry()
        elif self._target is None or (tuple(box["lines"]) != self._key and self._moved(self._target, target)) \
                or abs(target.bottom() - self._target.bottom()) > max(10, self._target.height() * 0.3):
            # same text: only a real vertical move (box pushed up) repositions – sideways detection wobble
            # never makes the subtitle shake
            # move at once (like the game): a gliding cover would let the original show for a moment
            self.geo_anim.stop()
            self.setGeometry(target)
            self._target = target
        self._layout_label()
        if html:                                   # safety net: the text must always fit inside the cover
            need = self.label.heightForWidth(self.label.width()) + 2 * PAD_Y
            if need > self.height():
                g = self.geometry()
                self.setGeometry(g.x(), g.bottom() + 1 - need, g.width(), need)
                self._target = self.geometry()
                self._layout_label()

        key = tuple(box["lines"])
        if key != self._key:
            new_text = [t for _, t in box["lines"] if t] != [t for _, t in (self._key or ()) if t]
            self._key = key
            if new_text:
                self.label.setText(html)
                self.text_anim.stop()
                self.fx.setOpacity(0.0)
                if html:
                    self.text_anim.setStartValue(0.25)          # like the old one: 25 % → 100 %
                    self.text_anim.setEndValue(1.0)
                    self.text_anim.start()
        self.update()
        if first:
            self.show()

    @staticmethod
    def _moved(a: QRect, b: QRect) -> bool:
        return max(abs(a.left() - b.left()), abs(a.right() - b.right()),
                   abs(a.top() - b.top()), abs(a.bottom() - b.bottom())) > JITTER

    def hide_box(self):
        if not self.isVisible() or self._hiding:
            return
        self._hiding = True
        self.fade.stop()
        self.fade.setStartValue(self.windowOpacity())
        self.fade.setEndValue(0.0)
        self.fade.start()

    def _faded(self):
        if self._hiding:
            self.hide()
            self._hiding = False
            self._key = None
            self._target = None
            self.setWindowOpacity(1.0)


def _screen_of(x: float, y: float):
    """(logical top-left, scale) of the monitor that holds this physical pixel. Qt keeps a monitor's
    top-left at its native position and scales only the size."""
    screens = QGuiApplication.screens() or []
    for sc in screens:
        g, d = sc.geometry(), sc.devicePixelRatio() or 1.0
        if g.x() <= x < g.x() + g.width() * d and g.y() <= y < g.y() + g.height() * d:
            return g.x(), g.y(), d
    sc = QGuiApplication.primaryScreen()
    if sc is None:
        return 0, 0, 1.0
    g = sc.geometry()
    return g.x(), g.y(), sc.devicePixelRatio() or 1.0


def _to_screen(box: dict):
    """Box in physical pixels -> the same box expressed so that show_box (which divides by the scale)
    lands on the right spot of the right monitor."""
    x0, y0, x1, y1 = box["rect"]
    ox, oy, d = _screen_of((x0 + x1) / 2, (y0 + y1) / 2)
    if d == 1.0 and not (ox or oy):
        return box, 1.0
    # logical = origin + (physical - origin) / d   ->   show_box gets logical * d
    lx = lambda v: (ox + (v - ox) / d) * d
    ly = lambda v: (oy + (v - oy) / d) * d
    b = dict(box)
    b["rect"] = (lx(x0), ly(y0), lx(x1), ly(y1))
    return b, d


class OverlayManager:
    def __init__(self):
        self.pool: list[OverlayBox] = []
        self.enabled = True
        self.scale = 1.0
        self.max_w = 1600

    def update(self, boxes: list[dict]):
        try:
            self._update(boxes)
        except Exception:  # noqa: BLE001 – a drawing error must show up in the log, not vanish
            import logging
            logging.getLogger(__name__).exception("overlay draw error")

    def _update(self, boxes: list[dict]):
        if not self.enabled:
            boxes = []
        # several monitors with different scaling: map every box with the monitor it is on
        # every box keeps its own window ("slot"): with several speakers nothing swaps or jumps
        want = {}
        for i, b in enumerate(boxes):
            want[b.get("slot", i)] = b
        need = max(want) + 1 if want else 0
        while len(self.pool) < need:
            self.pool.append(OverlayBox())
        for i, w in enumerate(self.pool):
            b = want.get(i)
            if b is not None:
                b, dpr = _to_screen(b)
                w.show_box(b, b.get("max_w", self.max_w), self.scale, dpr)
            else:
                w.hide_box()

    def clear(self):
        self.update([])
