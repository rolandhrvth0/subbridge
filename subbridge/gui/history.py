"""Subtitle history of this session: read back what you missed, search, fix a translation, save to a file."""
from __future__ import annotations

import threading
import time
from html import escape

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QFileDialog, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QPushButton, QVBoxLayout)

from .. import report
from ..i18n import tr
from ..translate.corrections import corrections


class HistoryDialog(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle(tr("history_title"))
        self.resize(760, 620)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(10)
        head = QHBoxLayout()
        t = QLabel(tr("history_title"))
        t.setStyleSheet("font-size: 18px; font-weight: 700;")
        self.search = QLineEdit(placeholderText=tr("history_search"), clearButtonEnabled=True)
        self.search.setMaximumWidth(280)
        head.addWidget(t)
        head.addStretch(1)
        head.addWidget(self.search)
        lay.addLayout(head)
        lay.addWidget(QLabel(tr("history_hint"), objectName="small", wordWrap=True))
        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.list.setAlternatingRowColors(False)
        self.list.setSpacing(2)
        lay.addWidget(self.list, 1)
        self.chk_send = QCheckBox(tr("history_send_fix"), checked=True)
        lay.addWidget(self.chk_send)
        btns = QHBoxLayout()
        self.info = QLabel(objectName="small")
        self.btn_fix = QPushButton(tr("history_fix"))
        self.btn_copy = QPushButton(tr("copy"))
        self.btn_save = QPushButton(tr("history_save"))
        close = QPushButton(tr("close") if tr("close") != "close" else "OK", objectName="primary")
        btns.addWidget(self.info, 1)
        for b in (self.btn_fix, self.btn_copy, self.btn_save, close):
            btns.addWidget(b)
        lay.addLayout(btns)
        self.search.textChanged.connect(self.refresh)
        self.list.itemDoubleClicked.connect(lambda _i: self.fix())
        self.btn_fix.clicked.connect(self.fix)
        self.btn_copy.clicked.connect(self.copy)
        self.btn_save.clicked.connect(self.save)
        close.clicked.connect(self.accept)
        self.refresh()

    # ------------------------------------------------------------------ list
    def _rows(self):
        q = self.search.text().strip().lower()
        for m in self.win.history.values():
            if q and q not in (m.get("text", "") + " " + m.get("original", "") + " " + (m.get("speaker") or "")).lower():
                continue
            yield m

    def refresh(self, *_):
        at_end = self.list.verticalScrollBar().value() >= self.list.verticalScrollBar().maximum() - 4
        cur = self.list.currentItem().data(Qt.UserRole) if self.list.currentItem() else None
        self.list.clear()
        c = self.win.colors()
        n = 0
        for m in self._rows():
            who = m.get("zone_name") or m.get("speaker") or ""
            ts = time.strftime("%H:%M", time.localtime(m.get("_t", time.time())))
            own = m.get("engine") == "own"
            lbl = QLabel()
            lbl.setTextFormat(Qt.RichText)
            lbl.setWordWrap(True)
            lbl.setContentsMargins(10, 6, 10, 6)
            lbl.setText(
                f'<span style="color:{c["muted"]};font-size:11px">{ts}</span>&nbsp; '
                + (f'<b style="color:{c["accent"]}">{escape(who)}</b>&nbsp; ' if who else "")
                + f'<span style="font-size:15px;font-weight:600">{escape(m.get("text", ""))}</span>'
                + (f'&nbsp;<span style="color:{c["ok"]};font-size:11px">✓ {tr("history_own")}</span>' if own else "")
                + f'<br><span style="color:{c["muted"]};font-size:12.5px">{escape(m.get("original", ""))}</span>')
            it = QListWidgetItem()
            it.setData(Qt.UserRole, m["id"])
            it.setSizeHint(lbl.sizeHint())
            self.list.addItem(it)
            self.list.setItemWidget(it, lbl)
            if m["id"] == cur:
                self.list.setCurrentItem(it)
            n += 1
        self.info.setText(tr("history_count").format(n=n, own=corrections().count(self.win.profile.target_lang)))
        if at_end:
            self.list.scrollToBottom()

    def _selected(self):
        it = self.list.currentItem()
        return self.win.history.get(it.data(Qt.UserRole)) if it else None

    # ------------------------------------------------------------------ actions
    def fix(self):
        m = self._selected()
        if not m:
            return
        new, ok = QInputDialog.getMultiLineText(self, tr("history_fix"),
                                                f'{tr("history_fix_hint")}\n\n{m.get("original", "")}', m.get("text", ""))
        if not ok or new.strip() == m.get("text", "").strip():
            return
        tgt = self.win.profile.target_lang
        old = m.get("text", "")
        corrections().put(m.get("original", ""), tgt, new)
        m["text"], m["engine"] = new.strip(), "own"
        if self.chk_send.isChecked() and new.strip():
            data = {"app": report.VERSION, "kind": "correction", "src": self.win.profile.source_lang, "tgt": tgt,
                    "en": m.get("original", "")[:1000], "mt": old[:1000], "fix": new.strip()[:1000]}
            threading.Thread(target=lambda: self._send(data), daemon=True).start()
        self.refresh()

    @staticmethod
    def _send(data):
        try:
            report.send(data, timeout=15)
        except Exception:  # noqa: BLE001  (offline: the local fix works anyway)
            pass

    def _text(self, rows):
        out = []
        for m in rows:
            who = m.get("zone_name") or m.get("speaker") or ""
            out.append((f"{who}: " if who else "") + m.get("text", "") + "\n    " + m.get("original", ""))
        return "\n".join(out)

    def copy(self):
        from PySide6.QtGui import QGuiApplication
        m = self._selected()
        QGuiApplication.clipboard().setText(self._text([m] if m else list(self._rows())))

    def save(self):
        name = time.strftime("SubBridge-felirat-%Y%m%d-%H%M.txt")
        path, _ = QFileDialog.getSaveFileName(self, tr("history_save"), name, "Text (*.txt)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._text(list(self._rows())) + "\n")
