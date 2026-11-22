import hashlib
import io

import pytest

from subbridge import updater as up


class FakeRemote:
    def __init__(self, files):
        self.latest = {"version": "9.9.9", "files": files}

    def update_available(self):
        return True


class FakeResp(io.BytesIO):
    def __init__(self, data, url):
        super().__init__(data)
        self._url = url

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(up, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(up, "platform_key", lambda: "windows")
    return tmp_path


def _run(u):
    a = u.asset()
    assert a is not None
    u._download(a, "9.9.9")


def test_good_file_is_ready(env, monkeypatch):
    data = b"installer-bytes" * 1000
    url = "https://rolandhrvth.hu/subbridge/dl/SubBridge-Setup-9.9.9.exe"
    monkeypatch.setattr(up.urllib.request, "urlopen", lambda req, timeout=0: FakeResp(data, url))
    u = up.Updater(FakeRemote({"windows": {"url": url, "sha256": hashlib.sha256(data).hexdigest()}}))
    _run(u)
    assert u.ready_path and u.ready_path.read_bytes() == data and not u.error


def test_bad_checksum_is_discarded(env, monkeypatch):
    url = "https://rolandhrvth.hu/subbridge/dl/SubBridge-Setup-9.9.9.exe"
    monkeypatch.setattr(up.urllib.request, "urlopen", lambda req, timeout=0: FakeResp(b"tampered", url))
    u = up.Updater(FakeRemote({"windows": {"url": url, "sha256": "0" * 64}}))
    _run(u)
    assert u.ready_path is None and "checksum" in u.error
    assert not list((env / "updates").iterdir())


def test_foreign_url_is_refused(env):
    u = up.Updater(FakeRemote({"windows": {"url": "https://evil.example/x.exe", "sha256": "0" * 64}}))
    assert u.asset() is None


def test_redirect_away_is_refused(env, monkeypatch):
    url = "https://rolandhrvth.hu/subbridge/dl/SubBridge-Setup-9.9.9.exe"
    monkeypatch.setattr(up.urllib.request, "urlopen", lambda req, timeout=0: FakeResp(b"x", "https://evil.example/x"))
    u = up.Updater(FakeRemote({"windows": {"url": url, "sha256": hashlib.sha256(b"x").hexdigest()}}))
    _run(u)
    assert u.ready_path is None and "redirected" in u.error


def test_source_checkout_never_updates(monkeypatch):
    monkeypatch.delattr(up.sys, "frozen", raising=False)
    assert up.platform_key() is None
