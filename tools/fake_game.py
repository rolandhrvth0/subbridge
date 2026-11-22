"""A stand-in for a Remote Play window: plays recorded frames full size, for testing without a console.
Usage: python tools/fake_game.py <folder> [fps]"""
import glob
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QLabel

app = QApplication(sys.argv)
files = sorted(glob.glob(f"{sys.argv[1]}/*eredeti*.jpg"))
fps = float(sys.argv[2]) if len(sys.argv) > 2 else 2
lbl = QLabel()
lbl.setWindowTitle("Remote Play Demo")
lbl.setAlignment(Qt.AlignCenter)
lbl.setStyleSheet("background:#000")
i = [0]


def nxt():
    lbl.setPixmap(QPixmap(files[i[0] % len(files)]))
    i[0] += 1


nxt()
lbl.resize(QPixmap(files[0]).size())
t = QTimer(timeout=nxt, interval=int(1000 / fps))
t.start()
lbl.show()
app.exec()
