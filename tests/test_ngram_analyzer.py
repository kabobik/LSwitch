"""Tests for lswitch.intelligence.ngram_analyzer.NgramAnalyzer."""

import pytest
from lswitch.intelligence.ngram_analyzer import NgramAnalyzer


@pytest.fixture
def analyzer() -> NgramAnalyzer:
    return NgramAnalyzer()


# ---------------------------------------------------------------------------
# score()
# ---------------------------------------------------------------------------

def test_ru_score_higher_for_russian_text(analyzer: NgramAnalyzer) -> None:
    """'привет' должен получать более высокий RU-score, чем EN-score."""
    score_ru = analyzer.score("привет", "ru")
    score_en = analyzer.score("привет", "en")
    assert score_ru > score_en, (
        f"RU-score({score_ru:.2f}) должен быть > EN-score({score_en:.2f})"
    )


def test_en_score_higher_for_english_text(analyzer: NgramAnalyzer) -> None:
    """'hello' должен получать более высокий EN-score, чем RU-score."""
    score_en = analyzer.score("hello", "en")
    score_ru = analyzer.score("hello", "ru")
    assert score_en > score_ru, (
        f"EN-score({score_en:.2f}) должен быть > RU-score({score_ru:.2f})"
    )


def test_empty_text_no_crash(analyzer: NgramAnalyzer) -> None:
    """score('', 'ru') не должен падать и возвращать числовой результат."""
    result = analyzer.score("", "ru")
    assert isinstance(result, float)


def test_short_text(analyzer: NgramAnalyzer) -> None:
    """score('ф', 'ru') не должен падать (1 символ)."""
    result = analyzer.score("ф", "ru")
    assert isinstance(result, float)


# ---------------------------------------------------------------------------
# should_convert()
# ---------------------------------------------------------------------------

def test_ghbdtn_should_convert(analyzer: NgramAnalyzer) -> None:
    """'ghbdtn' (EN-раскладка вместо 'привет') → should_convert('en') = True."""
    assert analyzer.should_convert("ghbdtn", "en") is True, (
        "Транслитерация 'ghbdtn' должна определяться как требующая конвертации"
    )


def test_hello_should_not_convert(analyzer: NgramAnalyzer) -> None:
    """'hello' правильный английский → should_convert('en') = False."""
    assert analyzer.should_convert("hello", "en") is False, (
        "Корректный английский текст не должен конвертироваться"
    )


def test_privet_should_not_convert(analyzer: NgramAnalyzer) -> None:
    """'привет' правильный русский → should_convert('ru') = False."""
    assert analyzer.should_convert("привет", "ru") is False, (
        "Корректный русский текст не должен конвертироваться"
    )


# ---------------------------------------------------------------------------
# Новые тесты: защита от ложных срабатываний
# ---------------------------------------------------------------------------

def test_numbers_not_converted(analyzer: NgramAnalyzer) -> None:
    """Числа не должны конвертироваться."""
    assert analyzer.should_convert("12345", "en") is False


def test_mixed_digits_not_converted(analyzer: NgramAnalyzer) -> None:
    """Смешанный текст с цифрами не должен конвертироваться."""
    assert analyzer.should_convert("123abc", "en") is False


def test_abbreviation_php_not_converted(analyzer: NgramAnalyzer) -> None:
    """Аббревиатура 'php' не должна конвертироваться."""
    assert analyzer.should_convert("php", "en") is False


def test_password_not_converted(analyzer: NgramAnalyzer) -> None:
    """Пароль со спецсимволами не должен конвертироваться."""
    assert analyzer.should_convert("P@ssw0rd", "en") is False


def test_ru_to_en_conversion(analyzer: NgramAnalyzer) -> None:
    """Кириллица с нулевым RU-скором (неверная раскладка) → should_convert('ru') = True.

    'йьъщ' — комбинация кириллических букв с нулевым n-gram скором в RU
    (нет таких биграмм в русском языке), что диагностирует неверную раскладку.
    """
    assert analyzer.should_convert("йьъщ", "ru") is True
