"""'Start the Game View' – asked every time the Game View opens (can be switched off): picture mode (native or
DLSS 5 with a style) with a preview of the card's current picture in each mode, and frame generation."""
from __future__ import annotations

import threading

import numpy as np
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QGuiApplication, QImage, QPixmap
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel, QPushButton,
                               QRadioButton, QVBoxLayout)

from ..i18n import tr

MODES = [("native", None), ("dlss_natural", 1), ("dlss_cinematic", 2), ("dlss_standard", 0)]


class _Bridge(QObject):
    ready = Signal(str, object)


class LaunchDialog(QDialog):
    def __init__(self, main, session):
        super().__init__(main)
        from .. import fgmodes, neural
        self.main, self.p = main, main.profile
        self.setWindowTitle(tr("ld_title"))
        self.setMinimumWidth(1150)
        self.frame = None
        try:
            self.frame = session.latest()                       # RGB, the card's current picture
        except Exception:  # noqa: BLE001
            pass
        self.dlss = neural.available() and self.frame is not None
        self.previews: dict[str, QImage] = {}
        self.bridge = _Bridge()
        self.bridge.ready.connect(self._got)
        self.worker = None
        self._busy = False

        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 20)
        root.setSpacing(14)
        root.addWidget(QLabel(tr("ld_title"), objectName="pageTitle"))
        root.addWidget(QLabel(tr("ld_sub"), objectName="pageSub", wordWrap=True))
        cols = QHBoxLayout()
        cols.setSpacing(22)
        root.addLayout(cols, 1)

        # left: preview + mode buttons
        left = QVBoxLayout()
        left.setSpacing(10)
        self.img = QLabel(alignment=Qt.AlignCenter, objectName="preview")
        self.img.setFixedSize(704, 396)
        left.addWidget(self.img)
        seg = QHBoxLayout()
        seg.setSpacing(6)
        self.mode_group = QButtonGroup(self)
        self.mode_btns = {}
        for key, _style in MODES:
            if key != "native" and not neural.available():
                continue
            b = QPushButton(tr(f"ld_{key}"), objectName="seg")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self._select(k))
            self.mode_group.addButton(b)
            self.mode_btns[key] = b
            seg.addWidget(b)
        seg.addStretch(1)
        left.addLayout(seg)
        self.cap = QLabel(objectName="small", wordWrap=True)
        left.addWidget(self.cap)
        if not neural.available():
            left.addWidget(QLabel(tr("ld_no_dlss"), objectName="small", wordWrap=True))
        cols.addLayout(left)

        # right: frame generation
        right = QVBoxLayout()
        right.setSpacing(8)
        right.addWidget(QLabel(tr("ld_fg"), objectName="h2"))
        fi = fgmodes.info()
        can_fg = fgmodes.info().resolve("auto") != "off" or "lsfg" in fi.choices()
        hz = 60.0
        sc = QGuiApplication.primaryScreen()
        if sc is not None and sc.refreshRate() > 1:
            hz = sc.refreshRate()
        self.fg_group = QButtonGroup(self)
        self.fg_btns = {}
        cur = 0 if self.p.framegen == "off" else int(self.p.fg_multiplier)
        for mult in (0, 2, 3, 4):
            fps = 30 * mult if mult else 30
            good = mult and abs((hz / fps) - round(hz / fps)) < 0.05
            text = tr("ld_fg_off") if not mult else tr("ld_fg_n", fps=fps, m=mult)
            if good:
                text += "  ·  " + tr("ld_fg_good", hz=round(hz))
            r = QRadioButton(text)
            r.setEnabled(mult == 0 or can_fg)
            r.setChecked(mult == cur or (mult == 0 and not can_fg))
            self.fg_group.addButton(r, mult)
            self.fg_btns[mult] = r
            right.addWidget(r)
            right.addWidget(QLabel(tr("ld_fg_off_sub") if not mult else tr("ld_fg_sub"), objectName="small",
                                   wordWrap=True))
        if not can_fg:
            right.addWidget(QLabel(tr("ld_fg_none"), objectName="small", wordWrap=True))
        right.addSpacing(10)
        sep = QFrame(objectName="rowSep")
        right.addWidget(sep)
        right.addWidget(QLabel(tr("ld_lat"), objectName="h2"))
        self.lat = QLabel(objectName="muted", wordWrap=True)
        right.addWidget(self.lat)
        right.addStretch(1)
        self.fg_group.idToggled.connect(lambda *_: self._latency())
        cols.addLayout(right, 1)

        bottom = QHBoxLayout()
        self.chk_ask = QCheckBox(tr("ld_ask"), checked=self.p.ask_launch)
        bottom.addWidget(self.chk_ask)
        bottom.addStretch(1)
        cancel = QPushButton(tr("cancel"))
        cancel.clicked.connect(self.reject)
        go = QPushButton(tr("ld_go"), objectName="primary")
        go.setMinimumWidth(170)
        go.clicked.connect(self.accept)
        go.setDefault(True)
        bottom.addWidget(cancel)
        bottom.addWidget(go)
        root.addLayout(bottom)

        start = "native"
        if self.p.neural and neural.available():
            start = {1: "dlss_natural", 2: "dlss_cinematic", 0: "dlss_standard"}.get(self.p.nr_style, "dlss_natural")
        self._select(start)

    # ---------------------------------------------------------------- preview
    def _select(self, key: str):
        self.mode = key
        if key in self.mode_btns:
            self.mode_btns[key].setChecked(True)
        self.cap.setText(tr(f"ld_{key}_cap"))
        self._latency()
        if self.frame is None:
            self.img.setText(tr("ld_no_picture"))
            return
        if key == "native":
            self._show(self._qimage(self.frame))
            return
        if key in self.previews:
            self._show(self.previews[key])
            return
        self.img.setText(tr("ld_computing"))
        if not self._busy:
            self._busy = True
            style = dict(MODES)[key]
            threading.Thread(target=self._compute, args=(key, style), daemon=True).start()

    def _compute(self, key, style):
        from .. import neural
        try:
            h, w = self.frame.shape[:2]
            if self.worker is None:
                self.worker = neural.NeuralWorker(w, h)
                import time
                t0 = time.time()
                while self.worker.starting and time.time() - t0 < 60:
                    time.sleep(0.05)
            self.worker.set_look(style, self.p.nr_intensity, self.p.nr_skin)
            rgba = np.dstack([self.frame, np.full(self.frame.shape[:2], 255, np.uint8)])
            out = self.worker.process(np.ascontiguousarray(rgba))
            self.bridge.ready.emit(key, None if out is None else np.ascontiguousarray(out[..., :3]))
        except Exception:  # noqa: BLE001
            self.bridge.ready.emit(key, None)

    def _got(self, key, rgb):
        self._busy = False
        if rgb is not None:
            self.previews[key] = self._qimage(rgb)
        if self.mode == key:
            if key in self.previews:
                self._show(self.previews[key])
            else:
                self.img.setText(tr("ld_failed"))
        elif self.mode not in self.previews and self.mode != "native":
            self._select(self.mode)                              # the user moved on meanwhile

    @staticmethod
    def _qimage(rgb: np.ndarray) -> QImage:
        h, w = rgb.shape[:2]
        return QImage(np.ascontiguousarray(rgb).data, w, h, w * 3, QImage.Format_RGB888).copy()

    def _show(self, img: QImage):
        self.img.setPixmap(QPixmap.fromImage(img).scaled(self.img.size(), Qt.KeepAspectRatio,
                                                        Qt.SmoothTransformation))

    def _latency(self):
        fg = self.fg_group.checkedId() if hasattr(self, "fg_group") else 0
        ms = 0
        parts = []
        if getattr(self, "mode", "native") != "native":
            extra = 23 if self.p.nr_stable else 13
            ms += extra
            parts.append(tr("ld_lat_dlss", ms=extra))
        if fg and fg > 0:
            ms += 33
            parts.append(tr("ld_lat_fg"))
        self.lat.setText(tr("ld_lat_total", ms=ms) + ("\n" + "\n".join(parts) if parts else "\n" + tr("ld_lat_min")))

    # ---------------------------------------------------------------- result
    def apply(self):
        p = self.p
        p.neural = self.mode != "native"
        if p.neural:
            p.nr_style = dict(MODES)[self.mode]
        mult = self.fg_group.checkedId()
        if mult and mult > 0:
            p.fg_multiplier = mult
            if p.framegen == "off":
                p.framegen = "auto"
        else:
            p.framegen = "off"
        p.ask_launch = self.chk_ask.isChecked()

    def done(self, r):
        if self.worker is not None:
            w, self.worker = self.worker, None
            threading.Thread(target=w.close, daemon=True).start()
        super().done(r)
