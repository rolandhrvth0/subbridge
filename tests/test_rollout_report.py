import json
import time

import numpy as np

from subbridge import remote as rm
from subbridge import report
from subbridge.branding import VERSION
from subbridge.config import AppSettings


def _remote(tmp_path, monkeypatch, latest, bucket):
    monkeypatch.setattr(rm, "data_dir", lambda: tmp_path)
    r = rm.Remote()
    r.latest = latest
    r._state["bucket"] = bucket
    return r


def _next():
    a, b, c = (int(x) for x in VERSION.split("."))
    return f"{a}.{b}.{c + 1}"


def test_staged_rollout(tmp_path, monkeypatch):
    t0 = time.time()
    lt = {"version": _next(), "rollout": {"start": t0, "hours": 24, "from": 20}}
    early, late = _remote(tmp_path, monkeypatch, lt, 5), _remote(tmp_path, monkeypatch, lt, 90)
    assert early.update_available(t0 + 60)
    assert not late.update_available(t0 + 60)
    assert late.update_available(t0 + 24 * 3600 + 1)          # everyone after the rollout window


def test_pause_and_no_rollout_info(tmp_path, monkeypatch):
    assert _remote(tmp_path, monkeypatch, {"version": _next()}, 99).update_available()
    assert not _remote(tmp_path, monkeypatch, {"version": _next(), "paused": True}, 0).update_available()


def test_rollback_goes_to_older_version(tmp_path, monkeypatch):
    r = _remote(tmp_path, monkeypatch, {"version": "0.0.1", "replaces": [VERSION], "paused": True}, 99)
    assert r.update_available()
    assert not _remote(tmp_path, monkeypatch, {"version": "0.0.1", "replaces": ["9.9.9"]}, 0).update_available()


def test_report_hides_secrets_and_home():
    s = AppSettings()
    s.deepl_key, s.google_key = "SECRET-DEEPL", "SECRET-GOOGLE"
    d = report.build(s, None, "  nem megy  ", screens=[{"name": "x"}])
    txt = json.dumps(d)
    assert "SECRET-DEEPL" not in txt and "SECRET-GOOGLE" not in txt and s.pin not in json.dumps(d["settings"])
    assert d["note"] == "nem megy" and d["app"] == VERSION


def test_report_image_is_small_jpeg():
    img = report.encode_image((np.random.default_rng(0).random((600, 3440, 3)) * 255).astype(np.uint8))
    import base64
    raw = base64.b64decode(img)
    assert raw[:3] == b"\xff\xd8\xff" and len(raw) <= report.MAX_IMG
