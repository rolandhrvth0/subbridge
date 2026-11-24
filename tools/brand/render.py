import sys
from PySide6.QtGui import QImage, QPainter, QGuiApplication
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtCore import Qt
app = QGuiApplication(sys.argv)
src, out, s = sys.argv[1], sys.argv[2], int(sys.argv[3])
r = QSvgRenderer(src)
im = QImage(s, s, QImage.Format_ARGB32); im.fill(Qt.transparent)
p = QPainter(im); p.setRenderHint(QPainter.Antialiasing); r.render(p); p.end(); im.save(out)
