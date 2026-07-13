"""Behavior lock for AutoDetector before structured trace refactoring."""

from __future__ import annotations

from dataclasses import dataclass, field

from lswitch.intelligence.auto_detector import AutoDetector
from lswitch.intelligence.dictionary_service import DictionaryDecision


@dataclass
class _Dictionary:
    result: tuple[bool, str] = (False, "not found in any dictionary")
    calls: list[tuple[str, str]] = field(default_factory=list)

    def should_convert(self, word: str, layout: str) -> tuple[bool, str]:
        self.calls.append((word, layout))
        return self.result

    def evaluate(self, word: str, layout: str) -> DictionaryDecision:
        self.calls.append((word, layout))
        should_convert, reason = self.result
        if reason.startswith("unknown layout"):
            reason_id = "dictionary.layout.unknown"
            source_match = None
            target_match = None
        elif should_convert:
            reason_id = "dictionary.target.match"
            source_match = False
            target_match = True
        elif reason.startswith("already correct"):
            reason_id = "dictionary.source.match"
            source_match = True
            target_match = None
        else:
            reason_id = "dictionary.no_match"
            source_match = False
            target_match = False
        return DictionaryDecision(
            should_convert=should_convert,
            reason_id=reason_id,
            reason=reason,
            word=word,
            current_lang=layout,
            target_lang="ru" if layout == "en" else "en",
            converted_word="привет" if word == "ghbdtn" else None,
            source_match=source_match,
            target_match=target_match,
            source_available=True,
            target_available=True,
        )


@dataclass
class _Ngrams:
    scores: dict[tuple[str, str], float]
    calls: list[tuple[str, str]] = field(default_factory=list)

    def score(self, word: str, lang: str) -> float:
        self.calls.append((word, lang))
        return self.scores.get((word, lang), 0.0)


class _UserDictionary:
    def __init__(self, weight: int):
        self.weight = weight
        self.calls = []

    def get_weight(self, word: str, lang: str) -> int:
        self.calls.append((word, lang))
        return self.weight


def _detector(
    *,
    dictionary: _Dictionary | None = None,
    ngrams: _Ngrams | None = None,
    user_dict=None,
) -> AutoDetector:
    return AutoDetector(
        dictionary=dictionary or _Dictionary(),
        ngrams=ngrams or _Ngrams({}),
        user_dict=user_dict,
    )


def test_guards_short_circuit_before_dictionary_lookup():
    dictionary = _Dictionary()
    detector = _detector(dictionary=dictionary)

    assert detector.should_convert(None, "en") == (
        False,
        "empty or invalid input",
    )
    assert detector.should_convert(" ", "en") == (False, "empty input")
    assert detector.should_convert("abc1", "en") == (
        False,
        "non-alphabetic input",
    )
    assert dictionary.calls == []


def test_user_override_has_priority_over_dictionary():
    dictionary = _Dictionary((False, "already correct English word"))
    user_dict = _UserDictionary(2)
    detector = _detector(dictionary=dictionary, user_dict=user_dict)

    assert detector.should_convert("hello", "en") == (
        True,
        "User dict override",
    )
    assert dictionary.calls == []


def test_user_protection_has_priority_over_dictionary():
    dictionary = _Dictionary((True, "converted to Russian word 'привет'"))
    user_dict = _UserDictionary(-2)
    detector = _detector(dictionary=dictionary, user_dict=user_dict)

    assert detector.should_convert("ghbdtn", "en") == (
        False,
        "user_dict: weight=-2 <= -2",
    )
    assert dictionary.calls == []


def test_source_dictionary_match_short_circuits_ngrams():
    dictionary = _Dictionary((False, "already correct English word"))
    ngrams = _Ngrams({})
    detector = _detector(dictionary=dictionary, ngrams=ngrams)

    assert detector.should_convert("hello", "en") == (
        False,
        "already correct English word",
    )
    assert ngrams.calls == []


def test_target_dictionary_match_short_circuits_ngrams():
    dictionary = _Dictionary((True, "converted to Russian word 'привет'"))
    ngrams = _Ngrams({})
    detector = _detector(dictionary=dictionary, ngrams=ngrams)

    assert detector.should_convert("ghbdtn", "en") == (
        True,
        "converted to Russian word 'привет'",
    )
    assert ngrams.calls == []


def test_ngram_delta_converts_after_dictionary_miss():
    ngrams = _Ngrams(
        {
            ("привет", "ru"): 0.2,
            ("ghbdtn", "en"): 0.1,
        }
    )
    detector = _detector(ngrams=ngrams)

    assert detector.should_convert("ghbdtn", "en") == (
        True,
        "ngram: target=0.200 > source=0.100",
    )


def test_zero_source_fallback_converts_long_word():
    ngrams = _Ngrams(
        {
            ("фывф", "ru"): 0.0,
            ("asdf", "en"): 0.0,
        }
    )
    detector = _detector(ngrams=ngrams)

    assert detector.should_convert("asdf", "en") == (
        True,
        "ngram: zero source score, likely wrong layout",
    )


def test_no_evidence_keeps_word():
    ngrams = _Ngrams(
        {
            ("фыв", "ru"): 0.0,
            ("asd", "en"): 0.0,
        }
    )
    detector = _detector(ngrams=ngrams)

    assert detector.should_convert("asd", "en") == (
        False,
        "no evidence of wrong layout",
    )


def test_unknown_layout_is_kept_after_dictionary_miss():
    dictionary = _Dictionary((False, "unknown layout: fr"))
    ngrams = _Ngrams({})
    detector = _detector(dictionary=dictionary, ngrams=ngrams)

    assert detector.should_convert("bonjour", "fr") == (
        False,
        "unknown layout: fr",
    )
    assert ngrams.calls == []
