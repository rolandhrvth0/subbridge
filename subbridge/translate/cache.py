from __future__ import annotations

import json
import threading
import time
from collections import OrderedDict
from pathlib import Path


class TranslationCache:
    """Small persistent LRU cache: (engine, src, tgt, text) -> translation."""

    def __init__(self, path: Path, max_items: int = 20000):
        self.path = Path(path)
        self.max_items = max_items
        self._d: OrderedDict[str, str] = OrderedDict()
        self._lock = threading.Lock()
        self._dirty = False
        self._last_save = 0.0
        try:
            self._d.update(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass

    @staticmethod
    def key(engine: str, src: str, tgt: str, text: str) -> str:
        return f"{engine}|{src}|{tgt}|{text}"

    def get(self, engine, src, tgt, text) -> str | None:
        k = self.key(engine, src, tgt, text)
        with self._lock:
            v = self._d.get(k)
            if v is not None:
                self._d.move_to_end(k)
            return v

    def put(self, engine, src, tgt, text, value) -> None:
        with self._lock:
            self._d[self.key(engine, src, tgt, text)] = value
            while len(self._d) > self.max_items:
                self._d.popitem(last=False)
            self._dirty = True
        if time.time() - self._last_save > 10:
            self.save()

    def clear(self) -> None:
        with self._lock:
            self._d.clear()
            self._dirty = True
        self.save()

    def __len__(self) -> int:
        return len(self._d)

    def save(self) -> None:
        with self._lock:
            if not self._dirty:
                return
            data = json.dumps(self._d, ensure_ascii=False)
            self._dirty = False
            self._last_save = time.time()
        tmp = self.path.with_suffix(".tmp")
        try:
            tmp.write_text(data, encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            pass
