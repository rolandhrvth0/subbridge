# PyInstaller spec – builds a one-folder app (Linux and Windows).
#   pyinstaller packaging/subbridge.spec --noconfirm
# Optional: put a tessdata/ folder (eng.traineddata) and, on Windows, a tesseract/ folder
# (tesseract.exe + DLLs) into packaging/bundle/ before building; they are shipped next to the app.
import os
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
PKG = ROOT / "subbridge"
BUNDLE = ROOT / "packaging" / "bundle"
win = sys.platform == "win32"

datas = [
    (str(PKG / "server" / "web"), "subbridge/server/web"),
    (str(PKG / "assets"), "subbridge/assets"),
]
if (BUNDLE / "tessdata").exists():
    datas.append((str(BUNDLE / "tessdata"), "subbridge/tessdata"))
if win and (BUNDLE / "tesseract").exists():
    datas.append((str(BUNDLE / "tesseract"), "tesseract"))

hidden = ["PySide6.QtNetwork", "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtSvg",
          "subbridge.capture.windows" if win else "subbridge.capture.x11",
          "aiohttp", "qrcode", "ctranslate2", "sentencepiece", "sacremoses", "subword_nmt"]

excludes = ["tkinter", "torch", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
            "PySide6.QtQuick3D", "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtPdf",
            "PySide6.QtBluetooth", "PySide6.QtLocation", "PySide6.QtPositioning", "PySide6.QtSensors",
            "PySide6.QtSerialPort", "PySide6.QtWebSockets", "PySide6.QtDesigner", "PySide6.QtQml",
            "PySide6.QtQuick", "PySide6.QtQuickWidgets", "rapidocr_onnxruntime", "onnxruntime",
            "matplotlib", "pytest", "IPython"]

a = Analysis([str(ROOT / "packaging" / "entry.py")], pathex=[str(ROOT)], datas=datas, hiddenimports=hidden,
             excludes=excludes, noarchive=False)
# drop Qt parts the app never uses (pulled in by plugins). Keep Qt6Qml/Quick: the FFmpeg media plugin links them.
_DROP = ("Qt6Pdf", "Qt6VirtualKeyboard", "Qt6WlShell", "Qt6EglFS", "Qt6EglFs",
         "libgtk-3", "libgdk-3", "qpdf", "virtualkeyboard", "platforminputcontexts", "qtquick", "libqgtk3",
         "Qt6Designer", "Qt6Test", "Qt6Sql", "Qt6Xml", "egldeviceintegrations", "wayland-decoration",
         "wayland-shell", "wayland-graphics")
a.binaries = [b for b in a.binaries if not any(k.lower() in b[0].lower() for k in _DROP)]
a.datas = [d for d in a.datas if not (d[0].startswith("PySide6/Qt/translations") and "qt_" not in d[0]
                                      and "qtbase_" not in d[0] and "qtmultimedia_" not in d[0])]
pyz = PYZ(a.pure)
icon = str(ROOT / "packaging" / ("subbridge.ico" if win else "subbridge.png"))
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="subbridge" if not win else "SubBridge",
          console=False, icon=icon if os.path.exists(icon) else None, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="SubBridge", upx=False)
