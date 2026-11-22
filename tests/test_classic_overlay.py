"""Regression: a subtitle box that grows (another speaker cuts in, longer line) must be covered in full
at once – even when the first OCR of the new box fails – so the English never shows around the old cover."""
import numpy as np
import pytest

from subbridge import classic_overlay as co


@pytest.fixture
def overlay(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(co.ClassicOverlay, "_load_color", lambda self: np.array([30, 30, 40]))
    monkeypatch.setattr(co.ClassicOverlay, "_save_color", lambda self, c: None)
    monkeypatch.setattr(co.ClassicOverlay, "_translate_entry", lambda self, e, gen, lines, ctx: None)
    out = []
    ov = co.ClassicOverlay(engine=None, emit=lambda boxes: out.append(boxes))
    yield ov, out, monkeypatch
    ov.pool.shutdown(wait=False)


def _frame(ov, mp, boxes, lines):
    mp.setattr(co, "find_boxes", lambda rgb, color=None: list(boxes))
    mp.setattr(co.ClassicOverlay, "_read", staticmethod(lambda *a, **k: list(lines)))
    rgb = np.zeros((200, 1000, 3), np.uint8)
    ov.process(rgb, (0, 0), (0, 0, 1000, 200), 1000, True, None, None, 0, "en", np.array([30, 30, 40]))


def test_grown_box_is_covered_even_if_ocr_fails(overlay):
    ov, out, mp = overlay
    _frame(ov, mp, [(450, 100, 550, 140)], [("Dre'Quan", "Yeah.")])
    e = ov.entries[0]
    e.hu = [("Dre'Quan", "Ja.")]
    e.shown_at -= 5                     # not "young" any more
    ov._emit()
    _frame(ov, mp, [(300, 98, 700, 142)], [])          # wider box, unreadable this frame
    last = out[-1]
    assert len(last) == 1
    x0, y0, x1, y1 = last[0]["rect"]
    assert x0 <= 300 and x1 >= 700, last[0]["rect"]
    assert all(not t for _, t in last[0]["lines"]), "old translation must not sit on the new text"


def test_same_box_keeps_translation(overlay):
    ov, out, mp = overlay
    _frame(ov, mp, [(450, 100, 550, 140)], [("Dre'Quan", "Yeah.")])
    e = ov.entries[0]
    e.hu = [("Dre'Quan", "Ja.")]
    e.shown_at -= 5
    _frame(ov, mp, [(451, 100, 549, 140)], [("Dre'Quan", "Yeah.")])   # detection wobble only
    assert ov.entries[0].hu == [("Dre'Quan", "Ja.")]


def test_font_size_stays_steady(overlay):
    ov, _out, _mp = overlay
    for px in (30, 31, 30):
        assert ov._steady_px(px) == px
    assert ov._steady_px(80) <= 31 * 1.2          # a two-line box read as one line: no giant text
    assert ov._steady_px(10) >= 30 * 0.8          # a cut-off box: no tiny text


def test_small_wobble_does_not_move_the_box(overlay):
    ov, out, mp = overlay
    _frame(ov, mp, [(450, 100, 550, 140)], [("A", "Hi.")])
    e = ov.entries[0]
    e.hu = [("A", "Szia.")]
    e.shown_at -= 5
    n = len(out)
    _frame(ov, mp, [(447, 104, 553, 145)], [("A", "Hi.")])          # a few px of detection wobble
    assert ov.entries[0].rect == (450, 100, 550, 140)
    assert len(out) == n                                             # nothing re-emitted: no jump


def test_stats_line_is_logged(overlay, caplog):
    import logging
    ov, _out, _mp = overlay
    ov._stat_t0 -= 31
    with caplog.at_level(logging.INFO):
        ov._stat_tick()
    assert any("overlay:" in r.getMessage() for r in caplog.records)
    assert ov.stats["ticks"] == 0


def test_overlay_maps_box_to_its_monitor(monkeypatch):
    from subbridge.gui import overlay as ov

    class G:
        def __init__(s, x, y, w, h): s._r = (x, y, w, h)
        def x(s): return s._r[0]
        def y(s): return s._r[1]
        def width(s): return s._r[2]
        def height(s): return s._r[3]

    class Sc:
        def __init__(s, g, d): s._g, s._d = g, d
        def geometry(s): return s._g
        def devicePixelRatio(s): return s._d

    left = Sc(G(0, 0, 1920, 1080), 1.0)                   # 100 % monitor
    right = Sc(G(1920, 0, 2560, 1440), 1.5)               # 150 % monitor, native 3840x2160
    monkeypatch.setattr(ov.QGuiApplication, "screens", staticmethod(lambda: [left, right]))
    monkeypatch.setattr(ov.QGuiApplication, "primaryScreen", staticmethod(lambda: left))
    b, d = ov._to_screen({"rect": (1920 + 1500, 1800, 1920 + 2300, 1900), "px": 45})
    assert d == 1.5
    x0 = b["rect"][0] / d                                    # what show_box will use (logical)
    assert abs(x0 - (1920 + 1000)) < 1                      # 1500 native px into the 150 % monitor = 1000 logical
    b2, d2 = ov._to_screen({"rect": (100, 900, 600, 960), "px": 30})
    assert d2 == 1.0 and b2["rect"] == (100, 900, 600, 960)


def test_wrong_remembered_colour_is_relearnt(overlay):
    ov, out, mp = overlay
    old, new = np.array([49, 43, 41]), np.array([24, 24, 30])
    ov.color = old
    ov._last_box_t -= 10                                   # nothing found with the old colour for a while
    mp.setattr(co, "box_color", lambda px: new)
    mp.setattr(co, "find_boxes", lambda rgb, color=None: [(450, 100, 550, 140)]
               if color is not None and np.array_equal(color, new) else [])
    mp.setattr(co.ClassicOverlay, "_read", staticmethod(lambda *a, **k: [("A", "Hello there.")]))
    rgb = np.zeros((200, 1000, 3), np.uint8)
    ov.process(rgb, (0, 0), (0, 0, 1000, 200), 1000, True, None, None, 0, "en", old)
    assert len(ov.entries) == 1 and out and out[-1]       # the subtitle is covered
    assert np.array_equal(ov.color, new)                  # and the new colour is remembered


def test_colour_not_relearnt_without_text(overlay):
    ov, out, mp = overlay
    old, new = np.array([49, 43, 41]), np.array([200, 0, 200])     # e.g. neon, no subtitle in it
    ov.color = old
    ov._last_box_t -= 10
    mp.setattr(co, "box_color", lambda px: new)
    mp.setattr(co, "find_boxes", lambda rgb, color=None: [(450, 100, 550, 140)]
               if color is not None and np.array_equal(color, new) else [])
    mp.setattr(co.ClassicOverlay, "_read", staticmethod(lambda *a, **k: []))
    ov.process(np.zeros((200, 1000, 3), np.uint8), (0, 0), (0, 0, 1000, 200), 1000, True, None, None, 0, "en", old)
    assert np.array_equal(ov.color, old)
