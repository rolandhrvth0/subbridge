"""Helpers to list capture sources for the UI."""
from __future__ import annotations

from ..capture import CaptureSource
from ..i18n import tr

KNOWN_STREAM_APPS = ("chiaki", "remote play", "ps remote", "pxplay", "moonlight", "steam link", "parsec",
                     "xbox", "greenlight", "sunshine", "obs")
SKIP_APPS = ("conky", "nemo-desktop", "desktop", "plank", "cinnamon", "subbridge")


def list_sources(cap: CaptureSource) -> list[dict]:
    out = []
    devices = []
    try:
        from ..capture.device import list_devices
        for d in list_devices():
            devices.append({"kind": "device", "ident": d["id"], "label": f"{tr('capture_device')}: {d['name']}",
                            "title": d["name"], "stream": False})
    except Exception:  # noqa: BLE001  (no multimedia backend)
        pass
    screens = cap.list_screens()
    for i, (_x, _y, w, h) in enumerate(screens):
        name = tr("whole_screen") if len(screens) == 1 else tr("screen_n", n=i + 1)
        out.append({"kind": "screen", "ident": i, "label": f"{name}  ({w}×{h})", "title": ""})
    wins = []
    for w in cap.list_windows():
        app = (w.app or "").lower()
        if any(s in app for s in SKIP_APPS) or w.title in ("Asztal", "Desktop"):
            continue
        wins.append({"kind": "window", "ident": w.id, "label": w.title, "title": w.title, "app": w.app,
                     "stream": any(k in (w.title + " " + w.app).lower() for k in KNOWN_STREAM_APPS)})
    wins.sort(key=lambda d: (not d["stream"], d["label"].lower()))
    return (wins + out if any(w["stream"] for w in wins) else out + wins) + devices


def best_source(sources: list[dict]) -> int:
    for i, s in enumerate(sources):
        if s.get("stream"):
            return i
    return 0
