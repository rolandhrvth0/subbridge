"""Frame generation for the Game View: which technique to use on this PC.

SubBridge does not re-implement the GPU makers' frame generation – it renders the Game View on the
graphics card (Vulkan on Linux, Direct3D 11 on Windows) so their technology can work on it:

  lsfg      Linux, any GPU: Lossless Scaling's frame generation through the lsfg-vk Vulkan layer
            (needs lsfg-vk 2.x and the user's own Lossless.dll from Lossless Scaling on Steam)
  afmf      Windows + AMD Radeon: AMD Fluid Motion Frames, switched on in AMD Software (Adrenalin)
  smooth    Windows + NVIDIA RTX 40/50: NVIDIA Smooth Motion, switched on in the NVIDIA app
  builtin   SubBridge's own CPU interpolation (experimental fallback)
  off
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

LSFG_LAYER = "VK_LAYER_LSFGVK_frame_generation"


@dataclass
class Gpu:
    vendor: str = ""          # amd | nvidia | intel | ""
    name: str = ""


@dataclass
class FgInfo:
    gpu: Gpu = field(default_factory=Gpu)
    lsfg_json: str = ""       # layer manifest
    lsfg_dll: str = ""        # Lossless.dll
    lsfg_gpu: str = ""        # gpu name from the user's own lsfg profile (multi-GPU systems)

    @property
    def lsfg_ok(self) -> bool:
        return bool(self.lsfg_json and self.lsfg_dll)

    def choices(self) -> list[str]:
        out = ["auto"]
        if sys.platform.startswith("linux") and self.lsfg_ok:
            out.append("lsfg")
        if sys.platform == "win32":
            if self.gpu.vendor == "amd":
                out.append("afmf")
            if self.gpu.vendor == "nvidia":
                out.append("smooth")
        out += ["builtin", "off"]
        return out

    def resolve(self, mode: str) -> str:
        """'auto' -> the best technique available here; an unavailable choice falls back too."""
        if mode in self.choices() and mode != "auto":
            return mode
        # only lsfg-vk 2.0 releases work in Qt Quick; the old dev builds fail there ("failed to get device
        # proc addr for vkCreateSwapchainKHR"), so those stay opt-in
        if sys.platform.startswith("linux") and self.lsfg_ok and lsfg_is_release(self.lsfg_json):
            return "lsfg"
        if sys.platform == "win32" and self.gpu.vendor == "amd":
            return "afmf"
        if sys.platform == "win32" and self.gpu.vendor == "nvidia":
            return "smooth"
        return "off"


_VENDORS = {"0x1002": "amd", "0x10de": "nvidia", "0x8086": "intel"}


def detect_gpu() -> Gpu:
    if sys.platform.startswith("linux"):
        best = Gpu()
        for v in sorted(glob.glob("/sys/class/drm/card*/device/vendor")):
            try:
                vendor = _VENDORS.get(Path(v).read_text().strip().lower(), "")
            except OSError:
                continue
            if vendor and (not best.vendor or best.vendor == "intel"):   # a discrete card beats the iGPU
                best = Gpu(vendor, "")
        return best
    if sys.platform == "win32":
        try:
            import winreg
            key = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
            best = Gpu()
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key) as k:
                for i in range(32):
                    try:
                        sub = winreg.EnumKey(k, i)
                    except OSError:
                        break
                    if not sub.isdigit():
                        continue
                    try:
                        with winreg.OpenKey(k, sub) as s:
                            desc = str(winreg.QueryValueEx(s, "DriverDesc")[0])
                    except OSError:
                        continue
                    low = desc.lower()
                    vendor = "nvidia" if "nvidia" in low else "amd" if ("amd" in low or "radeon" in low) else \
                        "intel" if "intel" in low else ""
                    if vendor and (not best.vendor or best.vendor == "intel"):
                        best = Gpu(vendor, desc)
            return best
        except Exception:  # noqa: BLE001
            return Gpu()
    return Gpu()


def _toml_value(text: str, key: str) -> str:
    m = re.search(rf"^\s*{key}\s*=\s*['\"]([^'\"]+)['\"]", text, re.M)
    return m.group(1) if m else ""


def _layer_rank(manifest: str) -> tuple:
    """Release 2.x layers (share/vulkan/… layout, works with Qt Quick and mpv) before old dev builds."""
    try:
        impl = int(json.loads(Path(manifest).read_text()).get("layer", {}).get("implementation_version", 0))
    except (OSError, ValueError, TypeError):
        impl = 0
    return ("/share/vulkan/" in manifest, impl, manifest)


def lsfg_is_release(manifest: str) -> bool:
    return "/share/vulkan/" in manifest


def find_lsfg() -> tuple[str, str, str]:
    """(layer manifest, shader DLL, gpu name) – empty strings when not installed.
    lsfg-vk 2.0 releases read lsfg-vk.dll (Lossless Scaling's "lsfg-vk" Steam beta branch); the old dev
    builds read Lossless.dll."""
    home = Path.home()
    manifests = []
    for pat in (str(home / ".local/opt/*/share/vulkan/*_layer.d/VkLayer_LSFGVK*.json"),
                str(home / ".local/share/vulkan/*_layer.d/VkLayer_LSFGVK*.json"),
                str(home / ".local/opt/lsfg-vk*/VkLayer_LSFGVK*.json"),
                "/usr/share/vulkan/*_layer.d/VkLayer_LSFGVK*.json", "/usr/local/share/vulkan/*_layer.d/VkLayer_LSFGVK*.json",
                "/etc/vulkan/*_layer.d/VkLayer_LSFGVK*.json"):
        manifests += [m for m in glob.glob(pat) if not m.endswith(".x86.json")]
    manifest = ""
    for m in sorted(set(manifests), key=_layer_rank, reverse=True):
        try:
            if json.loads(Path(m).read_text()).get("layer", {}).get("name") == LSFG_LAYER:
                manifest = m
                break
        except (OSError, ValueError):
            continue
    release = lsfg_is_release(manifest)
    steam_dirs = [home / ".steam/steam/steamapps/common", home / ".local/share/Steam/steamapps/common",
                  home / ".steam/debian-installation/steamapps/common",
                  home / ".var/app/com.valvesoftware.Steam/.local/share/Steam/steamapps/common",
                  home / "snap/steam/common/.local/share/Steam/steamapps/common"]
    names = ["lsfg-vk.dll"] if release else ["Lossless.dll"]
    gpu, conf_dll = "", ""
    confs = ([str(Path(manifest).parent / "conf.toml")] if manifest and not release else []) + \
        [str(home / ".config/lsfg-vk/conf.toml")]
    for c in confs:
        try:
            t = Path(c).read_text(encoding="utf-8")
        except OSError:
            continue
        conf_dll = conf_dll or _toml_value(t, "dll")
        gpu = gpu or _toml_value(t, "gpu")
    cands = [conf_dll] if conf_dll and Path(conf_dll).name in names else []
    cands += [str(d / "Lossless Scaling" / n) for d in steam_dirs for n in names]
    for d in cands:
        if d and os.path.isfile(d):
            return manifest, d, gpu
    return manifest, "", gpu


_info: FgInfo | None = None


def info() -> FgInfo:
    global _info
    if _info is None:
        lj, dll, g = find_lsfg() if sys.platform.startswith("linux") else ("", "", "")
        _info = FgInfo(detect_gpu(), lj, dll, g)
    return _info


def enable_lsfg(fi: FgInfo, multiplier: int = 2) -> bool:
    """Load the lsfg-vk layer for this process's Vulkan windows (the Game View). Must run before the
    first Vulkan instance is created. Writes SubBridge's own lsfg profile; the user's file stays as is."""
    if not fi.lsfg_ok:
        return False
    from .paths import config_dir
    names = {Path(sys.executable).name, Path(sys.argv[0]).name, "subbridge", "SubBridge", "python3", "python"}
    try:
        names.add(Path("/proc/self/comm").read_text().strip())
    except OSError:
        pass
    conf = config_dir() / "lsfg-vk.toml"
    release = lsfg_is_release(fi.lsfg_json)
    lines = ["version = 2", "[global]", f"dll = '{fi.lsfg_dll}'", "allow_fp16 = true", "",
             "[[profile]]", "name = 'SubBridge Game View'",
             "active_in = [" + ", ".join(f"'{n}'" for n in sorted(names) if n) + "]"]
    if fi.lsfg_gpu and not release:              # 2.0 releases reject the old "gpu" key
        lines.append(f"gpu = '{fi.lsfg_gpu}'")
    lines += [f"multiplier = {int(multiplier)}", "flow_scale = 1.0", "performance_mode = false"]
    if not release:
        lines.append("pacing = 'none'")          # the dev builds knew only this one
    conf.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ["VK_ADD_LAYER_PATH"] = os.pathsep.join(
        [str(Path(fi.lsfg_json).parent)] + [p for p in os.environ.get("VK_ADD_LAYER_PATH", "").split(os.pathsep) if p])
    layers = [x for x in os.environ.get("VK_INSTANCE_LAYERS", "").split(":") if x]
    if LSFG_LAYER not in layers:
        os.environ["VK_INSTANCE_LAYERS"] = ":".join(layers + [LSFG_LAYER])
    os.environ["LSFGVK_CONFIG"] = str(conf)
    return True
