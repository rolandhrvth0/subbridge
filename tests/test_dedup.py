from subbridge.pipeline.dedup import is_extension, similarity


def test_similarity_basics():
    assert similarity("Hello there.", "Hello there.") == 1.0
    assert similarity("Hello there.", "Hello there,") == 1.0          # punctuation ignored
    assert similarity("Hello there.", "Hellp there.") > 0.85           # single OCR error
    assert similarity("Hello there.", "Get in the car!") < 0.5


def test_is_extension():
    assert is_extension("You should hear", "You should hear how he's talking now")
    assert not is_extension("You should hear", "Something else entirely")
