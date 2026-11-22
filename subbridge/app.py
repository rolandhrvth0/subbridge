from __future__ import annotations

import logging
import os
import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFontDatabase, QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from .branding import APP_ID, APP_NAME
from .config import AppSettings
from .paths import config_dir, resource_dir


def _instance_name() -> str:
    return f"{APP_ID}-{os.environ.get('USER') or os.environ.get('USERNAME') or 'user'}"


def _forward_to_running(args: list[str]) -> bool:
    """Single instance: if SubBridge already runs, hand it our arguments and quit."""
    sock = QLocalSocket()
    sock.connectToServer(_instance_name())
    if not sock.waitForConnected(400):
        return False
    sock.write((" ".join(a for a in args if a.startswith("--")) or "--show").encode())
    sock.waitForBytesWritten(400)
    sock.disconnectFromServer()
    return True


def selftest(out_path: str | None) -> int:
    """Packaged-build check (used by CI on every platform): every part loads and works without a display."""
    import json
    import traceback
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    report, ok = {}, True

    def step(name, fn):
        nonlocal ok
        try:
            report[name] = fn() or "ok"
        except Exception:  # noqa: BLE001
            report[name] = "FAIL: " + traceback.format_exc(limit=3)
            ok = False

    app = QApplication([sys.argv[0]])
    step("fonts", lambda: str([QFontDatabase.addApplicationFont(str(resource_dir() / "assets" / "fonts" / f))
                               for f in ("InterVariable.ttf", "Figtree.ttf")]))
    def capture():
        from .capture import create_backend
        c = create_backend()
        return f"{type(c).__name__}: {len(c.list_screens())} screen(s)"
    step("capture", capture)
    def ocr():
        from PIL import Image, ImageDraw, ImageFont
        from .ocr import create_ocr
        e = create_ocr("tesseract", "en")
        if not e.available():
            raise RuntimeError("tesseract not available")
        im = Image.new("RGB", (900, 120), "white")
        ImageDraw.Draw(im).text((20, 30), "Hello there friend", fill="black",
                                font=ImageFont.truetype(str(resource_dir() / "assets" / "fonts" / "InterVariable.ttf"), 48))
        got = " ".join(l.text for l in e.recognize(im))
        if "Hello" not in got:
            raise RuntimeError(f"OCR read {got!r}; cmd={getattr(e, '_cmd', None)!r} tessdata={getattr(e, 'tessdata', None)!r} "
                               f"err={getattr(e, 'last_error', '')!r}")
        return got
    step("ocr", ocr)
    step("translate", lambda: __import__("ctranslate2").__version__)
    def server():
        from .server.server import SubtitleServer
        srv = SubtitleServer(18765, "123456", "t")
        if not srv.start():
            raise RuntimeError(srv.error)
        srv.stop()
    step("server", server)
    def gui():
        from .config import AppSettings
        from .gui.main_window import MainWindow
        st = AppSettings()
        st.port, st.online_feed = 18766, False
        w = MainWindow(st)
        w.engine.shutdown()
        w.server.stop()
    step("gui", gui)
    report["ok"] = ok
    text = json.dumps(report, indent=1)
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text)
    print(text)
    del app
    return 0 if ok else 1


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.FileHandler(config_dir() / "subbridge.log", encoding="utf-8"),
                                  logging.StreamHandler()])
    if sys.platform.startswith("linux") and os.environ.get("XDG_SESSION_TYPE") == "wayland":
        os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
    if "--selftest" in sys.argv:
        i = sys.argv.index("--selftest")
        return selftest(sys.argv[i + 1] if len(sys.argv) > i + 1 else None)
    # cheap MJPEG capture cards spam "Corrupt JPEG data" for harmless padding bytes
    os.environ.setdefault("QT_LOGGING_RULES", "qt.gui.imageio.jpeg=false;qt.multimedia.ffmpeg=false")
    app = QApplication(argv or sys.argv)
    app.setApplicationName(APP_NAME)
    app.setDesktopFileName(APP_ID)
    app.setWindowIcon(QIcon(str(resource_dir() / "server" / "web" / "icon-512.png")))
    QFontDatabase.addApplicationFont(str(resource_dir() / "assets" / "fonts" / "InterVariable.ttf"))
    QFontDatabase.addApplicationFont(str(resource_dir() / "assets" / "fonts" / "Figtree.ttf"))   # in-game overlay
    args = sys.argv[1:]
    if _forward_to_running(args):
        return 0

    from .gui.main_window import MainWindow
    from .gui.wizard import Wizard
    settings = AppSettings.load()
    win = MainWindow(settings)
    win.show()
    if not settings.first_run_done or "--wizard" in sys.argv:
        wiz = Wizard(win)
        if wiz.exec():
            settings.first_run_done = True
            settings.save()
            if not win.engine.running:
                win.toggle_run()
        else:
            settings.first_run_done = True
            settings.save()

    def handle(cmd: str):
        logging.getLogger("subbridge").info("command %r (running=%s)", cmd, win.engine.running)
        if "--start" in cmd and not win.engine.running and win.profile.source_kind:
            win.toggle_run()
        if "--show" in cmd or "--start" in cmd and not win.isVisible():
            win.showNormal()
            win.raise_()

    # "--start": begin translating right away (used by the Remote Play launcher); later launches only signal us
    server = QLocalServer()
    QLocalServer.removeServer(_instance_name())
    server.listen(_instance_name())

    def on_conn():
        c = server.nextPendingConnection()
        c.waitForReadyRead(400)
        handle(bytes(c.readAll()).decode(errors="ignore"))
        c.close()
    server.newConnection.connect(on_conn)
    if "--start" in args and settings.first_run_done:
        QTimer.singleShot(800, lambda: handle("--start"))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
