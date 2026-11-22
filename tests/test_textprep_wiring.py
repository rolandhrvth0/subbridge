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
