"""'Send a bug report' dialog: description, optional contact, optional picture – then one click."""
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton,
                               QVBoxLayout)

from .. import report
from ..i18n import tr


class _Sig(QObject):
    done = Signal(str, str)          # id, error


class ReportDialog(QDialog):
    def __init__(self, win, note: str = ""):
        super().__init__(win)
        self.win = win
        self.setWindowTitle(tr("report_title"))
        self.setModal(True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 18)
        lay.setSpacing(10)
        t = QLabel(tr("report_title"))
        t.setStyleSheet("font-size: 18px; font-weight: 700;")
        intro = QLabel(tr("report_intro"), objectName="muted", wordWrap=True)
        self.note = QPlainTextEdit(placeholderText=tr("report_note_ph"))
        self.note.setPlainText(note)
        self.note.setMinimumHeight(110)
        self.contact = QLineEdit(placeholderText=tr("report_contact_ph"))
        self.chk_img = QCheckBox(tr("report_image"), checked=True)
        self.what = QLabel(objectName="small", wordWrap=True)
        self.result = QLabel(wordWrap=True, textInteractionFlags=Qt.TextSelectableByMouse)
        self.result.hide()
        for w in (t, intro, self.note, self.contact, self.chk_img, self.what, self.result):
            lay.addWidget(w)
        btns = QHBoxLayout()
        btns.addStretch(1)
        self.btn_close = QPushButton(tr("cancel"))
        self.btn_send = QPushButton(tr("report_send"), objectName="primary")
        btns.addWidget(self.btn_close)
        btns.addWidget(self.btn_send)
        lay.addLayout(btns)
        self.chk_img.toggled.connect(self._update_what)
        self.btn_close.clicked.connect(self.reject)
        self.btn_send.clicked.connect(self._send)
        self.sig = _Sig()
        self.sig.done.connect(self._done)
        self._update_what()
        self.resize(560, 470)

    def _update_what(self):
        self.what.setText(tr("report_what").format(img=tr("report_what_img") if self.chk_img.isChecked() else ""))

    def _images(self):
        """(strip, frame thumbnail) of the selected source, or (None, None)."""
        win = self.win
        s = win.current_source()
        if not s or s.get("waiting"):
            return None, None
        try:
            frame = win.capture.grab(s["kind"], s["ident"])
            strip = None
            if frame is not None:
                h, w = frame.shape[:2]
                fx, fy, fw, fh = win.profile.region
                y0, y1 = int(fy * h), int((fy + fh) * h)
                strip = frame[max(0, y0):max(y0 + 8, y1)]
            return report.encode_image(strip), report.encode_image(frame, max_w=800)
        except Exception:  # noqa: BLE001  (a failed grab must not block the report)
            return None, None

    def _send(self):
        win = self.win
        screens = [{"name": sc.name(), "geo": list(sc.geometry().getRect()), "dpr": sc.devicePixelRatio(),
                    "primary": sc == QGuiApplication.primaryScreen()} for sc in QGuiApplication.screens()]
        s = win.current_source() or {}
        source = {"kind": s.get("kind"), "label": s.get("label"),
                  "region": list(win.profile.region)}
        try:
            source["size"] = list(win.capture.source_size(s["kind"], s["ident"])) if s.get("ident") is not None else None
        except Exception:  # noqa: BLE001
            pass
        strip, frame = self._images() if self.chk_img.isChecked() else (None, None)
        data = report.build(win.settings, win.engine, self.note.toPlainText(), self.contact.text(),
                            screens=screens, source=source, image=strip, frame=frame)
        self.btn_send.setEnabled(False)
        self.btn_send.setText(tr("report_sending"))

        def run():
            try:
                self.sig.done.emit(report.send(data), "")
            except Exception as e:  # noqa: BLE001
                self.sig.done.emit("", str(e)[:120])
        threading.Thread(target=run, name="report", daemon=True).start()

    def _done(self, rid: str, err: str):
        self.result.show()
        if err:
            self.result.setText(tr("report_fail").format(e=err))
            self.btn_send.setEnabled(True)
            self.btn_send.setText(tr("report_send"))
            return
        self.result.setText("<b>" + tr("report_ok").format(id=rid) + "</b>")
        self.btn_send.hide()
        self.btn_close.setText("OK")
