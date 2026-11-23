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
        # lsfg-vk 2.0 (dev builds) fails to start in Qt Quick and mpv on current Mesa/loader versions
        # ("failed to get device proc addr for vkCreateSwapchainKHR"), so it is opt-in, not automatic
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


def find_lsfg() -> tuple[str, str, str]:
    """(layer manifest, Lossless.dll, gpu name) – empty strings when not installed."""
    home = Path.home()
    manifests = []
    for pat in (str(home / ".local/opt/lsfg-vk*/VkLayer_LSFGVK*.json"),
                str(home / ".local/share/vulkan/*_layer.d/*LSFGVK*.json"),
                str(home / ".local/share/vulkan/*_layer.d/*lsfg*.json"),
                "/usr/share/vulkan/*_layer.d/*LSFGVK*.json", "/usr/share/vulkan/*_layer.d/*lsfg*.json",
                "/etc/vulkan/*_layer.d/*lsfg*.json", "/usr/local/share/vulkan/*_layer.d/*lsfg*.json"):
        manifests += glob.glob(pat)
    manifest = ""
    for m in sorted(manifests, reverse=True):          # lsfg-vk2 before lsfg-vk
        try:
            if json.loads(Path(m).read_text()).get("layer", {}).get("name") == LSFG_LAYER:
                manifest = m
                break
        except (OSError, ValueError):
            continue
    dll, gpu = "", ""
    confs = [str(Path(manifest).parent / "conf.toml")] if manifest else []
    confs += [str(home / ".config/lsfg-vk/conf.toml")]
    for c in confs:
        try:
            t = Path(c).read_text(encoding="utf-8")
        except OSError:
            continue
        dll = dll or _toml_value(t, "dll")
        gpu = gpu or _toml_value(t, "gpu")
    for d in ([dll] if dll else []) + [
            str(home / ".local/share/Steam/steamapps/common/Lossless Scaling/Lossless.dll"),
            str(home / ".steam/steam/steamapps/common/Lossless Scaling/Lossless.dll"),
            str(home / ".var/app/com.valvesoftware.Steam/data/Steam/steamapps/common/Lossless Scaling/Lossless.dll")]:
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
    lines = ["version = 2", "[global]", f"dll = '{fi.lsfg_dll}'", "allow_fp16 = true", "",
             "[[profile]]", "name = 'SubBridge Game View'",
             "active_in = [" + ", ".join(f"'{n}'" for n in sorted(names) if n) + "]"]
    if fi.lsfg_gpu:
        lines.append(f"gpu = '{fi.lsfg_gpu}'")
    lines += [f"multiplier = {int(multiplier)}", "flow_scale = 1.0", "performance_mode = false", "pacing = 'none'"]
    conf.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ["VK_ADD_LAYER_PATH"] = os.pathsep.join(
        [str(Path(fi.lsfg_json).parent)] + [p for p in os.environ.get("VK_ADD_LAYER_PATH", "").split(os.pathsep) if p])
    layers = [x for x in os.environ.get("VK_INSTANCE_LAYERS", "").split(":") if x]
    if LSFG_LAYER not in layers:
        os.environ["VK_INSTANCE_LAYERS"] = ":".join(layers + [LSFG_LAYER])
    os.environ["LSFGVK_CONFIG"] = str(conf)
    return True
