"""News, content packs and update notice from the project site – new slang, speaker roles, fixes and
announcements reach every installation without an app update.

  {FEED}/index.json = {
    "news":   [{"id", "date", "title": {"hu","en"}, "body": {"hu","en"}, "link"?}],
    "packs":  {"slang-en": {"version": 3, "url": "packs/slang-en.json"}, …},
    "latest": {"version": "0.2.0", "url": "https://…", "notes": {"hu","en"}}
  }
Packs land in <data>/packs/<name>.json and are picked up by translate.textprep.
Only these public files are requested; nothing about the user or the game is sent."""
from __future__ import annotations

import json
import logging
import threading
import time
import urllib.request

from .branding import HOMEPAGE, VERSION
from .paths import data_dir

FEED = HOMEPAGE.rstrip("/") + "/feed"
log = logging.getLogger(__name__)


def _get(url: str, timeout: float = 8.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": f"SubBridge/{VERSION}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(2_000_000)


def _ver(v: str) -> tuple:
    try:
        return tuple(int(x) for x in str(v).split(".")[:3])
    except ValueError:
        return (0,)


class Remote:
    def __init__(self, on_change=None):
        self.on_change = on_change or (lambda: None)
        self.news: list[dict] = []
        self.latest: dict | None = None
        self._dir = data_dir() / "packs"
        self._state_f = data_dir() / "remote.json"
        self._state = self._load_state()
        self.news = self._state.get("news", [])
        self.latest = self._state.get("latest")

    def _load_state(self) -> dict:
        try:
            return json.loads(self._state_f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save_state(self):
        try:
            self._state_f.write_text(json.dumps(self._state, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    # ------------------------------------------------------------------ public
    @property
    def unread(self) -> int:
        seen = set(self._state.get("seen", []))
        return sum(1 for n in self.news if n.get("id") not in seen)

    def mark_read(self):
        self._state["seen"] = [n.get("id") for n in self.news]
        self._save_state()

    def update_available(self) -> bool:
        return bool(self.latest) and _ver(self.latest.get("version", "0")) > _ver(VERSION)

    def start(self, every_hours: float = 6.0):
        def loop():
            while True:
                try:
                    self.refresh()
                except Exception as e:  # noqa: BLE001  (offline: keep the cached state)
                    log.info("feed not reachable: %s", e)
                time.sleep(every_hours * 3600)
        threading.Thread(target=loop, name="feed", daemon=True).start()

    def refresh(self):
        idx = json.loads(_get(f"{FEED}/index.json"))
        changed = False
        self._dir.mkdir(parents=True, exist_ok=True)
        have = self._state.setdefault("packs", {})
        for name, info in (idx.get("packs") or {}).items():
            if not name.replace("-", "").isalnum():
                continue
            ver = int(info.get("version", 0))
            if have.get(name) == ver and (self._dir / f"{name}.json").exists():
                continue
            data = json.loads(_get(f"{FEED}/{info['url'].lstrip('/')}"))       # must be valid JSON
            (self._dir / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            have[name] = ver
            changed = True
        news = idx.get("news") or []
        if news != self.news:
            self.news = news
            self._state["news"] = news
            changed = True
        latest = idx.get("latest")
        if latest != self.latest:
            self.latest = latest
            self._state["latest"] = latest
            changed = True
        if changed:
            self._save_state()
            from .translate.textprep import textprep
            textprep().reload()
            self.on_change()
