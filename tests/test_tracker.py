from subbridge.pipeline.textclean import Line
from subbridge.pipeline.tracker import LineTracker


def L(text, speaker=None):
    return Line(speaker, text)


def run(frames, **kw):
    tr = LineTracker(**kw)
    out = []
    for i, fr in enumerate(frames):
        out += [(e.kind, e.id, e.line.speaker, e.line.text) for e in tr.feed(fr, now=i * 0.25)]
    return out


def test_single_line_sent_once():
    out = run([[L("Get in the car!", "Lena")]] * 20)
    assert out == [("new", 1, "Lena", "Get in the car!")]


def test_needs_two_stable_reads():
    assert run([[L("Get in the car!")]]) == []


def test_two_speakers_on_screen_are_separate_lines_in_order():
    fr = [L("Move your car! Move it!", "Local"), L("Stop yelling at me!", "Stranger")]
    out = run([fr] * 5)
    assert [(k, s) for k, _, s, _ in out] == [("new", "Local"), ("new", "Stranger")]


def test_second_speaker_appears_later_first_not_resent():
    a = L("Move your car! Move it!", "Local")
    b = L("Stop yelling at me! I'm on a call here!", "Stranger")
    out = run([[a]] * 4 + [[a, b]] * 4 + [[b]] * 4)
    assert [t for _, _, _, t in out] == [a.text, b.text]


def test_ocr_noise_variants_do_not_duplicate():
    v = ["Hey, do you hear me?", "Hey, do you hear me?", "Hey, do yau hear me?", "Hey, do you hear me", "Hey, do you hear me?"]
    out = run([[L(x, "Local")] for x in v])
    assert len(out) == 1


def test_fade_in_partial_first_read():
    out = run([[L("Oh, rea", "Lena")], [L("Oh, really?", "Lena")], [L("Oh, really?", "Lena")]])
    assert out == [("new", 1, "Lena", "Oh, really?")]


def test_typewriter_growth_gives_update():
    out = run([[L("You mean the guy")]] * 3 + [[L("You mean the guy ripping him off")]] * 3)
    assert [k for k, *_ in out] == ["new", "update"]
    assert out[-1][3] == "You mean the guy ripping him off"


def test_line_shown_again_soon_is_not_resent():
    a = L("Uh huh.", "Theo")
    out = run([[a]] * 3 + [[]] * 12 + [[a]] * 3)
    assert len(out) == 1


def test_line_shown_again_much_later_is_resent():
    a = L("Uh huh.", "Theo")
    tr = LineTracker()
    ev = tr.feed([a], 0) + tr.feed([a], 0.25)
    for i in range(12):
        tr.feed([], 1 + i)
    ev += tr.feed([a], 200) + tr.feed([a], 200.25)
    assert [e.kind for e in ev] == ["new", "new"]


def test_speaker_found_later_updates_line():
    out = run([[L("Look what you did!")]] * 2 + [[L("Look what you did!", "Local")]] * 2)
    assert out[0][2] is None and out[-1] == ("update", 1, "Local", "Look what you did!")


def test_alternating_misreads_single_line():
    seq = [[L("48 Settings is great today.")], [L("4 Settings is great today.")]] * 6
    assert len(run(seq)) == 1


def test_same_speaker_new_sentence_is_new_line():
    out = run([[L("Yeah! Take it!", "Tourist")]] * 3 + [[L("Woo! Hoo-hoo, baby!", "Tourist")]] * 3)
    assert [k for k, *_ in out] == ["new", "new"]


def test_speaker_names_fixed():
    from subbridge.engine import SpeakerNames
    n = SpeakerNames()
    for _ in range(5):
        n.fix("Lena")
    n.fix("Local"); n.fix("Local")
    assert n.fix("Jena") == "Lena"
    assert n.fix("Loca") == "Local"
    assert n.fix("Bie Stranger") == "Bie Stranger"     # unknown yet
    for _ in range(3):
        n.fix("Stranger")
    assert n.fix("Bie Stranger") == "Stranger"
    assert n.fix("Theo") == "Theo"


def test_similar_real_speakers_not_merged():
    from subbridge.engine import SpeakerNames
    n = SpeakerNames()
    for _ in range(6):
        n.fix("Local")
    for _ in range(5):
        n.fix("Locals")
    assert n.fix("Locals") == "Locals"
    assert n.fix("Local") == "Local"


def test_last_ids_parallel_to_lines():
    from subbridge.pipeline.tracker import LineTracker
    from subbridge.pipeline.textclean import Line
    tr = LineTracker(stable_frames=2)
    a, b = Line("Theo", "Hey, you know."), Line("Lena", "Oh, really?")
    tr.feed([a, b], 0.0)
    assert tr.last_ids == [None, None]
    tr.feed([a, b], 0.3)
    assert all(tr.last_ids) and tr.last_ids[0] != tr.last_ids[1]
