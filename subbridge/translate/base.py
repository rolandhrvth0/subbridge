from __future__ import annotations

import re


class TranslationError(Exception):
    """Raised with a user-readable message."""


class Translator:
    id = "base"
    name = "Base"
    online = False          # True: text leaves the machine (shown in the privacy hint)

    def translate(self, texts: list[str], source: str, target: str,
                  context: list[str] | None = None) -> list[str]:
        raise NotImplementedError

    def warmup(self) -> None:
        pass

    def close(self) -> None:
        pass


_SENT_RE = re.compile(r"(?<=[.!?…])[\"')\]]?\s+(?=[\"'(\[]?[A-Z0-9])")


def split_sentences(text: str) -> list[str]:
    parts = [p.strip() for p in _SENT_RE.split(text) if p.strip()]
    return parts or [text]
