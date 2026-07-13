"""Tests for ordered structured mid-word decisions."""

from __future__ import annotations

from lswitch.core.decision_trace import DecisionOutcome, StepState
from lswitch.intelligence.mid_word_detector import MidWordDetector
from lswitch.intelligence.prefix_dictionary import (
    PrefixDictionary,
    PrefixDictionarySource,
)


def _dictionary() -> PrefixDictionary:
    return PrefixDictionary(
        en_words={"hello", "help", "world"},
        ru_words={"привет", "пример", "пока"},
    )


def _ids(decision) -> list[str]:
    return [step.rule_id for step in decision.steps]


def _facts(step) -> dict:
    return {fact.key: fact.value for fact in step.facts}


class _UserDictionary:
    def __init__(self, weights: dict[tuple[str, str], int]):
        self.weights = weights

    def get_weight(self, word: str, lang: str) -> int:
        return self.weights.get((word, lang), 0)


def test_short_prefix_is_a_decisive_skip():
    decision = MidWordDetector(_dictionary(), min_prefix_len=4).should_switch(
        "ghb",
        "en",
    )

    assert decision.outcome is DecisionOutcome.SKIP
    assert decision.reason_id == "midword.prefix_length"
    assert _ids(decision) == ["midword.prefix_length"]
    assert decision.steps[0].state is StepState.NOT_MATCHED
    assert decision.steps[0].decisive is True
    assert _facts(decision.steps[0]) == {"length": 3, "minimum": 4}


def test_case_rule_follows_successful_length_rule():
    decision = MidWordDetector(_dictionary(), min_prefix_len=4).should_switch(
        "GhbD",
        "en",
    )

    assert decision.outcome is DecisionOutcome.KEEP
    assert _ids(decision) == ["midword.prefix_length", "midword.case"]
    assert decision.steps[-1].decisive is True


def test_source_prefix_match_stops_before_target_rule():
    decision = MidWordDetector(_dictionary(), min_prefix_len=4).should_switch(
        "hell",
        "en",
    )

    assert decision.reason_id == "midword.source_prefix"
    assert _ids(decision) == [
        "midword.prefix_length",
        "midword.case",
        "midword.characters",
        "midword.source_prefix",
    ]
    assert _facts(decision.steps[-1])["count"] == 1
    assert decision.steps[-1].decisive is True


def test_missing_target_prefix_records_source_miss_first():
    decision = MidWordDetector(_dictionary(), min_prefix_len=4).should_switch(
        "asdf",
        "en",
    )

    assert decision.reason_id == "midword.target_prefix"
    assert _ids(decision)[-2:] == [
        "midword.source_prefix",
        "midword.target_prefix",
    ]
    assert decision.steps[-2].state is StepState.NOT_MATCHED
    assert decision.steps[-1].state is StepState.NOT_MATCHED
    assert decision.steps[-1].decisive is True


def test_user_protection_is_recorded_after_target_evidence():
    detector = MidWordDetector(
        _dictionary(),
        min_prefix_len=4,
        user_dict=_UserDictionary({("ghbd", "en"): -2}),
        user_dict_min_weight=2,
    )

    decision = detector.should_switch("ghbd", "en")

    assert decision.reason_id == "midword.user_protection"
    assert _ids(decision)[-1] == "midword.user_protection"
    assert _facts(decision.steps[-1]) == {
        "prefix": "ghbd",
        "weight": -2,
        "threshold": -2,
    }


def test_successful_switch_has_explicit_decisive_rule():
    decision = MidWordDetector(_dictionary(), min_prefix_len=4).should_switch(
        "ghbd",
        "en",
    )

    assert decision.outcome is DecisionOutcome.CONVERT
    assert decision.reason_id == "midword.switch"
    assert _ids(decision)[-2:] == [
        "midword.user_dictionary.disabled",
        "midword.switch",
    ]
    assert decision.steps[-1].decisive is True
    assert decision.converted_prefix == "прив"


def test_prefix_steps_capture_active_dictionary_source_metadata():
    sources = {
        "en": (
            PrefixDictionarySource(
                lang="en",
                kind="builtin",
                enabled=True,
                loaded=True,
                word_count=1,
            ),
        ),
        "ru": (
            PrefixDictionarySource(
                lang="ru",
                kind="builtin",
                enabled=True,
                loaded=True,
                word_count=1,
            ),
            PrefixDictionarySource(
                lang="ru",
                kind="system",
                enabled=True,
                loaded=True,
                word_count=100,
                path="/usr/share/hunspell/ru_RU.dic",
            ),
        ),
    }
    dictionary = PrefixDictionary(
        en_words={"hello"},
        ru_words={"привет"},
        sources=sources,
    )

    decision = MidWordDetector(dictionary, min_prefix_len=4).should_switch(
        "ghbd",
        "en",
    )
    target_step = next(
        step
        for step in decision.steps
        if step.rule_id == "midword.target_prefix"
    )
    facts = _facts(target_step)

    assert facts["dictionary_source_count"] == 2
    assert facts["dictionary_1_kind"] == "system"
    assert facts["dictionary_1_path"] == "/usr/share/hunspell/ru_RU.dic"
    assert len(decision.dictionary_sources) == 3
