import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import numpy as np
import pytest

from subbridge.translate.base import TranslationError
from subbridge.translate.google import GoogleCloudTranslator
from subbridge.translate.libre import LibreTranslator
from subbridge.translate.registry import create_translator, engine_key


class _Libre(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if body.get("api_key") == "bad":
            self.send_response(403)
            out = {"error": "Invalid API key"}
        else:
            self.send_response(200)
            out = {"translatedText": f"[{body['target']}] {body['q']}"}
        raw = json.dumps(out).encode()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


@pytest.fixture
def libre_url():
    srv = HTTPServer(("127.0.0.1", 0), _Libre)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_libre_roundtrip(libre_url):
    t = LibreTranslator(libre_url)
    assert t.translate(["Hello.", "Bye."], "en", "hu") == ["[hu] Hello.", "[hu] Bye."]
    with pytest.raises(TranslationError):
        LibreTranslator(libre_url, "bad").translate(["x"], "en", "hu")


def test_missing_keys_are_friendly_errors():
    for eng in ("deepl", "google", "libre"):
        with pytest.raises(TranslationError):
            create_translator(eng, {}, [])


def test_engine_key_tracks_relevant_settings():
    a = engine_key("google", {"google_key": "a", "deepl_key": "x"})
    assert a != engine_key("google", {"google_key": "b", "deepl_key": "x"})
    assert a == engine_key("google", {"google_key": "a", "deepl_key": "y"})


def test_google_parses_and_unescapes(monkeypatch):
    t = GoogleCloudTranslator("k")
    monkeypatch.setattr(t.http, "request", lambda *a, **k: (200, {"data": {"translations": [
        {"translatedText": "Ez &quot;jó&quot; &amp; szép"}]}}))
    assert t.translate(["x"], "en", "hu") == ['Ez "jó" & szép']
    monkeypatch.setattr(t.http, "request", lambda *a, **k: (403, {"error": {"message": "API disabled"}}))
    with pytest.raises(TranslationError, match="API disabled"):
        t.translate(["x"], "en", "hu")


def test_tls_cert(tmp_path, monkeypatch):
    pytest.importorskip("cryptography")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    from subbridge.server import tls
    c1, _ = tls.ensure_cert("192.168.1.50")
    m1 = os.path.getmtime(c1)
    assert tls.ensure_cert("192.168.1.50")[0] == c1 and os.path.getmtime(c1) == m1   # reused
    tls.ensure_cert("10.0.0.7")                                                        # new IP -> new cert
    from cryptography import x509
    import ipaddress
    cert = x509.load_pem_x509_certificate(open(c1, "rb").read())
    ips = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.IPAddress)
    assert ipaddress.ip_address("10.0.0.7") in ips
    assert tls.ssl_context("10.0.0.7")


def test_rapid_row_split_touching_lines():
    from subbridge.ocr.rapid import RapidEngine
    a = np.full((100, 400, 3), 255, np.uint8)
    a[10:45, 20:380] = 0          # line 1
    a[44:46, 20:60] = 0           # a descender touching line 2
    a[46:85, 20:300] = 0          # line 2
    rows = RapidEngine._rows(a)
    assert len(rows) == 2, rows


def test_settings_dialog_roundtrip(tmp_path, monkeypatch, qapp_offscreen):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    from subbridge.config import AppSettings
    from subbridge.gui.main_window import MainWindow
    from subbridge.gui.settings_dialog import SettingsDialog
    st = AppSettings()
    st.port = 8791
    win = MainWindow(st)
    try:
        dlg = SettingsDialog(win)
        dlg.cmb_tr.setCurrentIndex(dlg.cmb_tr.findData("libre"))
        dlg.ed_libre_url.setText("http://localhost:5000")
        dlg._add_rule({"find": "Theo", "stage": "keep"})
        dlg.sp_interval.setCurrentIndex(dlg.sp_interval.findData(500))
        dlg._save()
        p = AppSettings.load().profile()
        assert p.engine == "libre" and p.interval_ms == 500
        assert p.glossary[0]["find"] == "Theo"
        assert AppSettings.load().libre_url == "http://localhost:5000"
        win.new_profile.__func__   # exists
        win.settings.save_profile(type(p)(name="Másik"))
        win.switch_profile("Másik")
        assert win.profile.name == "Másik" and win.settings.active_profile == "Másik"
    finally:
        win.engine.shutdown()
        win.server.stop()
