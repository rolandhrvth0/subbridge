from subbridge.translate.memory import lookup, sentence_keys, tm_key


def _t(*pairs):
    return {tm_key(e): h for e, h in pairs}


def test_glued_caller_label_and_junk():
    t = _t(("Right, Andy. The one with the clothes. Nice to meet you.", "Jó, Andy. Az, akinél a ruhák vannak. Örvendek."))
    assert lookup("Right, Andy. The one with the clothes. Nice to meet you. Unknown Be 00:08", t)
    assert lookup("Right, Andy. The one with the clothes. Nice to meet you. o™% q", t)


def test_two_lines_read_as_one():
    t = _t(("So, you still driving that piece of shit car?", "Szóval még mindig azzal a szar kocsival jársz?"),
           ("Get in your vehicle", "Szállj be a járművedbe"))
    assert lookup("So, you still driving that piece of shit car? Get in your vehicle", t) == \
        "Szóval még mindig azzal a szar kocsival jársz? Szállj be a járművedbe"


def test_unknown_sentence_is_not_guessed():
    t = _t(("Get in your vehicle", "Szállj be a járművedbe"))
    assert lookup("I have no idea what you mean here. Get in your vehicle", t) is None


def test_short_sentence_inside_a_read():
    t = _t(("I'll call you later tonight.", "Majd este hívlak."))
    assert lookup("Okay. I'll call you later tonight.", t) == "Oké. Majd este hívlak."


def test_sentence_keys():
    k = sentence_keys("Lucia, the bank just called. They're asking how I got all this money.",
                      "Lucia, hívott a bank. Azt kérdezik, honnan van ennyi pénzem.")
    assert len(k) == 2
