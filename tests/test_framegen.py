"""Frame generation: duplicate detection, mode learning and the Game View hook-up."""
import numpy as np
import pytest

fg_mod = pytest.importorskip("subbridge.framegen")
if not fg_mod.available():
    pytest.skip("OpenCV not installed", allow_module_level=True)


def _scene(shift: int, w=640, h=360):
    """A textured picture moved right by ``shift`` px (a camera pan)."""
    rng = np.random.default_rng(1)
    base = (rng.random((h // 8, (w + 200) // 8, 3)) * 255).astype(np.uint8)
    import cv2
    big = cv2.resize(base, (w + 200, h), interpolation=cv2.INTER_CUBIC)
    return np.ascontiguousarray(big[:, 100 - shift:100 - shift + w])


def test_mid_frame_is_between():
    ip = fg_mod.Interpolator()
    a, b, truth = _scene(0), _scene(16), _scene(8)
    mid = ip.mid(a, b)
    err = np.abs(mid.astype(int) - truth).mean()
    blend = np.abs(((a.astype(int) + b) // 2) - truth).mean()
    assert err < blend * 0.7, (err, blend)


def test_duplicate_stream_becomes_60():
    g = fg_mod.FrameGen()
    shown = []
    for i in range(60):
        f = _scene(i)          # 30 unique pictures, each sent twice (60 Hz card, 30 fps game)
        shown += [len(g.push(f)), len(g.push(f))]
    assert g.mode == "dup"
    assert all(n == 1 for n in shown[-20:])          # one picture per 60 Hz slot
    assert g.stats["generated"] > 0


def test_true_60_passes_through():
    g = fg_mod.FrameGen()
    for i in range(60):
        g.push(_scene(i))
    assert g.mode == "pass"


def test_gameview_framegen(qapp_offscreen):
    from PySide6.QtGui import QImage
    from subbridge.gui.gameview import GameView

    class Sess:
        cb = None
        def attach_view(self, s): pass
        def set_frame_callback(self, cb): self.cb = cb
        def size(self): return (640, 360)

    s = Sess()
    v = GameView(s)
    assert s.cb is not None and v.fg_worker is not None
    for i in range(50):
        a = _scene(i)
        img = QImage(a.data, 640, 360, 640 * 3, QImage.Format_RGB888).copy()
        s.cb(img); s.cb(img)
        qapp_offscreen.processEvents()
        v.fg_worker.msleep(5)
    for _ in range(20):
        qapp_offscreen.processEvents()
        v.fg_worker.msleep(10)
    assert not v.fg_item.pixmap().isNull()
    v.close()
    assert s.cb is None
