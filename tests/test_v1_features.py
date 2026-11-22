import json

from subbridge.translate import argos
from subbridge.translate.corrections import Corrections, norm


def test_corrections_exact_sentence(tmp_path):
    c = Corrections(tmp_path / "c.json")
    c.put("You better have my money by Friday.", "hu", "Péntekre legyen meg a pénzem.")
    assert c.get("you better have my money by friday", "hu") == "Péntekre legyen meg a pénzem."
    assert c.get("You better have my money", "hu") is None          # never leaks into other sentences
    assert Corrections(tmp_path / "c.json").count() == 1             # saved
    c.put("You better have my money by Friday.", "hu", "")           # empty = remove
    assert c.get("You better have my money by Friday.", "hu") is None
    assert norm("  Hello,   THERE! ") == "hello,   there".replace("   ", " ")


def test_precise_model_preferred(tmp_path, monkeypatch):
    monkeypatch.setattr(argos, "models_dir", lambda: tmp_path)
    for name, prio in (("translate-en_hu-1_9", None), ("opus-big-en_hu-1", 10)):
        d = tmp_path / name
        (d / "model").mkdir(parents=True)
        (d / "model" / "model.bin").write_bytes(b"x")
        meta = {"from_code": "en", "to_code": "hu"}
        if prio:
            meta["priority"] = prio
        (d / "metadata.json").write_text(json.dumps(meta))
    assert argos.installed_models()[("en", "hu")].name == "opus-big-en_hu-1"
    assert argos.precise_installed("en", "hu")
    assert len(argos.PRECISE[("en", "hu")]["sha256"]) == 64


def test_engine_uses_own_correction(tmp_path, monkeypatch):
    from subbridge.translate import corrections as cm
    c = Corrections(tmp_path / "c.json")
    c.put("Follow that car!", "hu", "Kövesd azt a verdát!")
    monkeypatch.setattr(cm, "_inst", c)
    from subbridge.engine import Engine
    class P:
        source_lang, target_lang, glossary = "en", "hu", []
    e = Engine.__new__(Engine)
    e.profile = P()
    assert e.translate("Follow that car!", []) == ("Kövesd azt a verdát!", "own")
