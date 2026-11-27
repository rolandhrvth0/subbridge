import time
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


def _outlined_frame():
    from PIL import Image, ImageDraw, ImageFont
    rng = np.random.default_rng(1)
    bg = (rng.random((200, 1000, 3)) * 120 + 40).astype(np.uint8)          # busy game picture, no box
    im = Image.fromarray(bg)
    f = ImageFont.truetype("subbridge/assets/fonts/InterVariable.ttf", 34)
    d = ImageDraw.Draw(im)
    d.text((500, 140), "Boobie: Man, I got a date tonight!", font=f, fill="white", anchor="mm",
           stroke_width=2, stroke_fill="black")
    return np.asarray(im)


def test_text_boxes_finds_boxless_subtitle():
    rgb = _outlined_frame()
    boxes = co._text_boxes(rgb, 1000)
    assert len(boxes) == 1
    x0, y0, x1, y1 = boxes[0]
    assert x0 < 280 and x1 > 720 and y0 < 125 and y1 > 152        # the whole line is inside


def test_boxless_subtitle_is_covered(overlay):
    ov, out, mp = overlay
    ov.color = None
    mp.setattr(co.ClassicOverlay, "_read", staticmethod(lambda *a, **k: [("Boobie", "Man, I got a date tonight!")]))
    rgb = _outlined_frame()
    ov.process(rgb, (0, 0), (0, 0, 1000, 200), 1000, True, None, None, 0, "en", None)
    assert not ov.entries                                        # one read is not enough (fade-in fragments)
    ov.process(rgb, (0, 0), (0, 0, 1000, 200), 1000, True, None, None, 0, "en", None)
    assert len(ov.entries) == 1
    assert not out or not out[-1]                                # no empty box before the translation
    e = ov.entries[0]
    e.hu = [("Boobie", "Ember, randim van ma este!")]
    ov._emit()
    assert out[-1] and out[-1][0]["lines"][0][1].startswith("Ember")
    assert ov.color is None                                      # no box colour learnt from a box-less subtitle


def test_ultrawide_side_bars():
    """A 16:9 picture between black bars on an ultrawide screen: bars are measured, the subtitle is
    still found and the wrap width follows the picture, not the whole screen."""
    pic = _outlined_frame()                                              # 1000 px wide picture
    rgb = np.zeros((200, 1400, 3), np.uint8)
    rgb[:, 200:1200] = pic
    assert co._bars_w(rgb) == 200
    assert co._bars_w(pic) == 0
    boxes = co._text_boxes(rgb, 1000)
    assert len(boxes) == 1 and boxes[0][0] < 480 and boxes[0][2] > 920


def test_ultrawide_wrap_width(overlay):
    ov, out, mp = overlay
    ov.color = None
    mp.setattr(co.ClassicOverlay, "_read", staticmethod(lambda *a, **k: [("Boobie", "Man, I got a date tonight!")]))
    rgb = np.zeros((200, 1400, 3), np.uint8)
    rgb[:, 200:1200] = _outlined_frame()
    for _ in range(2):
        ov.process(rgb, (0, 0), (0, 0, 1400, 200), 1400, True, None, None, 0, "en", None)
    ov.entries[0].hu = [("Boobie", "Ember!")]
    ov._emit()
    assert out and out[-1] and out[-1][0]["max_w"] == int(1000 * 0.5 / 0.62)


def test_black_frame_has_no_bars():
    assert co._bars_w(np.zeros((100, 1400, 3), np.uint8)) == 0


def test_health_states(overlay):
    ov, _out, _mp = overlay
    now = time.time()
    ov._t = dict.fromkeys(ov._t, 0.0)
    assert ov.health() == "idle"
    ov._t["not_front"] = now
    assert ov.health() == "covered"
    ov._t["front"] = now
    assert ov.health() == "no_subtitle"
    ov._t["box"] = now
    assert ov.health() == "reading"
    ov._t["cover"] = now
    assert ov.health() == "ok"


def test_font_size_is_one_size(overlay):
    ov, _out, _mp = overlay
    for px in (30, 33, 29, 31):
        ov._steady_px(px)
    sizes = {ov._steady_px(px) for px in (28, 34, 30, 36, 27)}
    assert len(sizes) <= 2                        # the same size for every subtitle (median may move by 1)


def test_size_follows_a_real_change(overlay):
    ov, _out, _mp = overlay
    for px in (30, 30, 30, 30):
        ov._steady_px(px)
    for _ in range(6):
        last = ov._steady_px(60)
    assert last == 60                             # another resolution: six measurements in a row win


def test_two_speakers_restacked_no_line_twice(overlay):
    """The game shows 'Guard: … / Rosebud: …' in one box, then only Rosebud's line in a box lower down:
    the held old box must not keep showing Rosebud's line above the new one."""
    ov, out, mp = overlay
    two = [("Security Guard", "I'm talking! You didn't even ask me anything!"),
           ("Rosebud", "It's okay. It will all be over soon.")]
    _frame(ov, mp, [(300, 60, 700, 120)], two)
    ov.entries[0].hu = [("Biztonsági őr", "Beszélek!"), ("Rosebud", "Semmi baj.")]
    _frame(ov, mp, [(350, 130, 650, 160)], [two[1]])          # only Rosebud, in a new place
    shown = [b for b in out[-1] if any(t for _s, t in b["lines"])] if out[-1] else []
    texts = [t for b in out[-1] for _s, t in b["lines"]]
    assert len(ov.entries) == 1, [x.lines for x in ov.entries]
    assert "Semmi baj." not in texts or len(shown) <= 1


def test_box_growing_upwards_is_covered_at_once(overlay):
    """A second line appears above (two-line subtitle): the cover must reach the new top at once."""
    ov, out, mp = overlay
    _frame(ov, mp, [(400, 100, 600, 140)], [(None, "Yeah, okay. Sounds good.")])
    ov.entries[0].hu = [(None, "Igen, oké. Jól hangzik.")]
    ov.entries[0].shown_at -= 5
    _frame(ov, mp, [(380, 62, 620, 140)], [])        # grew upwards, unreadable this frame
    rects = [b["rect"] for b in out[-1]]
    assert any(r[1] <= 62 and r[3] >= 140 for r in rects), rects


def test_obs_gets_boxes_relative_to_the_picture(overlay):
    """The OBS page draws the translation in place: boxes go out as 0..1 of the source picture."""
    ov, out, mp = overlay
    got = []
    ov.eng = type("E", (), {"publish_boxes": lambda self, b: got.append(b)})()
    ov._src_wh = (1000, 500)
    _frame(ov, mp, [(400, 100, 600, 140)], [("Lucia", "Hey.")])      # band starts at y=0 in _frame
    ov._band = (0, 300, 1000, 200)                                     # the band read was y 300..500
    ov.entries[0].hu = [("Lucia", "Hé.")]
    ov._emit()
    b = got[-1][0]
    assert b["r"] == [0.4, 0.8, 0.6, 0.88]
    assert b["lines"] == [["Lucia", "Hé."]]
