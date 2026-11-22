"""Tiny JSON-over-HTTPS helper shared by the online translators (stdlib only, keep-alive pool)."""
from __future__ import annotations

import http.client
import json
import queue
from urllib.parse import urlsplit

from .base import TranslationError


class JsonClient:
    def __init__(self, base_url: str, name: str, timeout: float = 5.0):
        u = urlsplit(base_url if "://" in base_url else "https://" + base_url)
        if u.scheme not in ("http", "https") or not u.hostname:
            raise TranslationError(f"Érvénytelen cím: {base_url}")
        self.scheme, self.host, self.port = u.scheme, u.hostname, u.port
        self.prefix = u.path.rstrip("/")
        self.name, self.timeout = name, timeout
        self._pool: queue.LifoQueue = queue.LifoQueue()

    def _conn(self):
        try:
            return self._pool.get_nowait()
        except queue.Empty:
            cls = http.client.HTTPSConnection if self.scheme == "https" else http.client.HTTPConnection
            return cls(self.host, self.port, timeout=self.timeout)

    def request(self, method: str, path: str, payload=None, headers=None) -> tuple[int, object]:
        hdr = {"User-Agent": "SubBridge", "Accept": "application/json", **(headers or {})}
        body = None
        if payload is not None:
            body = json.dumps(payload).encode()
            hdr["Content-Type"] = "application/json"
        for _ in range(2):
            c = self._conn()
            try:
                c.request(method, self.prefix + path, body=body, headers=hdr)
                r = c.getresponse()
                raw = r.read()
                if self._pool.qsize() < 4:
                    self._pool.put(c)
                try:
                    data = json.loads(raw or b"null")
                except ValueError:
                    data = raw.decode("utf-8", "replace")
                return r.status, data
            except (OSError, http.client.HTTPException):
                c.close()
        raise TranslationError(f"A(z) {self.name} nem érhető el (nincs internet vagy rossz cím?).")
