"""Integration tests for AutoDetector (DictionaryService + NgramAnalyzer pipeline).

Covers stage 1.3 from TODO.md: verify the full detection pipeline works end-to-end
with real data (no mocks).
"""
from __future__ import annotations

import pytest

from unittest.mock import MagicMock

from lswitch.intelligence.dictionary_service import DictionaryService
from lswitch.intelligence.ngram_analyzer import NgramAnalyzer
from lswitch.intelligence.auto_detector import AutoDetector
from lswitch.intelligence.user_dictionary import UserDictionary


@pytest.fixture(scope="module")
def detector() -> AutoDetector:
    return AutoDetector(dictionary=DictionaryService(), ngrams=NgramAnalyzer())


def test_ghbdtn_should_convert(detector):
    """Classical EN→RU translit: 'ghbdtn' is 'привет' typed in EN layout."""
    ok, reason = detector.should_convert("ghbdtn", "en")
    assert ok is True


def test_hello_no_convert(detector):
    """Correct EN word — should not be converted."""
    ok, reason = detector.should_convert("hello", "en")
    assert ok is False


def test_privet_ru_no_convert(detector):
    """Correct RU word — should not be converted."""
    ok, reason = detector.should_convert("привет", "ru")
    assert ok is False


def test_privet_wrong_layout(detector):
    """'ghbdtn' is 'привет' typed in EN layout → needs conversion to RU."""
    ok, reason = detector.should_convert("ghbdtn", "en")
    assert ok is True


def test_number_no_convert(detector):
    """Numbers are never converted."""
    ok, reason = detector.should_convert("12345", "en")
    assert ok is False


def test_empty_no_crash(detector):
    """Empty string must not crash and must return False."""
    ok, reason = detector.should_convert("", "en")
    assert ok is False


def test_none_no_crash(detector):
    """None must not crash and must return False."""
    ok, reason = detector.should_convert(None, "en")
    assert ok is False


def test_reason_is_string(detector):
    """Result reason must always be a non-empty string."""
    _, reason = detector.should_convert("ghbdtn", "en")
    assert isinstance(reason, str) and len(reason) > 0


def test_result_is_tuple(detector):
    """should_convert must always return a 2-tuple (bool, str)."""
    result = detector.should_convert("ghbdtn", "en")
    assert isinstance(result, tuple) and len(result) == 2
    ok, reason = result
    assert isinstance(ok, bool)
    assert isinstance(reason, str)


def test_mixed_content_no_convert(detector):
    """Mixed alphanumeric input is not converted."""
    ok, reason = detector.should_convert("abc123", "en")
    assert ok is False


def test_unknown_layout_no_crash(detector):
    """Unknown layout should not crash, returns False."""
    ok, reason = detector.should_convert("hello", "fr")
    assert ok is False


def test_user_dict_positive_override():
    # word "hello" is valid EN word, so normally shouldn't be converted
    detector = AutoDetector(dictionary=DictionaryService(), ngrams=NgramAnalyzer())
    ok, _ = detector.should_convert("hello", "en")
    assert ok is False  # baseline
    
    mock_ud = MagicMock(spec=UserDictionary)
    mock_ud.get_weight.return_value = 5  # >= default 2
    
    detector.user_dict = mock_ud
    ok, reason = detector.should_convert("hello", "en")
    assert ok is True
    assert "User dict override" in reason

def test_user_dict_negative_protection():
    # word "ghbdtn" is generic typo, normally converted
    detector = AutoDetector(dictionary=DictionaryService(), ngrams=NgramAnalyzer())
    ok, _ = detector.should_convert("ghbdtn", "en")
    assert ok is True  # baseline
    
    mock_ud = MagicMock(spec=UserDictionary)
    mock_ud.get_weight.return_value = -3  # <= -2
    
    detector.user_dict = mock_ud
    ok, reason = detector.should_convert("ghbdtn", "en")
    assert ok is False
    assert "user_dict: weight=" in reason

