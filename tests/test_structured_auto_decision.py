"""Tests for ordered structured AutoDetector decisions."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

from lswitch.core.decision_trace import DecisionOutcome, StepState
from lswitch.intelligence.auto_detector import AutoDetector
from lswitch.intelligence.dictionary_service import (
    DictionaryDecision,
    DictionaryService,
)
from lswitch.intelligence.ngram_analyzer import NgramAnalyzer


def _rule_ids(decision) -> list[str]:
    return [step.rule_id for step in decision.steps]


def _facts(step) -> dict:
    return {fact.key: fact.value for fact in step.facts}


@dataclass
class _StaticDictionary:
    decision: DictionaryDecision

    def evaluate(self, word: str, layout: str) -> DictionaryDecision:
        return self.decision


class _Scores:
    def __init__(self, source: float, target: float):
        self.source = source
        self.target = target

    def score(self, word: str, lang: str) -> float:
        return self.target if lang == "ru" else self.source


class _UserDictionary:
    def __init__(self, weight: int):
        self.weight = weight

    def get_weight(self, word: str, lang: str) -> int:
        return self.weight


def _dictionary_miss() -> DictionaryDecision:
    return DictionaryDecision(
        should_convert=False,
        reason_id="dictionary.no_match",
        reason="not found in any dictionary",
        word="ghbdtn",
        current_lang="en",
        target_lang="ru",
        converted_word="привет",
        source_match=False,
        target_match=False,
        source_available=True,
        target_available=True,
    )


def test_source_dictionary_match_is_decisive_keep():
    detector = AutoDetector(
        DictionaryService(en_words={"hello"}, ru_words={"привет"}),
        NgramAnalyzer(),
    )

    decision = detector.evaluate("hello", "en")

    assert decision.outcome is DecisionOutcome.KEEP
    assert decision.reason_id == "auto.source_dictionary.match"
    assert _rule_ids(decision) == [
        "candidate.valid",
        "auto.user_dictionary.disabled",
        "auto.source_dictionary.match",
    ]
    assert decision.steps[-1].decisive is True
    assert decision.steps[-1].state is StepState.MATCHED


def test_target_dictionary_match_is_left_to_ngram_fallback():
    detector = AutoDetector(
        DictionaryService(en_words={"hello"}, ru_words={"привет"}),
        NgramAnalyzer(),
    )

    decision = detector.evaluate("ghbdtn", "en")

    assert decision.outcome is DecisionOutcome.CONVERT
    assert decision.converted == "привет"
    assert _rule_ids(decision) == [
        "candidate.valid",
        "auto.user_dictionary.disabled",
        "auto.source_dictionary.match",
        "auto.ngram.min_length",
        "auto.ngram.delta",
    ]
    assert decision.steps[-3].state is StepState.NOT_MATCHED
    assert decision.steps[-1].decisive is True


def test_boundary_detector_uses_source_only_dictionary_api():
    service = DictionaryService(
        en_words={"hello"},
        ru_words={"привет"},
    )
    service.evaluate = MagicMock(
        side_effect=AssertionError("legacy target lookup must not run")
    )
    detector = AutoDetector(service, NgramAnalyzer())

    decision = detector.evaluate("ghbdtn", "en")

    assert decision.outcome is DecisionOutcome.CONVERT
    service.evaluate.assert_not_called()


def test_user_override_short_circuits_dictionary_rules():
    detector = AutoDetector(
        DictionaryService(),
        NgramAnalyzer(),
        user_dict=_UserDictionary(2),
    )

    decision = detector.evaluate("hello", "en")

    assert decision.outcome is DecisionOutcome.CONVERT
    assert _rule_ids(decision) == [
        "candidate.valid",
        "auto.user_dictionary.override",
    ]
    assert _facts(decision.steps[-1]) == {"weight": 2, "threshold": 2}


def test_user_protection_is_decisive_keep():
    detector = AutoDetector(
        DictionaryService(),
        NgramAnalyzer(),
        user_dict=_UserDictionary(-3),
    )

    decision = detector.evaluate("ghbdtn", "en")

    assert decision.outcome is DecisionOutcome.KEEP
    assert decision.reason_id == "auto.user_dictionary.protection"
    assert decision.steps[-1].decisive is True


def test_exact_user_decision_ignores_ngram_minimum_length():
    detector = AutoDetector(
        DictionaryService(),
        _Scores(source=0.0, target=0.0),
        user_dict=_UserDictionary(2),
    )

    decision = detector.evaluate("ghb", "en", ngram_min_length=10)

    assert decision.outcome is DecisionOutcome.CONVERT
    assert decision.reason_id == "auto.user_dictionary.override"
    assert "auto.ngram.min_length" not in _rule_ids(decision)


def test_ngram_minimum_length_applies_only_after_user_and_source_rules():
    detector = AutoDetector(
        _StaticDictionary(_dictionary_miss()),
        _Scores(source=0.0, target=0.2),
    )

    decision = detector.evaluate("ghb", "en", ngram_min_length=10)

    assert decision.outcome is DecisionOutcome.SKIP
    assert decision.reason_id == "auto.ngram.min_length"
    assert _rule_ids(decision)[-2:] == [
        "auto.source_dictionary.match",
        "auto.ngram.min_length",
    ]


def test_unavailable_source_dictionary_is_not_reported_as_a_miss():
    unavailable = DictionaryDecision(
        **{
            **_dictionary_miss().__dict__,
            "source_available": False,
        }
    )
    detector = AutoDetector(
        _StaticDictionary(unavailable),
        _Scores(source=0.0, target=0.0),
    )

    decision = detector.evaluate("ghbdtn", "en")

    source_step = next(
        step
        for step in decision.steps
        if step.rule_id == "auto.source_dictionary.match"
    )
    assert source_step.state is StepState.UNAVAILABLE


def test_ngram_delta_captures_scores_delta_and_threshold():
    detector = AutoDetector(
        _StaticDictionary(_dictionary_miss()),
        _Scores(source=0.1, target=0.2),
    )

    decision = detector.evaluate("ghbdtn", "en")

    assert decision.outcome is DecisionOutcome.CONVERT
    assert decision.reason_id == "auto.ngram.delta"
    assert _rule_ids(decision)[-1] == "auto.ngram.delta"
    assert _facts(decision.steps[-1]) == {
        "source_score": 0.1,
        "target_score": 0.2,
        "delta": 0.1,
        "threshold": 0.05,
        "target_positive": True,
    }


def test_zero_source_without_target_evidence_reaches_no_evidence():
    detector = AutoDetector(
        _StaticDictionary(_dictionary_miss()),
        _Scores(source=0.0, target=0.0),
    )

    decision = detector.evaluate("ghbdtn", "en")

    assert decision.reason_id == "auto.no_evidence"
    assert _rule_ids(decision)[-2:] == [
        "auto.ngram.delta",
        "auto.no_evidence",
    ]
    assert decision.steps[-2].state is StepState.NOT_MATCHED
    assert decision.steps[-1].decisive is True


def test_no_evidence_is_final_keep_rule_for_short_zero_score_word():
    miss = DictionaryDecision(
        **{
            **_dictionary_miss().__dict__,
            "word": "asd",
            "converted_word": "фыв",
        }
    )
    detector = AutoDetector(
        _StaticDictionary(miss),
        _Scores(source=0.0, target=0.0),
    )

    decision = detector.evaluate("asd", "en")

    assert decision.outcome is DecisionOutcome.KEEP
    assert decision.reason_id == "auto.no_evidence"
    assert _rule_ids(decision)[-1] == "auto.no_evidence"
    assert decision.steps[-1].decisive is True


def test_invalid_candidate_stops_before_optional_services():
    detector = AutoDetector(DictionaryService(), NgramAnalyzer())

    decision = detector.evaluate("abc1", "en")

    assert decision.outcome is DecisionOutcome.SKIP
    assert decision.reason_id == "candidate.non_alphabetic"
    assert _rule_ids(decision) == ["candidate.non_alphabetic"]


def test_dictionary_service_exposes_structured_match_and_miss():
    service = DictionaryService(
        en_words={"hello"},
        ru_words={"привет"},
    )

    source = service.evaluate("hello", "en")
    target = service.evaluate("ghbdtn", "en")
    miss = service.evaluate("asd", "en")
    unknown = service.evaluate("bonjour", "fr")

    assert source.source_match is True
    assert source.target_match is None
    assert target.source_match is False
    assert target.target_match is True
    assert target.converted_word == "привет"
    assert miss.source_match is False
    assert miss.target_match is False
    assert unknown.reason_id == "dictionary.layout.unknown"
