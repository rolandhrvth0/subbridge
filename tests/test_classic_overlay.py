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
