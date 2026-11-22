"""News dialog: announcements from the project site (new features, tips, packs)."""
from __future__ import annotations

from html import escape

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from ..i18n import tr
from .widgets import Card


class NewsDialog(QDialog):
    def __init__(self, main):
        super().__init__(main)
        self.setWindowTitle(tr("news"))
        self.resize(640, 620)
        lang = main.settings.language
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 18)
        lay.addWidget(QLabel(tr("news"), objectName="h1"))
        lay.addWidget(QLabel(tr("news_sub"), objectName="small", wordWrap=True))
        sc = QScrollArea(widgetResizable=True)
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        col = QVBoxLayout(body)
        col.setContentsMargins(0, 8, 0, 8)
        col.setSpacing(12)
        remote = main.remote
        if remote.update_available():
            up = Card(tr("update_title", v=remote.latest.get("version", "")))
            notes = (remote.latest.get("notes") or {}).get(lang) or (remote.latest.get("notes") or {}).get("en", "")
            up.lay.addWidget(QLabel(escape(notes), wordWrap=True))
            if remote.latest.get("url"):
                b = QPushButton(tr("update_get"), objectName="primary")
                b.clicked.connect(lambda: main.open_url(remote.latest["url"]))
                row = QHBoxLayout()
                row.addWidget(b)
                row.addStretch(1)
                up.lay.addLayout(row)
            col.addWidget(up)
        if not remote.news:
            col.addWidget(QLabel(tr("news_empty"), objectName="muted", wordWrap=True))
        for n in remote.news:
            title = (n.get("title") or {}).get(lang) or (n.get("title") or {}).get("en", "")
            text = (n.get("body") or {}).get(lang) or (n.get("body") or {}).get("en", "")
            c = Card(title)
            if n.get("date"):
                c.lay.addWidget(QLabel(escape(n["date"]), objectName="small"))
            lb = QLabel(escape(text).replace("\n", "<br>"), wordWrap=True, textFormat=Qt.RichText)
            c.lay.addWidget(lb)
            if n.get("link"):
                link = QLabel(f'<a href="{escape(n["link"])}">{tr("news_more")}</a>', openExternalLinks=True)
                c.lay.addWidget(link)
            col.addWidget(c)
        col.addStretch(1)
        sc.setWidget(body)
        lay.addWidget(sc, 1)
        close = QPushButton(tr("close"))
        close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close)
        lay.addLayout(row)
        remote.mark_read()
