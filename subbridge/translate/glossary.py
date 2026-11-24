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


_GAME_NAMES: tuple[float, list[str]] | None = None


def game_names() -> list[str]:
    """Proper names of the game world (brands, places, crews) that machine translation would otherwise
    translate word by word ("Jack of Hearts" -> "Szív Jack", "Final Chapter" -> "Utolsó fejezet").
    Bundled assets/packs/names.json, overridden by a newer downloaded <data>/packs/names.json."""
    global _GAME_NAMES
    import json
    from ..paths import data_dir, resource_dir
    files = [resource_dir() / "assets" / "packs" / "names.json", data_dir() / "packs" / "names.json"]
    stamp = sum((f.stat().st_mtime if f.exists() else 0) for f in files)
    if _GAME_NAMES and _GAME_NAMES[0] == stamp:
        return _GAME_NAMES[1]
    best, ver = [], -1
    for f in files:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if int(d.get("version", 0)) > ver:
            best, ver = [str(x) for x in d.get("keep") or []], int(d.get("version", 0))
    _GAME_NAMES = (stamp, best)
    return best


def with_game_names(items: list[dict]) -> Glossary:
    """The user's glossary plus the game's proper names (the user's own rules come first and win)."""
    g = Glossary.from_list(items)
    have = {r.find.lower() for r in g.rules}
    g.rules += [Rule(n, stage="keep", case_sensitive=True) for n in game_names() if n.lower() not in have]
    return g
