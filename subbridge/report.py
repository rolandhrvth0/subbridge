"""Bug report: one click sends what is needed to find a problem to the project site.

Sent (and shown to the user before sending): the user's description, optional contact, app version,
OS, monitors, settings WITHOUT keys/tokens/PINs, the overlay's state and the end of the log (home
folder and user name masked), and – only if the user leaves it ticked – one picture of the selected
subtitle strip. Nothing is sent automatically."""
from __future__ import annotations

import base64
import dataclasses
import getpass
import io
import json
import logging
import os
import platform
import re
import sys
import urllib.request
from pathlib import Path

from .branding import HOMEPAGE, VERSION
from .paths import config_dir

log = logging.getLogger(__name__)
URL = HOMEPAGE.rstrip("/") + "/api/report"
SECRET = re.compile(r"key|token|pin|pass|secret|url|cookie", re.I)
MAX_IMG = 1_200_000


def _scrub(v):
    if isinstance(v, dict):
        return {k: ("***" if SECRET.search(str(k)) and v[k] else _scrub(x)) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_scrub(x) for x in v]
    return v


def _mask(text: str) -> str:
    home = str(Path.home())
    text = text.replace(home, "~").replace(home.replace("\\", "/"), "~")
    try:
        user = getpass.getuser()
        if len(user) >= 3:
            text = re.sub(re.escape(user), "<user>", text, flags=re.I)
    except Exception:  # noqa: BLE001
        pass
    return text


def log_tail(lines: int = 400) -> str:
    f = config_dir() / "subbridge.log"
    try:
        with open(f, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - 400_000))
            data = fh.read().decode("utf-8", "replace").splitlines()[-lines:]
        return _mask("\n".join(data))
    except OSError:
        return ""


def overlay_state(engine) -> dict:
    ov = getattr(engine, "_classic", None)
    if ov is None:
        return {}
    try:
        return {"health": ov.health(), "stats": dict(ov.stats),
                "color": None if ov.color is None else [int(c) for c in ov.color],
                "geo": list(ov._geo[:4]) if getattr(ov, "_geo", None) else None,
                "entries": len(ov.entries)}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def encode_image(rgb, max_w: int = 1600) -> str | None:
    """RGB array -> base64 JPEG (small enough for the upload limit)."""
    if rgb is None:
        return None
    from PIL import Image
    im = Image.fromarray(rgb)
    if im.width > max_w:
        im = im.resize((max_w, max(1, int(im.height * max_w / im.width))))
    for q in (85, 70, 55):
        buf = io.BytesIO()
        im.convert("RGB").save(buf, "JPEG", quality=q)
        if buf.tell() <= MAX_IMG:
            return base64.b64encode(buf.getvalue()).decode("ascii")
    return None


def build(settings, engine, note: str, contact: str = "", screens=None, source=None, image=None,
          frame=None) -> dict:
    try:
        st = _scrub(dataclasses.asdict(settings))
    except Exception:  # noqa: BLE001
        st = {}
    return {
        "app": VERSION, "frozen": bool(getattr(sys, "frozen", False)),
        "os": platform.platform(), "python": platform.python_version(),
        "note": note.strip()[:4000], "contact": contact.strip()[:200],
        "screens": screens or [], "source": _scrub(source or {}),
        "settings": st, "overlay": overlay_state(engine),
        "running": bool(getattr(engine, "running", False)),
        "log": log_tail(), "image": image, "frame": frame,
    }


def send(report: dict, timeout: float = 25.0) -> str:
    """POST the report; returns the report id from the server."""
    body = json.dumps(report, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(URL, data=body, method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": f"SubBridge/{VERSION}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read(10_000))
    if not out.get("ok"):
        raise RuntimeError(out.get("error") or "server error")
    return str(out.get("id", ""))
