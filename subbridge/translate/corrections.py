"""The user's own corrections: a sentence fixed once is always shown the user's way.

Stored in <data>/corrections.json as {"hu": {"<normalised english>": "<translation>"}}. Exact sentence
match (case, spacing and edge punctuation ignored), so a fix never leaks into other sentences."""
from __future__ import annotations

import json
import re
import threading

from ..paths import data_dir

_inst = None


def norm(text: str) -> str:
    t = re.sub(r"\s+", " ", (text or "").replace("’", "'")).strip().lower()
    return t.strip(" .,!?…\"'-")


class Corrections:
    def __init__(self, path=None):
        self.path = path or (data_dir() / "corrections.json")
        self._lock = threading.Lock()
        try:
            self.data: dict[str, dict[str, str]] = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.data = {}

    def get(self, text: str, tgt: str) -> str | None:
        k = norm(text)
        return self.data.get(tgt, {}).get(k) if k else None

    def put(self, text: str, tgt: str, fixed: str):
        k = norm(text)
        if not k:
            return
        with self._lock:
            if fixed.strip():
                self.data.setdefault(tgt, {})[k] = fixed.strip()
            else:
                self.data.get(tgt, {}).pop(k, None)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self.path)

    def count(self, tgt: str = "hu") -> int:
        return len(self.data.get(tgt, {}))


def corrections() -> Corrections:
    global _inst
    if _inst is None:
        _inst = Corrections()
    return _inst
