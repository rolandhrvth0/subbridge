"""First-run wizard: source → region → phone. Designed so nobody can get lost."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QPushButton, QStackedWidget, QVBoxLayout, QWidget)

from ..branding import APP_NAME
from ..capture import CaptureError
from ..i18n import tr
from .icons import icon
from .widgets import PreviewWidget, QrWidget


class Wizard(QDialog):
    def __init__(self, main):
        super().__init__(main)
        self.main = main
        self.setWindowTitle(APP_NAME)
        self.setModal(True)
        self.resize(720, 560)
        c = main.colors()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 28, 32, 24)
        lay.setSpacing(6)
        h1 = QLabel(tr("wiz_title", app=APP_NAME), objectName="h1")
        sub = QLabel(tr("wiz_sub"), objectName="muted")
        lay.addWidget(h1)
        lay.addWidget(sub)
        dots = QHBoxLayout()
        dots.setSpacing(6)
        self.dots = []
        for _ in range(3):
            d = QFrame(objectName="stepDot")
            d.setFixedSize(36, 6)
            dots.addWidget(d)
            self.dots.append(d)
        dots.addStretch(1)
        lay.addSpacing(10)
        lay.addLayout(dots)
        lay.addSpacing(14)

        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)

        # step 1: source
        p1 = QWidget()
        l1 = QVBoxLayout(p1)
        l1.setContentsMargins(0, 0, 0, 0)
        l1.addWidget(QLabel(tr("wiz_step1"), objectName="h2"))
        t1 = QLabel(tr("wiz_step1_text"), objectName="muted", wordWrap=True)
        l1.addWidget(t1)
        self.lst = QListWidget()
        self.lst.setStyleSheet("QListWidget{border:1px solid %s;border-radius:10px;padding:6px;background:%s}"
                               "QListWidget::item{padding:10px;border-radius:8px}"
                               "QListWidget::item:selected{background:%s;color:%s}"
                               % (c["line"], c["surface"], c["sel"], c["text"]))
        self.lst.setFocusPolicy(Qt.NoFocus)
        for s in main.sources:
            label = s["label"] + (f"   ·   {tr('recommended')}" if s.get("stream") else "")
            it = QListWidgetItem(icon("window" if s["kind"] == "window" else "monitor", c["muted"], 18), label)
            self.lst.addItem(it)
        self.lst.setCurrentRow(max(0, main.cmb_source.currentIndex()))
        l1.addWidget(self.lst, 1)
        self.stack.addWidget(p1)

        # step 2: region
        p2 = QWidget()
        l2 = QVBoxLayout(p2)
        l2.setContentsMargins(0, 0, 0, 0)
        l2.addWidget(QLabel(tr("wiz_step2"), objectName="h2"))
        l2.addWidget(QLabel(tr("wiz_step2_text"), objectName="muted", wordWrap=True))
        self.btn_region = QPushButton(tr("select_region"), objectName="primary")
        self.btn_region.setIcon(icon("crop", c["accent_ink"], 16))
        self.btn_region.clicked.connect(self._select_region)
        r = QHBoxLayout()
        r.addWidget(self.btn_region)
        self.lbl_region = QLabel(objectName="small")
        r.addWidget(self.lbl_region, 1)
        l2.addLayout(r)
        self.preview = PreviewWidget()
        l2.addWidget(self.preview, 1)
        self.stack.addWidget(p2)

        # step 3: phone
        p3 = QWidget()
        l3 = QVBoxLayout(p3)
        l3.setContentsMargins(0, 0, 0, 0)
        l3.addWidget(QLabel(tr("wiz_step3"), objectName="h2"))
        l3.addWidget(QLabel(tr("wiz_step3_text"), objectName="muted", wordWrap=True))
        qr = QrWidget()
        qr.setFixedSize(230, 230)
        qr.set_data(f"{main.phone_url()}?k={main.settings.token}")
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(qr)
        row.addStretch(1)
        l3.addSpacing(8)
        l3.addLayout(row)
        info = QLabel(f"{main.phone_url().rstrip('/')}   ·   {tr('pin')}: <b>{main.settings.pin}</b>",
                      objectName="muted", alignment=Qt.AlignCenter)
        l3.addWidget(info)
        self.lbl_clients = QLabel(tr("clients_none"), objectName="small", alignment=Qt.AlignCenter)
        l3.addWidget(self.lbl_clients)
        main.bridge.clients.connect(self._clients)
        l3.addStretch(1)
        self.stack.addWidget(p3)

        nav = QHBoxLayout()
        self.btn_skip = QPushButton(tr("skip"), objectName="ghost")
        self.btn_back = QPushButton(tr("back"))
        self.btn_next = QPushButton(tr("next"), objectName="primary")
        self.btn_skip.clicked.connect(self.reject)
        self.btn_back.clicked.connect(lambda: self._go(self.stack.currentIndex() - 1))
        self.btn_next.clicked.connect(self._next)
        nav.addWidget(self.btn_skip)
        nav.addStretch(1)
        nav.addWidget(self.btn_back)
        nav.addWidget(self.btn_next)
        lay.addSpacing(12)
        lay.addLayout(nav)
        self._go(0)

    def _clients(self, n, names):
        self.lbl_clients.setText(tr("clients_n", n=n, names=", ".join(names)) if n else tr("clients_none"))

    def _go(self, i):
        i = max(0, min(2, i))
        self.stack.setCurrentIndex(i)
        for k, d in enumerate(self.dots):
            d.setProperty("active", k <= i)
            d.style().unpolish(d)
            d.style().polish(d)
        self.btn_back.setVisible(i > 0)
        self.btn_next.setText(tr("done") if i == 2 else tr("next"))
        if i == 1:
            self._refresh_preview()

    def _next(self):
        i = self.stack.currentIndex()
        if i == 0:
            row = self.lst.currentRow()
            if 0 <= row < len(self.main.sources):
                self.main.cmb_source.setCurrentIndex(row)
                self.main._apply_source(self.main.sources[row])
        if i == 2:
            self.accept()
            return
        self._go(i + 1)

    def _select_region(self):
        self.hide()
        self.main.hide()
        try:
            self.main.select_region()
        finally:
            self.main.show()
            self.show()
            self.raise_()
        self._refresh_preview()

    def _refresh_preview(self):
        m = self.main
        s = m.current_source()
        if not s:
            return
        try:
            sw, sh = m.capture.source_size(s["kind"], s["ident"])
            fx, fy, fw, fh = m.profile.region
            img = m.capture.grab(s["kind"], s["ident"], (int(fx * sw), int(fy * sh), int(fw * sw), int(fh * sh)))
            self.preview.set_frame(img, [])
            self.lbl_region.setText(tr("region_set", w=int(fw * sw), h=int(fh * sh)))
        except CaptureError as e:
            self.preview.clear_frame(m._err_text(e.code, str(e)))
