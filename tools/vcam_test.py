"""End-to-end capture card test without hardware: synthetic game frames are played into a v4l2loopback
device (e.g. the OBS Virtual Camera) with ffmpeg, SubBridge opens it as a capture card, runs the engine
and screenshots the Game View.

Usage: QT_QPA_PLATFORM=offscreen python tools/vcam_test.py [/dev/video10] [out dir]

Note: v4l2loopback with exclusive_caps advertises placeholder formats, and Qt does not always negotiate
with it; if the stream does not start, test with any real UVC device (webcam) instead – capture cards
behave like those."""
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="sb-vcam-")

from docs_shots import FONT, draw_subtitle, scene  # noqa: E402

LINES = [("Lena:", "Get in the car, we're late. They won't wait for us."),
         ("Theo:", "Where are you? Everyone's waiting."),
         ("Lena:", "On my way, five minutes."),
         ("Theo:", "Don't forget the keys this time.")]


def make_frames(d: Path):
    base = scene(subtitle=False)
    n = 0
    for name, text in LINES:
        img = base.copy()
        draw_subtitle(img, name, text, (120, 200, 215) if name.startswith("Lena") else (215, 200, 120))
        for _ in range(6):                   # 3 s per subtitle at 2 fps
            img.save(d / f"{n:03d}.png")
            n += 1


def main():
    dev = sys.argv[1] if len(sys.argv) > 1 else "/dev/video10"
    out = Path(sys.argv[2] if len(sys.argv) > 2 else ROOT / "build" / "vcam")
    out.mkdir(parents=True, exist_ok=True)
    frames = Path(tempfile.mkdtemp(prefix="sb-frames-"))
    make_frames(frames)
    ff = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-re", "-stream_loop", "-1", "-framerate", "2",
                           "-i", str(frames / "%03d.png"), "-vf", "fps=30,format=yuyv422", "-f", "v4l2", dev])
    time.sleep(5)                            # let the loopback device take the producer's format
    try:
        run(dev, out)
    finally:
        ff.terminate()
        shutil.rmtree(frames, ignore_errors=True)


def run(dev, out):
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QFontDatabase
    from PySide6.QtWidgets import QApplication
    app = QApplication([])
    QFontDatabase.addApplicationFont(FONT)
    from subbridge.config import AppSettings
    from subbridge.gui.main_window import MainWindow
    st = AppSettings()
    st.port, st.first_run_done = 8790, True
    p = st.profile()
    p.region, p.engine = [0.0, 0.7, 1.0, 0.3], "argos"
    st.save_profile(p)
    win = MainWindow(st)
    win.show()
    got = []
    win.bridge.subtitle.connect(lambda m: got.append(m) if m.get("type") == "line" else None)

    def go():
        i = [k for k, s in enumerate(win.sources) if s["kind"] == "device" and s["ident"] == dev]
        if not i:
            print("device not found:", dev)
            app.quit()
            return
        win.cmb_source.setCurrentIndex(i[0])
        win._apply_source(win.sources[i[0]])
        QTimer.singleShot(1500, start)

    def start():
        sess = win.devices.sessions[dev]
        print("format:", sess.format or "auto", "| usb2:", sess.usb2)
        win.open_gameview()
        win.gameview.resize(1280, 720)
        win.toggle_run()
        QTimer.singleShot(8000, lambda: win.gameview.grab().save(str(out / "gameview.png")))
        QTimer.singleShot(13000, finish)

    def finish():
        for m in got:
            print(f"  {m['speaker']}: {m['original']}  ->  {m['text']}")
        print("lines:", len(got), "| overlay boxes:", sum(b.isVisible() for b in win.gameview.boxes) if win.gameview else 0)
        win.close()
        app.quit()

    QTimer.singleShot(800, go)
    app.exec()


if __name__ == "__main__":
    main()
