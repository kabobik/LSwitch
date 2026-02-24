"""Pure text conversion functions (no side effects, fully testable)."""

from __future__ import annotations

from lswitch.intelligence.maps import EN_TO_RU, RU_TO_EN


def convert_text(text: str) -> str:
    """Convert text from one layout to the other, preserving case."""
    result = []
    for ch in text:
        lower = ch.lower()
        if lower in EN_TO_RU:
            converted = EN_TO_RU[lower]
        elif lower in RU_TO_EN:
            converted = RU_TO_EN[lower]
        else:
            result.append(ch)
            continue
        result.append(converted.upper() if ch.isupper() else converted)
    return "".join(result)


def detect_language(text: str) -> str:
    """Return 'ru' if text contains Cyrillic, else 'en'."""
    for ch in text:
        if "\u0400" <= ch <= "\u04ff":
            return "ru"
    return "en"
