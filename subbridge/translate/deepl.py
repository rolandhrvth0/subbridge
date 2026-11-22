from __future__ import annotations

import html
import http.client
import json
import queue
import re
import threading
import time

from .base import TranslationError, Translator

# DeepL target codes that need a regional variant
_TARGET_FIX = {"en": "EN-US", "pt": "PT-PT", "zh": "ZH-HANS"}


class DeepLTranslator(Translator):
    id = "deepl"
    name = "DeepL"
    online = True

    def __init__(self, api_key: str, keep_terms: list[str] | None = None):
        self.key = (api_key or "").strip()
        if not self.key:
            raise TranslationError("Nincs megadva DeepL API-kulcs.")
        self.host = "api-free.deepl.com" if self.key.endswith(":fx") else "api.deepl.com"
        self.keep_terms = keep_terms or []
        self._pool: queue.LifoQueue = queue.LifoQueue()
        self._sem = threading.Semaphore(2)
        self.disabled_until = 0.0
        self._backoff = 0.0
        self.last_error = ""

    def _conn(self):
        try:
            return self._pool.get_nowait()
        except queue.Empty:
            return http.client.HTTPSConnection(self.host, timeout=5)

    def _request(self, method, path, body=None):
        hdr = {"Authorization": f"DeepL-Auth-Key {self.key}", "User-Agent": "SubBridge"}
        if body is not None:
            hdr["Content-Type"] = "application/json"
        for _ in range(2):
            c = self._conn()
            try:
                c.request(method, path, body=body, headers=hdr)
                r = c.getresponse()
                raw = r.read()
                if self._pool.qsize() < 4:
                    self._pool.put(c)
                return r.status, raw
            except (OSError, http.client.HTTPException):
                c.close()
        raise TranslationError("A DeepL nem érhető el (nincs internet?).")

    def warmup(self):
        try:
            self._request("GET", "/v2/usage")
        except TranslationError:
            pass

    def usage(self) -> tuple[int, int] | None:
        st, raw = self._request("GET", "/v2/usage")
        if st != 200:
            return None
        d = json.loads(raw)
        return d.get("character_count", 0), d.get("character_limit", 0)

    def _protect(self, text: str) -> str:
        body = html.escape(text, quote=False)
        for t in sorted(self.keep_terms, key=len, reverse=True):
            et = html.escape(t, quote=False)
            body = re.sub(rf"(?<![\w>]){re.escape(et)}(?![\w<])", f"<k>{et}</k>", body)
        return body

    def translate(self, texts, source, target, context=None):
        if time.time() < self.disabled_until:
            raise TranslationError(self.last_error or "A DeepL átmenetileg szünetel.")
        data = {"text": [self._protect(t) for t in texts], "target_lang": _TARGET_FIX.get(target, target.upper()),
                "tag_handling": "xml", "ignore_tags": ["k"], "preserve_formatting": True}
        if source and source != "auto":
            data["source_lang"] = source.upper()
        if context:
            data["context"] = " ".join(context)[-1500:]
        if not self._sem.acquire(timeout=2):
            raise TranslationError("A DeepL túlterhelt.")
        try:
            st, raw = self._request("POST", "/v2/translate", json.dumps(data).encode())
        finally:
            self._sem.release()
        if st == 403:
            self._pause(600, "Hibás DeepL API-kulcs.")
        if st == 456:
            self._pause(600, "Elfogyott a havi DeepL keret.")
        if st == 429 or st >= 500:
            self._backoff = min(30.0, max(2.0, self._backoff * 2))
            self._pause(self._backoff, "A DeepL túl sok kérést kapott, rövid szünet.")
        if st != 200:
            raise TranslationError(f"DeepL hiba ({st}).")
        self._backoff = 0.0
        out = []
        for t in json.loads(raw)["translations"]:
            x = re.sub(r"(?<=\w)<k>", " <k>", t["text"])
            x = re.sub(r"</k>(?=\w)", "</k> ", x)
            out.append(html.unescape(re.sub(r"</?k>", "", x)))
        return out

    def _pause(self, secs, msg):
        self.disabled_until = time.time() + secs
        self.last_error = msg
        raise TranslationError(msg)
