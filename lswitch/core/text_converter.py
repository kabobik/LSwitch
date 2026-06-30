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


def invert_layout_text(text: str) -> str:
    """Invert layout direction independently for each non-whitespace fragment.

    ``convert_text(text)`` intentionally chooses one direction for the whole
    string. Selection conversion needs different behavior: a multi-word or
    multi-line selection can contain fragments from both layouts, and each
    fragment should be inverted on its own.
    """
    return "".join(converted for converted, _target_lang in invert_layout_runs(text))


def invert_layout_runs(text: str) -> list[tuple[str, str | None]]:
    """Return converted text runs with the layout language needed to type them."""
    runs: list[tuple[str, str | None]] = []
    current_source_lang: str | None = None
    current_chars: list[str] = []

    def flush() -> None:
        nonlocal current_source_lang, current_chars
        if not current_chars:
            return

        raw = "".join(current_chars)
        if current_source_lang is None:
            converted = raw
            target_lang = None
        else:
            target_lang = "ru" if current_source_lang == "en" else "en"
            direction = "en_to_ru" if current_source_lang == "en" else "ru_to_en"
            converted = convert_text(raw, direction=direction)

        if runs and runs[-1][1] == target_lang:
            prev_text, prev_lang = runs[-1]
            runs[-1] = (prev_text + converted, prev_lang)
        else:
            runs.append((converted, target_lang))

        current_source_lang = None
        current_chars = []

    for ch in text:
        char_source_lang = _char_source_lang(ch)
        if char_source_lang is None:
            current_chars.append(ch)
            continue

        if current_source_lang is None:
            current_source_lang = char_source_lang
        elif char_source_lang != current_source_lang:
            flush()
            current_source_lang = char_source_lang

        current_chars.append(ch)

    flush()
    return runs


def _char_source_lang(ch: str) -> str | None:
    if "\u0400" <= ch <= "\u04ff":
        return "ru"
    if ("a" <= ch <= "z") or ("A" <= ch <= "Z"):
        return "en"
    return None
