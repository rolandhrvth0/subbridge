"""LibreTranslate: self-hosted (e.g. on the same PC or LAN) or a public instance with a key."""
from __future__ import annotations

from .base import TranslationError, Translator
from .http import JsonClient


class LibreTranslator(Translator):
    id = "libre"
    name = "LibreTranslate"
    online = True

    def __init__(self, url: str, api_key: str = ""):
        url = (url or "").strip()
        if not url:
            raise TranslationError("Nincs megadva LibreTranslate-cím.")
        self.http = JsonClient(url, "LibreTranslate", timeout=8)
        self.key = (api_key or "").strip()
        self.local = self.http.host in ("localhost", "127.0.0.1") or self.http.host.startswith(("192.168.", "10."))

    def translate(self, texts, source, target, context=None):
        out = []
        for t in texts:
            body = {"q": t, "source": source, "target": target, "format": "text"}
            if self.key:
                body["api_key"] = self.key
            st, data = self.http.request("POST", "/translate", body)
            if st == 200 and isinstance(data, dict) and "translatedText" in data:
                out.append(data["translatedText"])
                continue
            msg = data.get("error", "") if isinstance(data, dict) else ""
            if st in (400, 403):
                raise TranslationError(f"LibreTranslate: {msg or 'hibás kérés vagy API-kulcs'}")
            raise TranslationError(f"LibreTranslate hiba ({st}). {msg}".strip())
        return out

    def warmup(self):
        try:
            self.http.request("GET", "/languages")
        except TranslationError:
            pass
