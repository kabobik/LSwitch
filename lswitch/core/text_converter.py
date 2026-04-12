"""Pure text conversion functions (no side effects, fully testable)."""

from __future__ import annotations

from lswitch.intelligence.maps import EN_TO_RU, RU_TO_EN


def detect_language(text: str) -> str:
    """Return 'ru' if text contains Cyrillic, else 'en'."""
    for ch in text:
        if "\u0400" <= ch <= "\u04ff":
            return "ru"
    return "en"


def convert_text(text: str, direction: str | None = None) -> str:
    """Convert text between keyboard layouts, preserving case.

    Args:
        text:      Source text to convert.
        direction: ``'en_to_ru'``, ``'ru_to_en'``, or ``None`` (auto-detect
                   from the text itself via :func:`detect_language`).
    """
    if direction is None:
        lang = detect_language(text)
        direction = "ru_to_en" if lang == "ru" else "en_to_ru"

    table = EN_TO_RU if direction == "en_to_ru" else RU_TO_EN

    result = []
    for ch in text:
        lower = ch.lower()
        converted = table.get(lower)
        if converted is None:
            result.append(ch)
        else:
            result.append(converted.upper() if ch.isupper() else converted)
    return "".join(result)
