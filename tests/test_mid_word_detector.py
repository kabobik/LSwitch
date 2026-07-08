"""Tests for mid-word layout detector."""

from __future__ import annotations

from lswitch.intelligence.mid_word_detector import MidWordDetector
from lswitch.intelligence.prefix_dictionary import PrefixDictionary


def _detector() -> MidWordDetector:
    dictionary = PrefixDictionary(
        en_words={"hello", "help", "world"},
        ru_words={"привет", "пример", "пока"},
    )
    return MidWordDetector(dictionary, min_prefix_len=4)


def test_mid_word_detector_switches_en_to_ru_when_target_prefix_exists():
    decision = _detector().should_switch("ghbd", "en")

    assert decision.should_switch is True
    assert decision.target_lang == "ru"
    assert decision.converted_prefix == "прив"
    assert decision.source_prefix_count == 0
    assert decision.target_prefix_count == 1


def test_mid_word_detector_switches_ru_to_en_when_target_prefix_exists():
    decision = _detector().should_switch("рудд", "ru")

    assert decision.should_switch is True
    assert decision.target_lang == "en"
    assert decision.converted_prefix == "hell"
    assert decision.source_prefix_count == 0
    assert decision.target_prefix_count == 1


def test_mid_word_detector_keeps_when_source_prefix_exists():
    decision = _detector().should_switch("hell", "en")

    assert decision.should_switch is False
    assert decision.reason == "source prefix exists"
    assert decision.source_prefix_count == 1


def test_mid_word_detector_keeps_short_prefixes():
    decision = _detector().should_switch("ghb", "en")

    assert decision.should_switch is False
    assert decision.reason == "prefix below threshold"


def test_mid_word_detector_rejects_non_prefix_input():
    decision = _detector().should_switch("ghb1", "en")

    assert decision.should_switch is False
    assert decision.reason == "non-prefix input"


def test_mid_word_detector_rejects_uppercase_and_mixed_case():
    decision = _detector().should_switch("GhbD", "en")

    assert decision.should_switch is False
    assert decision.reason == "mixed or uppercase input"


def test_mid_word_detector_rejects_unknown_layout():
    decision = _detector().should_switch("abcd", "fr")

    assert decision.should_switch is False
    assert "unknown layout" in decision.reason


def test_mid_word_detector_requires_target_prefix_count_threshold():
    dictionary = PrefixDictionary(en_words={"hello"}, ru_words={"привет"})
    detector = MidWordDetector(
        dictionary,
        min_prefix_len=4,
        min_target_prefix_count=2,
    )

    decision = detector.should_switch("ghbd", "en")

    assert decision.should_switch is False
    assert decision.reason == "target prefix not found"
    assert decision.target_prefix_count == 1
