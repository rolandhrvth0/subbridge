from __future__ import annotations

from .argos import ArgosTranslator
from .base import TranslationError, Translator
from .deepl import DeepLTranslator
from .google import GoogleCloudTranslator
from .libre import LibreTranslator

ENGINES = {
    "argos": ArgosTranslator.name,
    "deepl": DeepLTranslator.name,
    "google": GoogleCloudTranslator.name,
    "libre": LibreTranslator.name,
}
ONLINE = {"deepl", "google", "libre"}


def engine_key(engine: str, settings: dict) -> tuple:
    """Everything that, when changed, requires a new translator instance."""
    return {"deepl": (settings.get("deepl_key"),), "google": (settings.get("google_key"),),
            "libre": (settings.get("libre_url"), settings.get("libre_key"))}.get(engine, ())


def create_translator(engine: str, settings: dict, keep_terms: list[str]) -> Translator:
    if engine == "argos":
        return ArgosTranslator()
    if engine == "deepl":
        return DeepLTranslator(settings.get("deepl_key", ""), keep_terms)
    if engine == "google":
        return GoogleCloudTranslator(settings.get("google_key", ""))
    if engine == "libre":
        return LibreTranslator(settings.get("libre_url", ""), settings.get("libre_key", ""))
    raise TranslationError(f"Ismeretlen fordítómotor: {engine}")
