"""Tests for mid-word layout detector."""

from __future__ import annotations

from lswitch.intelligence.mid_word_detector import MidWordDetector
from lswitch.intelligence.prefix_dictionary import PrefixDictionary
from lswitch.intelligence.user_dictionary import UserPolicyMatch


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


class _UserDictionary:
    def __init__(self, weights: dict[tuple[str, str], int]):
        self.weights = weights

    def get_weight(self, word: str, lang: str) -> int:
        return self.weights.get((word, lang), 0)

    def lookup_policy(
        self,
        prefix: str,
        lang: str,
        *,
        min_weight: int,
    ) -> UserPolicyMatch:
        weight = self.get_weight(prefix, lang)
        exact_action = (
            "convert"
            if weight >= min_weight
            else "keep"
            if weight <= -min_weight
            else None
        )
        return UserPolicyMatch(
            prefix=prefix,
            lang=lang,
            exact_action=exact_action,
            exact_weight=weight if exact_action else 0,
            has_convert_descendants=any(
                word_lang == lang
                and word.startswith(prefix)
                and word != prefix
                and candidate_weight >= min_weight
                for (word, word_lang), candidate_weight in self.weights.items()
            ),
            has_keep_descendants=any(
                word_lang == lang
                and word.startswith(prefix)
                and word != prefix
                and candidate_weight <= -min_weight
                for (word, word_lang), candidate_weight in self.weights.items()
            ),
        )


def test_mid_word_detector_respects_user_rejected_prefix():
    dictionary = PrefixDictionary(ru_words={"привет"})
    detector = MidWordDetector(
        dictionary,
        min_prefix_len=4,
        user_dict=_UserDictionary({("ghbd", "en"): -2}),
        user_dict_min_weight=2,
    )

    decision = detector.should_switch("ghbd", "en")

    assert decision.should_switch is False
    assert decision.reason == "exact user dictionary keep decision"


def test_mid_word_detector_releases_exact_keep_after_prefix_diverges():
    dictionary = PrefixDictionary(ru_words={"приветик"})
    detector = MidWordDetector(
        dictionary,
        min_prefix_len=4,
        user_dict=_UserDictionary({("ghbd", "en"): -2}),
        user_dict_min_weight=2,
    )

    decision = detector.should_switch("ghbdtn", "en")

    assert decision.should_switch is True
    assert decision.reason == "target prefix found and source prefix absent"


def test_mid_word_detector_reserves_user_dictionary_proper_prefix():
    dictionary = PrefixDictionary(ru_words={"привет"})
    detector = MidWordDetector(
        dictionary,
        min_prefix_len=4,
        user_dict=_UserDictionary({("ghbdtn", "en"): 2}),
        user_dict_min_weight=2,
    )

    decision = detector.should_switch("ghbd", "en")

    assert decision.should_switch is False
    assert decision.reason == "user dictionary prefix reserved"


def test_mid_word_detector_exact_user_convert_bypasses_system_minimum_length():
    detector = MidWordDetector(
        PrefixDictionary(),
        min_prefix_len=4,
        user_dict=_UserDictionary({("ghb", "en"): 2}),
        user_dict_min_weight=2,
    )

    decision = detector.should_switch("ghb", "en")

    assert decision.should_switch is True
    assert decision.reason_id == "midword.user_dictionary.exact_convert"


def test_mid_word_detector_waits_for_opposite_user_descendant():
    detector = MidWordDetector(
        PrefixDictionary(),
        min_prefix_len=4,
        user_dict=_UserDictionary(
            {
                ("foo", "en"): 2,
                ("foobar", "en"): -2,
            }
        ),
        user_dict_min_weight=2,
    )

    decision = detector.should_switch("foo", "en")

    assert decision.should_switch is False
    assert decision.reason_id == "midword.user_dictionary.prefix_reserved"
