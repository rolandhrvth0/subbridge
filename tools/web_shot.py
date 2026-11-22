"""Screenshot the phone page in an invisible Qt WebEngine view.
Usage: QT_QPA_PLATFORM=offscreen python tools/web_shot.py <url> <out.png> [w h] [js-to-run]"""
import sys

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication

url, out = sys.argv[1], sys.argv[2]
w, h = (int(sys.argv[3]), int(sys.argv[4])) if len(sys.argv) > 4 else (390, 844)
js = sys.argv[5] if len(sys.argv) > 5 else ""
app = QApplication(sys.argv[:1] + ["--disable-gpu"])
v = QWebEngineView()
v.resize(w, h)
v.load(QUrl(url))
v.show()


def run_js():
    if js:
        v.page().runJavaScript(js)


def shot():
    v.grab().save(out)
    app.quit()


QTimer.singleShot(3500, run_js)
QTimer.singleShot(5200, shot)
app.exec()
