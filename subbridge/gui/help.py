from PySide6.QtWidgets import QDialog, QHBoxLayout, QListWidget, QTextBrowser

from ..branding import APP_NAME
from ..i18n import tr
from .. import i18n
from .help_content import HELP


class HelpDialog(QDialog):
    def __init__(self, parent=None, topic: str = ""):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} – {tr('help')}")
        self.resize(820, 560)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        self.list = QListWidget()
        self.list.setFixedWidth(250)
        self.text = QTextBrowser(openExternalLinks=True)
        self.text.document().setDefaultStyleSheet("p,li{line-height:150%;} code{font-family:monospace;}")
        lay.addWidget(self.list)
        lay.addWidget(self.text, 1)
        self.topics = HELP.get(i18n._lang, HELP["en"])
        for _key, title, _ in self.topics:
            self.list.addItem(title)
        self.list.currentRowChanged.connect(self._show)
        idx = next((i for i, t in enumerate(self.topics) if t[0] == topic), 0)
        self.list.setCurrentRow(idx)

    def _show(self, i):
        if 0 <= i < len(self.topics):
            _k, title, body = self.topics[i]
            self.text.setHtml(f"<h2>{title}</h2>" + body.replace("{app}", APP_NAME))
