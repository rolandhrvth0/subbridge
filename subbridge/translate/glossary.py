"""User glossary: terms to keep untranslated and replacement rules before/after translation."""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Rule:
    find: str
    replace: str = ""
    stage: str = "keep"      # "keep" | "before" | "after"
    whole_word: bool = True
    case_sensitive: bool = False

    def pattern(self) -> re.Pattern:
        p = re.escape(self.find)
        if self.whole_word:
            p = rf"(?<!\w){p}(?!\w)"
        return re.compile(p, 0 if self.case_sensitive else re.IGNORECASE)


@dataclass
class Glossary:
    rules: list[Rule] = field(default_factory=list)

    @classmethod
    def from_list(cls, items: list[dict]) -> "Glossary":
        out = []
        for it in items or []:
            try:
                if it.get("find"):
                    out.append(Rule(**{k: v for k, v in it.items() if k in Rule.__annotations__}))
            except TypeError:
                continue
        return cls(out)

    def keep_terms(self) -> list[str]:
        return [r.find for r in self.rules if r.stage == "keep"]

    def before(self, text: str) -> str:
        for r in self.rules:
            if r.stage == "before":
                text = r.pattern().sub(r.replace, text)
        return text

    def after(self, text: str) -> str:
        for r in self.rules:
            if r.stage == "after":
                text = r.pattern().sub(r.replace, text)
        return text

    def protect(self, text: str) -> tuple[str, dict[str, str]]:
        """Swap keep-terms for opaque tokens that machine translation leaves alone."""
        mapping: dict[str, str] = {}
        for i, term in enumerate(sorted(self.keep_terms(), key=len, reverse=True)):
            tok = f"ZQX{i}"
            pat = Rule(term).pattern()
            if pat.search(text):
                text = pat.sub(tok, text)
                mapping[tok] = term
        return text, mapping

    @staticmethod
    def restore(text: str, mapping: dict[str, str]) -> str:
        for tok, term in mapping.items():
            text = re.sub(rf"{tok}\w*", term, text)
        return text
