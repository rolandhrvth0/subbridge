"""Cleanup rules found on real gameplay OCR (text only, no game imagery)."""
import pytest

from subbridge.pipeline.textclean import Line, is_dialogue, split_lines


@pytest.mark.parametrize("raw,want", [
    ("a Fy Yeah, that's what it said.", "Yeah, that's what it said."),
    ("aa 2 Yeah, that's it. 5 This guy owns it.", "Yeah, that's it. This guy owns it."),
    ('i a i" Yeah, that\'s the one.', "Yeah, that's the one."),
    ("x «gf »Yeah, that's the one.", "Yeah, that's the one."),
    ("eee That's the name.", "That's the name."),
    ("Wait. 10 Minutes left.", "Wait. 10 Minutes left."),
    ("I I can't tell, bro.", "I I can't tell, bro."),
    ("Oh. I see.", "Oh. I see."),
    ("My man. We go now.", "My man. We go now."),
])
def test_junk_prefix(raw, want):
    assert [ln.text for ln in split_lines(raw, True, "en")] == [want]


@pytest.mark.parametrize("t", ["Turn Left 108 ft", "U-Turn Left 55 ft", "Keep Right '136 ft", "Turn Right 231 ft 7"])
def test_navigation_is_not_dialogue(t):
    assert not is_dialogue(Line(None, t), "en")


def test_real_turn_sentence_stays():
    assert is_dialogue(Line(None, "Turn the car around, now!"), "en")


@pytest.mark.parametrize("raw,want", [
    ("Where's the fuckin' maney?", "Where's the fuckin' money?"),
    ("See yeu soon.", "See you soon."),
    ("I was genna werk my way up.", "I was gonna work my way up."),
    ("We still don't know what's on the hard crive.", "We still don't know what's on the hard drive."),
    ("Nah, bro, lil homie tryna dip.", "Nah, bro, lil homie tryna dip."),     # street words stay
    ("Raina and Jason, pre-workout.", "Raina and Jason, pre-workout."),       # names / hyphens stay
])
def test_ocr_word_fix(raw, want):
    from subbridge.pipeline.textclean import fix_ocr_words
    assert fix_ocr_words(raw) == want
