import os
import sys
from pathlib import Path

from .branding import APP_ID


def config_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    d = base / APP_ID
    d.mkdir(parents=True, exist_ok=True)
    return d


def data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    d = base / APP_ID
    d.mkdir(parents=True, exist_ok=True)
    return d


def resource_dir() -> Path:
    """Bundled read-only resources (works from source and from a PyInstaller bundle)."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / "subbridge"
    return Path(__file__).resolve().parent
