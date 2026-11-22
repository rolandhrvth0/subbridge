from subbridge.pipeline.textclean import clean, has_real_text, split_speaker


def test_pipe_to_i():
    assert clean("Local: | know you can hear me.") == "Local: I know you can hear me."
    assert clean("Local: No! [ don't have to") == "Local: No! I don't have to"


def test_box_edge_artifacts_removed():
    assert clean("| Stranger: My wife...|") == "Stranger: My wife..."
    assert clean("Theo: Well take it easy, man. |") == "Theo: Well take it easy, man."


def test_whitespace_and_quotes():
    assert clean("Hey,\n  you   know’s") == "Hey, you know's"


def test_speaker_split():
    assert split_speaker("LENA: Let's go.") == ("Lena", "Let's go.")
    assert split_speaker("Tourist 2: Hey!") == ("Tourist 2", "Hey!")
    assert split_speaker("Time is 10:30 now") == (None, "Time is 10:30 now")
    assert split_speaker("This is a very long sentence that has: a colon") == (None, "This is a very long sentence that has: a colon")
    assert split_speaker("LENA: Let's go.", enabled=False) == (None, "LENA: Let's go.")


def test_has_real_text():
    assert has_real_text("Hey!")
    assert not has_real_text("|")
    assert not has_real_text("° ,")
