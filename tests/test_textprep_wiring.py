"""The feed packs must actually be used: slang is rewritten before translating, post-fixes (incl. the
offensive-word safety net) run on every result – also on translations cached by older versions."""
import json
import types

from subbridge import engine as eng_mod
from subbridge.translate import textprep as tp_mod


def _packs(tmp_path, monkeypatch):
    d = tmp_path / "packs"
    d.mkdir()
    (d / "slang-en.json").write_text(json.dumps({"version": 2, "rules": [[r"\bnigg(?:a|er)\b", "bro"]]}))
    (d / "post.json").write_text(json.dumps({"version": 2, "rules": {"hu": [[r"\b[Nn]igger\w*", "haver"]]}}))
    monkeypatch.setattr(tp_mod, "data_dir", lambda: tmp_path, raising=False)
    monkeypatch.setattr(tp_mod, "_inst", None)


class FakeCache:
    def __init__(self, data=None):
        self.data = dict(data or {})

    def get(self, eid, src, tgt, text):
        return self.data.get(text)

    def put(self, eid, src, tgt, text, out):
        self.data[text] = out


class FakeEngine:
    id = "fake"

    def __init__(self):
        self.seen = []

    def translate(self, texts, src, tgt, context=None):
        self.seen += texts
        return ["Szia, " + t for t in texts]


class G:
    def before(self, t):
        return t

    def protect(self, t):
        return t, {}

    def after(self, t):
        return t


def test_slang_and_post_fix(tmp_path, monkeypatch):
    _packs(tmp_path, monkeypatch)
    monkeypatch.setattr(eng_mod.Glossary, "restore", staticmethod(lambda out, m: out))
    self = types.SimpleNamespace(cache=FakeCache({"old line": "Ez a nigger volt."}))
    fe = FakeEngine()
    out = eng_mod.Engine._translate_text(self, fe, "Yo nigga", "en", "hu", G(), [])
    assert fe.seen == ["Yo bro"]                                   # slang rewritten before translating
    cached = eng_mod.Engine._translate_text(self, fe, "old line", "en", "hu", G(), [])
    assert "nigger" not in cached.lower() and "haver" in cached    # old cached result fixed too
    assert "nigg" not in out.lower()


def test_translation_memory_key_tolerates_ocr():
    from subbridge.translate.memory import tm_key
    a = tm_key("Yeah, could help take our mind off things.")
    assert a and a == tm_key("Yeah, could help take our mind eff things.") == tm_key("yeah could help take our mind off things")
    assert tm_key("This Giorgio Gallo owns Bilge Co.") == tm_key("This Giorgio Gallo owns Bilge Ca.")
    assert tm_key("Jason: We're done here.") == tm_key("We're done here.")
    assert tm_key("Go!") == ""
    assert tm_key("Lucia Yeah, I know.") == tm_key("Lucia: Yeah, I know.") == tm_key("Yeah, I know.")
    assert tm_key("Man, I hate those zombies.") != tm_key("I hate those zombies.")
    assert a != tm_key("Yeah, could help take our mind off the job.")


def test_translation_memory_lookup(tmp_path, monkeypatch):
    import json
    from subbridge.translate import memory as m
    (tmp_path / "packs").mkdir()
    (tmp_path / "packs" / "lines-hu.json").write_text(json.dumps(
        {"version": 99, "lines": {m.tm_key("Lose the cops"): "Rázd le a zsarukat"}}), encoding="utf-8")
    monkeypatch.setattr(m, "data_dir", lambda: tmp_path)
    mem = m.Memory()
    assert mem.get("Lose the caps", "hu") == "Rázd le a zsarukat"
    assert mem.get("Something else entirely", "hu") is None
