"""Render UI screenshots without showing any window (QT_QPA_PLATFORM=offscreen).
Usage: QT_QPA_PLATFORM=offscreen python tools/screens.py <out dir> [light|dark]"""
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

# never touch the real user settings: work on a throw-away copy
_tmp = tempfile.mkdtemp(prefix="sb-shots-")
_real = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "subbridge"
if _real.exists():
    shutil.copytree(_real, Path(_tmp) / "subbridge")
os.environ["XDG_CONFIG_HOME"] = _tmp

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtGui import QFontDatabase  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from subbridge.config import AppSettings  # noqa: E402
from subbridge.paths import resource_dir  # noqa: E402

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
app = QApplication(sys.argv[:1])
QFontDatabase.addApplicationFont(str(resource_dir() / "assets" / "fonts" / "InterVariable.ttf"))
from subbridge.gui.main_window import MainWindow  # noqa: E402
from subbridge.gui.wizard import Wizard  # noqa: E402

st = AppSettings.load()
st.port = 8796
if len(sys.argv) > 2:
    st.theme = sys.argv[2]
win = MainWindow(st)
win.show()


def shoot():
    app.processEvents()
    win._idle_preview(force=True)
    for i, (sp, hu, en) in enumerate([("Local", "Mozgasd a kocsidat! Mozgás!", "Move your car! Move it!"),
                                      ("Stranger", "Ne kiabálj velem! Telefonon vagyok!", "Stop yelling at me! I'm on a call here!"),
                                      ("Lena", "Hallanod kéne, hogy beszél, tényleg döntött.",
                                       "You should hear how he's talking now, he's really made up his mind.")]):
        win._on_subtitle({"type": "line", "id": i + 1, "engine": "deepl", "latency_ms": 310, "speaker": sp,
                          "text": hu, "original": en})
    win._on_stats({"fps": 4.0, "ocr_ms": 31})
    win._on_clients(1, ["iPhone"])
    app.processEvents()
    win.grab().save(str(out / f"main-{st.theme}.png"))
    wiz = Wizard(win)
    wiz.show()
    for i in range(3):
        wiz._go(i)
        app.processEvents()
        time.sleep(0.2)
        app.processEvents()
        wiz.grab().save(str(out / f"wizard-{i + 1}-{st.theme}.png"))
    from subbridge.gui.settings_dialog import SettingsDialog
    dlg = SettingsDialog(win)
    dlg.show()
    for i, name in enumerate(dlg._ids):
        dlg.nav.setCurrentRow(i)
        app.processEvents()
        dlg.grab().save(str(out / f"settings-{name}-{st.theme}.png"))
    win.close()
    app.quit()


QTimer.singleShot(1500, shoot)
app.exec()
