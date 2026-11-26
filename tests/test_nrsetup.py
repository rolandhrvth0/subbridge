"""DLSS 5 setup: a wrong file never leaves a model behind; the worker ships with the package."""
from pathlib import Path

from subbridge import nrsetup


def test_bad_file_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("SUBBRIDGE_NR_DIR", str(tmp_path / "nr"))
    bad = tmp_path / "x.dll"
    bad.write_bytes(b"MZ" + b"\0" * 5000)
    ok, msg = nrsetup.setup_from_dll(str(bad))
    assert not ok and "nvngx_dlssnr" in msg
    assert not nrsetup.model_ready()
    assert not list((tmp_path / "nr" / "dlssnr-amd").glob("*.bin"))


def test_bundle_has_worker_tools_and_no_nvidia_files():
    b = nrsetup.bundle_dir()
    assert (b / "sb-nrview").is_file()
    assert (b / "model-tools" / "pack_model.py").is_file()
    assert (b / "dlssnr-amd" / "shaders").is_dir()
    assert not list(Path(b).rglob("*.dll")) and not list(Path(b).rglob("*.bin"))
