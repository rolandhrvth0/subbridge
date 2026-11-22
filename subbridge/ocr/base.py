from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OcrLine:
    text: str
    confidence: float     # 0-100


class OcrEngine:
    id = "base"
    name = "Base"

    def recognize(self, img) -> list[OcrLine]:
        raise NotImplementedError

    def available(self) -> bool:
        return True
