"""DLSS 5 neural rendering (experimental): setting it up on the user's PC.

Supported: Linux, AMD Radeon RX 9000 (RDNA4, FP8 matrix instructions), Mesa 26.2 or newer.

SubBridge ships the DLSSNR-AMD runtime (MIT) as the sb-nrview worker plus its shaders – nothing of NVIDIA's.
The network's weights come from the user's own nvngx_dlssnr.dll (310.9.16 or 310.8.0): the model tools read the
weight data out of it (the DLL is never loaded or run) and every one of the hundreds of entries is checked against
the known hashes of NVIDIA's model; a model file is written only if all of them match. The DLL's own hash is not
required to match one exact build: copies differ (signing, repacks) while the weights are identical.
"""
from __future__ import annotations

import contextlib
import io
import os
import runpy
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .paths import resource_dir

MODELS = (  # (DLL resource, descriptor, post-block record, file list, checksums, output)
    ("WEIGHTS_CC_SMALL_FP8", "descriptor-small.json", "block30.layer0.layer", "model-files-small.txt",
     "model-files-small.sha256", "CC_SMALL_FP8.bin"),
    ("WEIGHTS_HT", "descriptor.json", "block70.layer0.layer", "model-files.txt", "model-files.sha256",
     "CC_SILVER_AARDWOLD.bin"),
)


def bundle_dir() -> Path:
    """Worker, shaders and model tools as shipped (packaging/nr in a source checkout)."""
    for d in (resource_dir() / "nr", Path(__file__).resolve().parents[1] / "packaging" / "nr"):
        if (d / "sb-nrview").is_file():
            return d
    return resource_dir() / "nr"


def data_dir() -> Path:
    """Writable: dlssnr-amd/ with the shaders, the extracted model and the pipeline cache."""
    base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
    return Path(os.environ.get("SUBBRIDGE_NR_DIR", str(base / "subbridge" / "nr")))


def worker() -> Path:
    """The worker binary, executable (a packaged data file may lose its +x bit: then a copy in the data dir)."""
    src = bundle_dir() / "sb-nrview"
    if src.is_file() and os.access(src, os.X_OK):
        return src
    dst = data_dir() / "sb-nrview"
    if src.is_file() and (not dst.is_file() or dst.stat().st_size != src.stat().st_size):
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, dst)
            dst.chmod(0o755)
        except OSError:
            pass
    return dst if dst.is_file() else src


def platform_ok() -> bool:
    return sys.platform.startswith("linux")


_probe_cache: tuple[bool, str] | None = None


def probe(force: bool = False) -> tuple[bool, str]:
    """(supported, text): the worker checks the graphics card for the FP8 matrix features the network needs."""
    global _probe_cache
    if _probe_cache is not None and not force:
        return _probe_cache
    if not platform_ok():
        _probe_cache = (False, "csak Linuxon")
    elif not worker().is_file():
        _probe_cache = (False, "a DLSS 5 modul nincs a csomagban")
    else:
        try:
            from .capture.device import _clean_env
            env = _clean_env()
            env["DISABLE_MANGOHUD"] = "1"
            r = subprocess.run([str(worker()), "--probe"], capture_output=True, text=True, timeout=20, env=env)
            line = (r.stdout.strip().splitlines() or ["no nincs válasz"])[-1]
            _probe_cache = (line.startswith("ok "), line[3:].strip())
        except Exception as e:  # noqa: BLE001
            _probe_cache = (False, str(e))
    return _probe_cache


def model_ready() -> bool:
    d = data_dir() / "dlssnr-amd"
    return ((d / "CC_SMALL_FP8.bin").is_file() or (d / "CC_SILVER_AARDWOLD.bin").is_file()) and (d / "shaders").is_dir()


def install_shaders():
    src = bundle_dir() / "dlssnr-amd" / "shaders"
    dst = data_dir() / "dlssnr-amd" / "shaders"
    if src.is_dir() and src.resolve() != dst.resolve():
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
    cache = data_dir() / "dlssnr-amd" / "pipeline.cache"      # built for the previous shaders
    if cache.exists() and src.is_dir():
        cache.unlink()


def _run(tools: Path, script: str, *args: str):
    """Run one model tool in this process (the packaged app has no separate Python)."""
    argv, path = sys.argv, list(sys.path)
    sys.argv = [script, *args]
    sys.path.insert(0, str(tools))
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            runpy.run_path(str(tools / script), run_name="__main__")
    except SystemExit as e:
        if e.code not in (None, 0):
            raise RuntimeError(f"{script}: {e.code}") from None
    finally:
        sys.argv, sys.path[:] = argv, path
    return out.getvalue()


def setup_from_dll(dll: str, progress=lambda pct, text: None) -> tuple[bool, str]:
    """Extract and verify the model(s) from the user's nvngx_dlssnr.dll (or a .zip holding it). ~1 minute."""
    tools = bundle_dir() / "model-tools"
    out_dir = data_dir() / "dlssnr-amd"
    out_dir.mkdir(parents=True, exist_ok=True)
    made = []
    with tempfile.TemporaryDirectory(prefix="sb-nr-") as tmp:
        steps = 7 * len(MODELS)
        n = 0
        for res, desc, post, files, sums, out in MODELS:
            w = Path(tmp) / res
            (w / "graph").mkdir(parents=True)
            shutil.copy(tools / desc, w / "graph" / "descriptor.json")
            try:
                progress(n * 100 // steps, f"{out}: súlyok kiolvasása…")
                _run(tools, "inspect_nr.py", dll, "--output", str(w / "inventory"), "--extract", "--resource", res)
                n += 1
                for script, args in (("unpack_swin_family.py", ["--artifacts", str(w), "--output", str(w / "unpacked"),
                                                                 "--max-c", "256"]),
                                     ("unpack_splitswin.py", ["--artifacts", str(w), "--output", str(w / "unpacked-splitswin")]),
                                     ("unpack_vit.py", ["--artifacts", str(w), "--output", str(w / "unpacked-vit")]),
                                     ("unpack_preblock.py", [str(w / "inventory" / "weights" / "block0.layer0.layer.bin"),
                                                              str(w / "unpacked-preblock")]),
                                     ("unpack_postblock.py", [str(w / "inventory" / "weights" / f"{post}.bin"),
                                                               str(w / "unpacked-postblock")])):
                    progress(n * 100 // steps, f"{out}: kibontás ({script.split('_', 1)[1][:-3]})…")
                    _run(tools, script, *args)
                    n += 1
                progress(n * 100 // steps, f"{out}: ellenőrzés…")
                _run(tools, "pack_model.py", "--root", str(w), "--list", str(tools / files), "--out", str(out_dir / out),
                     "--verify", str(tools / sums))
                n += 1
                made.append(out)
            except Exception:  # noqa: BLE001 – this DLL has no such model, or it does not match NVIDIA's weights
                (out_dir / out).unlink(missing_ok=True)
                n = (MODELS.index((res, desc, post, files, sums, out)) + 1) * 7
    if not made:
        return False, ("Ebből a fájlból nem sikerült a DLSS 5 modellt kibontani. Az nvngx_dlssnr.dll 310.9.16-os "
                       "verziója kell (vagy egy .zip, ami tartalmazza).")
    progress(98, "shaderek telepítése…")
    install_shaders()
    progress(100, "kész")
    return True, "DLSS 5 modell rendben: " + ", ".join(m[:-4] for m in made)
