"""Google Cloud Translation (official API v2, own API key). Never the unofficial free endpoint."""
from __future__ import annotations

import html
from urllib.parse import quote

from .base import TranslationError, Translator
from .http import JsonClient


class GoogleCloudTranslator(Translator):
    id = "google"
    name = "Google Cloud"
    online = True

    def __init__(self, api_key: str):
        self.key = (api_key or "").strip()
        if not self.key:
            raise TranslationError("Nincs megadva Google Cloud API-kulcs.")
        self.http = JsonClient("https://translation.googleapis.com", "Google Cloud")

    def translate(self, texts, source, target, context=None):
        st, data = self.http.request("POST", f"/language/translate/v2?key={quote(self.key)}",
                                     {"q": texts, "source": source, "target": target, "format": "text"})
        if st == 200 and isinstance(data, dict):
            tr = data.get("data", {}).get("translations", [])
            if len(tr) == len(texts):
                return [html.unescape(t.get("translatedText", "")) for t in tr]
        if st in (400, 401, 403):
            msg = data.get("error", {}).get("message", "") if isinstance(data, dict) else ""
            raise TranslationError(f"Google Cloud: a kulcs nem érvényes vagy nincs engedélyezve a Translation API. {msg}".strip())
        if st == 429:
            raise TranslationError("Google Cloud: túl sok kérés vagy elfogyott a keret.")
        raise TranslationError(f"Google Cloud hiba ({st}).")

    def warmup(self):
        try:
            self.http.request("GET", f"/language/translate/v2/languages?key={quote(self.key)}")
        except TranslationError:
            pass
