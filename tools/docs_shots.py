"""Screenshots for the README / website with a synthetic game scene (no real game imagery).
Usage: QT_QPA_PLATFORM=offscreen python tools/docs_shots.py docs/img"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

_tmp = tempfile.mkdtemp(prefix="sb-docs-")
os.environ["XDG_CONFIG_HOME"] = _tmp
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FONT = str(ROOT / "subbridge" / "assets" / "fonts" / "InterVariable.ttf")


def scene(w=1920, h=1080, subtitle=True) -> Image.Image:
    """A dusk city street, drawn procedurally."""
    y = np.linspace(0, 1, h)[:, None]
    sky = np.stack([40 + 190 * (1 - y) ** 2, 30 + 110 * (1 - y) ** 2.4, 60 + 60 * (1 - y)], -1)
    img = Image.fromarray(np.repeat(sky, w, 1).clip(0, 255).astype(np.uint8))
    d = ImageDraw.Draw(img)
    rng = np.random.default_rng(7)
    x = 0
    while x < w:                                   # skyline
        bw, bh = int(rng.integers(90, 220)), int(rng.integers(260, 640))
        d.rectangle((x, h * 0.72 - bh, x + bw, h), fill=(22, 20, 34))
        for wy in range(int(h * 0.72 - bh) + 20, int(h * 0.7), 34):
            for wx in range(x + 14, x + bw - 14, 26):
                if rng.random() < 0.35:
                    d.rectangle((wx, wy, wx + 10, wy + 16), fill=(250, 200, 120))
        x += bw + int(rng.integers(4, 18))
    d.rectangle((0, h * 0.72, w, h), fill=(78, 74, 84))          # street
    for i in range(0, w, 160):
        d.rectangle((i, h * 0.86, i + 80, h * 0.87), fill=(200, 190, 140))
    img = img.filter(ImageFilter.GaussianBlur(1.2))
    if subtitle:
        draw_subtitle(img, "Lena:", "Get in the car, we're late. They won't wait for us.")
    return img


def draw_subtitle(img, name, text, color=(120, 200, 215)):
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(FONT, 40)
    full = f"{name} {text}"
    tw = d.textlength(full, font=f)
    w, h = img.size
    x0, y0 = (w - tw) / 2 - 18, h * 0.84
    d.rectangle((x0, y0, x0 + tw + 36, y0 + 62), fill=(24, 24, 30))
    d.text((x0 + 18, y0 + 8), name, font=f, fill=color)
    d.text((x0 + 18 + d.textlength(name + " ", font=f), y0 + 8), text, font=f, fill=(240, 240, 240))


def main():
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    s = scene()
    s.save(out / "scene.jpg", quality=90)

    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QFontDatabase, QImage
    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv[:1])
    QFontDatabase.addApplicationFont(FONT)
    from subbridge.config import AppSettings
    from subbridge.gui.main_window import MainWindow
    from subbridge.gui.overlay import OverlayBox
    from subbridge.gui.settings_dialog import SettingsDialog
    from subbridge.engine import read_lines, name_color, text_line_height
    from subbridge.ocr import create_ocr
    from subbridge.ocr.preprocess import PrepOptions

    for theme in ("dark", "light"):
        st = AppSettings()
        st.port, st.theme, st.first_run_done = 8792, theme, True
        p = st.profile()
        p.source_kind, p.region = "window", [0.15, 0.78, 0.7, 0.18]
        st.save_profile(p)
        win = MainWindow(st)
        win.resize(1180, 860)
        win.show()
        app.processEvents()
        arr = np.asarray(s)
        hh, ww = arr.shape[:2]
        win.preview.set_frame(arr[int(hh * 0.78):int(hh * 0.96), int(ww * 0.15):int(ww * 0.85)].copy(), [])
        win.lbl_region.setText("Felirat-terület kijelölve (1344×194 px)" if st.language == "hu" else "")
        win.cmb_source.clear()
        win.cmb_source.addItem("Remote Play")
        for i, (sp, hu, en) in enumerate([("Theo", "Hol vagy már? Mindenki rád vár.", "Where are you? Everyone's waiting."),
                                          ("Lena", "Úton vagyok, öt perc.", "On my way, five minutes."),
                                          ("Lena", "Szállj be a kocsiba, késésben vagyunk. Nem fognak ránk várni.",
                                           "Get in the car, we're late. They won't wait for us.")]):
            win._on_subtitle({"type": "line", "id": i + 1, "engine": "deepl", "latency_ms": 240, "speaker": sp,
                              "text": hu, "original": en})
        win._on_stats({"fps": 4.0, "ocr_ms": 28})
        win._on_clients(1, ["Pixel 8"])
        win.profile.source_kind, win.profile.overlay = "window", True
        win._update_tiles()
        app.processEvents()
        win.grab().save(str(out / f"desktop-{theme}.png"))
        if theme == "dark":
            dlg = SettingsDialog(win, "translate")
            dlg.show()
            app.processEvents()
            dlg.grab().save(str(out / "settings.png"))
            dlg.close()
        win.engine.shutdown()
        win.server.stop()
        win.close()

    # overlay before / after on the synthetic scene
    rgb = np.asarray(s)
    top = int(rgb.shape[0] * 0.78)                   # like the app: search inside the subtitle region
    _, boxes, color = read_lines(rgb[top:], create_ocr("tesseract", "en"), PrepOptions(), 60, True)
    boxes = [(x0, y0 + top, x1, y1 + top) for (x0, y0, x1, y1) in boxes]
    after = s.copy()
    for (x0, y0, x1, y1) in boxes[:1]:
        crop = rgb[y0:y1, x0:x1]
        w = OverlayBox()
        w.show_box({"rect": (x0, y0, x1, y1), "bg": tuple(int(v) for v in color), "name": name_color(crop),
                    "px": text_line_height(crop), "max_w": rgb.shape[1],
                    "lines": [("Lena", "Szállj be a kocsiba, késésben vagyunk. Nem fognak ránk várni.")]}, rgb.shape[1], 1.0, 1.0)
        w.text_anim.stop()
        w.fx.setOpacity(1.0)
        app.processEvents()
        g = w.geometry()
        qi = w.grab().toImage().convertToFormat(QImage.Format_RGB888)
        a = np.frombuffer(qi.constBits(), np.uint8).reshape(qi.height(), qi.bytesPerLine())[:, :qi.width() * 3]
        after.paste(Image.fromarray(a.reshape(qi.height(), qi.width(), 3).copy()), (g.x(), g.y()))
    s.crop((0, 600, 1920, 1080)).save(out / "overlay-before.jpg", quality=90)
    after.crop((0, 600, 1920, 1080)).save(out / "overlay-after.jpg", quality=90)
    QTimer.singleShot(0, app.quit)
    app.exec()
    shutil.rmtree(_tmp, ignore_errors=True)
    print("ok")


if __name__ == "__main__":
    main()
