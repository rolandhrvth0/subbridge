"""Automatic update for the installed app (Windows installer, Linux .deb).

Safety rules (hundreds of installs):
  * only the file named in the project feed (https://rolandhrvth.hu/subbridge/feed) is downloaded,
    only over HTTPS from rolandhrvth.hu, and its SHA-256 must match the feed – otherwise it is deleted;
  * nothing is installed while translating; Windows installs silently when the app closes (or on click),
    Linux asks for the system password once (pkexec) – a system package cannot be installed without it;
  * running from source (developer checkout) never updates itself.

Feed:  "latest": {"version": "0.1.1", "files": {"windows": {"url": …, "sha256": …},
                                                "linux-deb": {"url": …, "sha256": …}}}"""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path

from .branding import VERSION
from .paths import data_dir

log = logging.getLogger(__name__)
ALLOWED_PREFIX = "https://rolandhrvth.hu/"


def platform_key() -> str | None:
    if not getattr(sys, "frozen", False):
        return None                                   # source checkout: never self-update
    if sys.platform == "win32":
        return "windows"
    if sys.platform.startswith("linux") and Path(sys.executable).resolve().as_posix().startswith("/opt/subbridge/"):
        return "linux-deb"
    return None


class Updater:
    def __init__(self, remote, on_ready=None):
        self.remote = remote
        self.on_ready = on_ready or (lambda: None)
        self.ready_path: Path | None = None
        self.ready_version = ""
        self.error = ""
        self._busy = False

    def asset(self) -> dict | None:
        key = platform_key()
        if not key or not self.remote.update_available():
            return None
        a = ((self.remote.latest or {}).get("files") or {}).get(key)
        if not a or not str(a.get("url", "")).startswith(ALLOWED_PREFIX) or len(str(a.get("sha256", ""))) != 64:
            return None
        return a

    def supported(self) -> bool:
        return self.asset() is not None

    def start_download(self):
        a = self.asset()
        ver = (self.remote.latest or {}).get("version", "")
        if a is None or self._busy or (self.ready_path and self.ready_version == ver):
            return
        self._busy = True
        threading.Thread(target=self._download, args=(a, ver), name="update", daemon=True).start()

    def _download(self, a: dict, ver: str):
        try:
            d = data_dir() / "updates"
            d.mkdir(parents=True, exist_ok=True)
            name = a["url"].rsplit("/", 1)[-1]
            if not name or "/" in name or name.startswith("."):
                raise ValueError("bad file name")
            dest, part = d / name, d / (name + ".part")
            h = hashlib.sha256()
            if dest.exists():                                    # downloaded earlier: verify again
                with open(dest, "rb") as f:
                    for chunk in iter(lambda: f.read(1 << 20), b""):
                        h.update(chunk)
            else:
                req = urllib.request.Request(a["url"], headers={"User-Agent": f"SubBridge/{VERSION}"})
                with urllib.request.urlopen(req, timeout=30) as r, open(part, "wb") as f:
                    if not r.geturl().startswith(ALLOWED_PREFIX):
                        raise ValueError("redirected away from the project site")
                    for chunk in iter(lambda: r.read(1 << 20), b""):
                        h.update(chunk)
                        f.write(chunk)
            if h.hexdigest().lower() != str(a["sha256"]).lower():
                for p in (dest, part):
                    p.unlink(missing_ok=True)
                raise ValueError("checksum mismatch – update discarded")
            if part.exists():
                part.replace(dest)
            for old in d.iterdir():                              # keep only the current update
                if old != dest:
                    old.unlink(missing_ok=True)
            self.ready_path, self.ready_version, self.error = dest, ver, ""
            log.info("update %s ready: %s", ver, dest)
            self.on_ready()
        except Exception as e:  # noqa: BLE001  (offline etc.: try again at the next feed refresh)
            self.error = str(e)
            log.warning("update download failed: %s", e)
        finally:
            self._busy = False

    def install(self, restart: bool = True) -> bool:
        """Start installing the downloaded update. Returns True when the app should quit now."""
        p = self.ready_path
        if not p or not p.exists():
            return False
        key = platform_key()
        if key == "windows":
            args = [str(p), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS",
                    f"/RELAUNCH={1 if restart else 0}"]
            flags = 0x00000008 | 0x00000200                      # DETACHED_PROCESS | NEW_PROCESS_GROUP
            subprocess.Popen(args, creationflags=flags, close_fds=True)
            return True
        if key == "linux-deb":
            pk = shutil.which("pkexec")
            if not pk:
                self.error = "pkexec not found"
                return False
            r = subprocess.run([pk, "apt-get", "install", "-y", "--allow-downgrades", str(p)],
                               capture_output=True, timeout=600)
            if r.returncode != 0:
                self.error = (r.stderr or b"").decode("utf-8", "ignore")[-300:] or f"rc={r.returncode}"
                return False
            if restart:
                # after this instance has quit (single instance: an early start would only signal us)
                subprocess.Popen(["sh", "-c", "sleep 2; exec /opt/subbridge/subbridge"], start_new_session=True,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=dict(os.environ))
            return True
        return False
