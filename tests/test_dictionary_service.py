"""Tests for DictionaryService — Этап 1.1."""

import pytest
from lswitch.intelligence.dictionary_service import DictionaryService


@pytest.fixture
def svc() -> DictionaryService:
    return DictionaryService()


def test_ru_word_recognized(svc: DictionaryService) -> None:
    """'привет' must be found in the Russian dictionary."""
    assert svc.in_ru("привет") is True


def test_en_word_recognized(svc: DictionaryService) -> None:
    """'hello' must be found in the English dictionary."""
    assert svc.in_en("hello") is True


def test_ru_word_not_in_en(svc: DictionaryService) -> None:
    """'привет' must NOT be found in the English dictionary."""
    assert svc.in_en("привет") is False


def test_en_word_not_in_ru(svc: DictionaryService) -> None:
    """'hello' must NOT be found in the Russian dictionary."""
    assert svc.in_ru("hello") is False


def test_should_convert_ghbdtn(svc: DictionaryService) -> None:
    """'ghbdtn' typed on EN layout is 'привет' → should convert."""
    result, reason = svc.should_convert("ghbdtn", "en")
    assert result is True, f"Expected True, reason: {reason}"


def test_should_not_convert_hello(svc: DictionaryService) -> None:
    """'hello' is a valid English word → should NOT convert."""
    result, reason = svc.should_convert("hello", "en")
    assert result is False, f"Expected False, reason: {reason}"


def test_should_convert_privet_from_ru(svc: DictionaryService) -> None:
    """'привет' typed on RU layout is already correct → should NOT convert."""
    result, reason = svc.should_convert("привет", "ru")
    assert result is False, f"Expected False, reason: {reason}"


def test_in_any_ru(svc: DictionaryService) -> None:
    assert svc.in_any("привет") is True


def test_in_any_en(svc: DictionaryService) -> None:
    assert svc.in_any("hello") is True


def test_in_any_unknown(svc: DictionaryService) -> None:
    assert svc.in_any("xyzqwerty") is False


def test_case_insensitive_ru(svc: DictionaryService) -> None:
    assert svc.in_ru("ПРИВЕТ") is True


def test_case_insensitive_en(svc: DictionaryService) -> None:
    assert svc.in_en("HELLO") is True


def test_should_convert_ru_typed_on_ru_layout(svc):
    """'руддщ' набрано в RU раскладке → 'hello' → должно конвертироваться."""
    result, reason = svc.should_convert("руддщ", "ru")
    assert result is True


def test_empty_string_no_crash(svc):
    result, _ = svc.should_convert("", "en")
    assert result is False


def test_none_input_no_crash(svc):
    result, _ = svc.should_convert(None, "en")
    assert result is False


def test_unknown_layout_returns_false(svc):
    result, reason = svc.should_convert("hello", "fr")
    assert result is False
