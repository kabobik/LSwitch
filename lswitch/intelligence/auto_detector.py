"""AutoDetector — integrates DictionaryService and NgramAnalyzer for layout detection."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from lswitch.core.decision_trace import (
    DecisionOutcome,
    DecisionTraceStep,
    StepState,
    TraceFact,
)
from lswitch.intelligence.dictionary_service import DictionaryDecision

if TYPE_CHECKING:
    from lswitch.intelligence.dictionary_service import DictionaryService
    from lswitch.intelligence.ngram_analyzer import NgramAnalyzer
    from lswitch.intelligence.user_dictionary import UserDictionary

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AutoDecision:
    """Structured automatic-layout decision with ordered rule evidence."""

    outcome: DecisionOutcome
    reason_id: str
    reason: str
    original: str
    source_lang: str
    converted: str | None = None
    target_lang: str | None = None
    steps: tuple[DecisionTraceStep, ...] = ()

    @property
    def should_convert(self) -> bool:
        return self.outcome is DecisionOutcome.CONVERT


class AutoDetector:
    """Decides whether a word needs layout conversion.

    Boundary priority chain:
    1. Exact user policy decides convert/keep.
    2. Exact source-system word vetoes conversion.
    3. Strict n-gram evidence is the final fallback.
    """

    def __init__(self, dictionary: "DictionaryService", ngrams: "NgramAnalyzer",
                 user_dict: "UserDictionary | None" = None,
                 user_dict_min_weight: int = 2):
        self.dictionary = dictionary
        self.ngrams = ngrams
        self.user_dict = user_dict
        self.user_dict_min_weight = user_dict_min_weight

    def evaluate(
        self,
        word: str | None,
        current_layout: str,
        *,
        ngram_min_length: int = 0,
    ) -> AutoDecision:
        """Evaluate a candidate once and retain every reached rule."""
        steps: list[DecisionTraceStep] = []

        if not isinstance(word, str):
            return AutoDecision(
                outcome=DecisionOutcome.SKIP,
                reason_id="candidate.invalid",
                reason="empty or invalid input",
                original="",
                source_lang=current_layout,
                steps=(
                    self._step(
                        "candidate.invalid",
                        StepState.MATCHED,
                        decisive=True,
                        input_type=type(word).__name__,
                    ),
                ),
            )

        word_clean = word.strip()
        if not word_clean:
            return AutoDecision(
                outcome=DecisionOutcome.SKIP,
                reason_id="candidate.empty",
                reason="empty input",
                original="",
                source_lang=current_layout,
                steps=(
                    self._step(
                        "candidate.empty",
                        StepState.MATCHED,
                        decisive=True,
                    ),
                ),
            )

        from lswitch.intelligence.maps import EN_TO_RU, RU_TO_EN

        if current_layout == "en":
            valid_characters = all(
                c.isalpha() or EN_TO_RU.get(c.lower(), "").isalpha()
                for c in word_clean
            )
        elif current_layout == "ru":
            valid_characters = all(
                c.isalpha() or RU_TO_EN.get(c.lower(), "").isalpha()
                for c in word_clean
            )
        else:
            valid_characters = word_clean.isalpha()

        if not valid_characters:
            return AutoDecision(
                outcome=DecisionOutcome.SKIP,
                reason_id="candidate.non_alphabetic",
                reason="non-alphabetic input",
                original=word_clean,
                source_lang=current_layout,
                steps=(
                    self._step(
                        "candidate.non_alphabetic",
                        StepState.MATCHED,
                        decisive=True,
                        length=len(word_clean),
                    ),
                ),
            )

        steps.append(
            self._step(
                "candidate.valid",
                StepState.MATCHED,
                length=len(word_clean),
                layout=current_layout,
            )
        )

        normalized = word_clean.lower()
        converted, target_lang = self._converted_word(
            normalized,
            current_layout,
        )

        if self.user_dict:
            weight = self.user_dict.get_weight(normalized, current_layout)
            min_w = self.user_dict_min_weight

            if weight >= min_w:
                steps.append(
                    self._step(
                        "auto.user_dictionary.override",
                        StepState.MATCHED,
                        decisive=True,
                        weight=weight,
                        threshold=min_w,
                    )
                )
                return AutoDecision(
                    outcome=DecisionOutcome.CONVERT,
                    reason_id="auto.user_dictionary.override",
                    reason="User dict override",
                    original=word_clean,
                    converted=converted,
                    source_lang=current_layout,
                    target_lang=target_lang,
                    steps=tuple(steps),
                )
            if weight <= -min_w:
                steps.append(
                    self._step(
                        "auto.user_dictionary.protection",
                        StepState.MATCHED,
                        decisive=True,
                        weight=weight,
                        threshold=-min_w,
                    )
                )
                return AutoDecision(
                    outcome=DecisionOutcome.KEEP,
                    reason_id="auto.user_dictionary.protection",
                    reason=f"user_dict: weight={weight} <= -{min_w}",
                    original=word_clean,
                    converted=converted,
                    source_lang=current_layout,
                    target_lang=target_lang,
                    steps=tuple(steps),
                )
            steps.append(
                self._step(
                    "auto.user_dictionary.neutral",
                    StepState.NOT_MATCHED,
                    weight=weight,
                    threshold=min_w,
                )
            )
        else:
            steps.append(
                self._step(
                    "auto.user_dictionary.disabled",
                    StepState.SKIPPED,
                )
            )

        evaluate_source = getattr(
            type(self.dictionary),
            "evaluate_source",
            None,
        )
        dictionary_decision = (
            evaluate_source(self.dictionary, word_clean, current_layout)
            if callable(evaluate_source)
            else self.dictionary.evaluate(word_clean, current_layout)
        )
        if not isinstance(dictionary_decision, DictionaryDecision):
            raise TypeError("DictionaryService.evaluate() returned invalid result")

        if dictionary_decision.reason_id == "dictionary.layout.unknown":
            steps.append(
                self._step(
                    "auto.layout.unknown",
                    StepState.MATCHED,
                    decisive=True,
                    layout=current_layout,
                )
            )
            return AutoDecision(
                outcome=DecisionOutcome.SKIP,
                reason_id="auto.layout.unknown",
                reason=dictionary_decision.reason,
                original=word_clean,
                source_lang=current_layout,
                steps=tuple(steps),
            )

        source_state = (
            StepState.UNAVAILABLE
            if not dictionary_decision.source_available
            else StepState.MATCHED
            if dictionary_decision.source_match
            else StepState.NOT_MATCHED
        )
        steps.append(
            self._step(
                "auto.source_dictionary.match",
                source_state,
                decisive=bool(dictionary_decision.source_match),
                available=dictionary_decision.source_available,
                lang=current_layout,
                word=normalized,
            )
        )
        if dictionary_decision.source_match:
            return AutoDecision(
                outcome=DecisionOutcome.KEEP,
                reason_id="auto.source_dictionary.match",
                reason=dictionary_decision.reason,
                original=word_clean,
                converted=converted,
                source_lang=current_layout,
                target_lang=target_lang,
                steps=tuple(steps),
            )

        if converted is None or target_lang is None:
            steps.append(
                self._step(
                    "auto.layout.unknown",
                    StepState.MATCHED,
                    decisive=True,
                    layout=current_layout,
                )
            )
            return AutoDecision(
                outcome=DecisionOutcome.SKIP,
                reason_id="auto.layout.unknown",
                reason=f"unknown layout: {current_layout}",
                original=word_clean,
                source_lang=current_layout,
                steps=tuple(steps),
            )

        minimum = max(0, int(ngram_min_length))
        if len(normalized) < minimum:
            steps.append(
                self._step(
                    "auto.ngram.min_length",
                    StepState.NOT_MATCHED,
                    decisive=True,
                    length=len(normalized),
                    minimum=minimum,
                )
            )
            return AutoDecision(
                outcome=DecisionOutcome.SKIP,
                reason_id="auto.ngram.min_length",
                reason="word below n-gram fallback threshold",
                original=word_clean,
                converted=converted,
                source_lang=current_layout,
                target_lang=target_lang,
                steps=tuple(steps),
            )

        steps.append(
            self._step(
                "auto.ngram.min_length",
                StepState.MATCHED,
                length=len(normalized),
                minimum=minimum,
            )
        )

        score_target = self.ngrams.score(converted, target_lang)
        score_source = self.ngrams.score(normalized, current_layout)

        threshold = 0.05
        delta = score_target - score_source
        ngram_matches = score_target > 0.0 and delta > threshold
        steps.append(
            self._step(
                "auto.ngram.delta",
                StepState.MATCHED if ngram_matches else StepState.NOT_MATCHED,
                decisive=ngram_matches,
                source_score=score_source,
                target_score=score_target,
                delta=delta,
                threshold=threshold,
                target_positive=score_target > 0.0,
            )
        )
        if ngram_matches:
            return AutoDecision(
                outcome=DecisionOutcome.CONVERT,
                reason_id="auto.ngram.delta",
                reason=(
                    f"ngram: target={score_target:.3f} "
                    f"> source={score_source:.3f}"
                ),
                original=word_clean,
                converted=converted,
                source_lang=current_layout,
                target_lang=target_lang,
                steps=tuple(steps),
            )

        steps.append(
            self._step(
                "auto.no_evidence",
                StepState.MATCHED,
                decisive=True,
            )
        )
        return AutoDecision(
            outcome=DecisionOutcome.KEEP,
            reason_id="auto.no_evidence",
            reason="no evidence of wrong layout",
            original=word_clean,
            converted=converted,
            source_lang=current_layout,
            target_lang=target_lang,
            steps=tuple(steps),
        )

    def should_convert(
        self,
        word: str | None,
        current_layout: str,
    ) -> tuple[bool, str]:
        """Compatibility wrapper preserving the legacy tuple contract."""
        decision = self.evaluate(word, current_layout)
        return decision.should_convert, decision.reason

    @staticmethod
    def _converted_word(
        word: str,
        current_layout: str,
    ) -> tuple[str | None, str | None]:
        from lswitch.intelligence.maps import EN_TO_RU, RU_TO_EN

        if current_layout == "en":
            return "".join(EN_TO_RU.get(char, char) for char in word), "ru"
        if current_layout == "ru":
            return "".join(RU_TO_EN.get(char, char) for char in word), "en"
        return None, None

    @staticmethod
    def _step(
        rule_id: str,
        state: StepState,
        *,
        decisive: bool = False,
        **facts,
    ) -> DecisionTraceStep:
        return DecisionTraceStep(
            rule_id=rule_id,
            state=state,
            decisive=decisive,
            facts=tuple(
                TraceFact(key=key, value=value)
                for key, value in facts.items()
            ),
        )
