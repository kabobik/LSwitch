"""Mid-word layout detector based on prefix dictionary evidence."""

from __future__ import annotations

from dataclasses import dataclass

from lswitch.core.decision_trace import (
    DecisionOutcome,
    DecisionTraceStep,
    StepState,
    TraceFact,
)
from lswitch.intelligence.maps import EN_TO_RU, RU_TO_EN
from lswitch.intelligence.prefix_dictionary import (
    PrefixDictionary,
    PrefixDictionarySource,
)
from lswitch.intelligence.user_dictionary import UserPolicyMatch


@dataclass(frozen=True)
class MidWordDecision:
    should_switch: bool
    reason: str
    current_lang: str
    target_lang: str | None = None
    typed_prefix: str = ""
    converted_prefix: str = ""
    source_prefix_count: int = 0
    target_prefix_count: int = 0
    reason_id: str = ""
    outcome: DecisionOutcome | None = None
    steps: tuple[DecisionTraceStep, ...] = ()
    dictionary_sources: tuple[PrefixDictionarySource, ...] = ()

    def __post_init__(self) -> None:
        if self.outcome is None:
            object.__setattr__(
                self,
                "outcome",
                (
                    DecisionOutcome.CONVERT
                    if self.should_switch
                    else DecisionOutcome.KEEP
                ),
            )
        object.__setattr__(self, "steps", tuple(self.steps))
        object.__setattr__(
            self,
            "dictionary_sources",
            tuple(self.dictionary_sources),
        )


class MidWordDetector:
    """Decides whether an unfinished word is likely typed in a wrong layout."""

    def __init__(
        self,
        prefix_dictionary: PrefixDictionary,
        *,
        min_prefix_len: int = 4,
        min_target_prefix_count: int = 1,
        user_dict=None,
        user_dict_min_weight: int = 2,
    ):
        self.prefix_dictionary = prefix_dictionary
        self.min_prefix_len = min_prefix_len
        self.min_target_prefix_count = min_target_prefix_count
        self.user_dict = user_dict
        self.user_dict_min_weight = max(1, int(user_dict_min_weight))

    def should_switch(
        self,
        prefix: str | None,
        current_lang: str,
    ) -> MidWordDecision:
        if not isinstance(prefix, str):
            return MidWordDecision(
                False,
                "empty or invalid input",
                current_lang,
                reason_id="candidate.invalid",
                outcome=DecisionOutcome.SKIP,
                steps=(
                    self._step(
                        "candidate.invalid",
                        StepState.MATCHED,
                        decisive=True,
                        input_type=type(prefix).__name__,
                    ),
                ),
            )

        typed_prefix = prefix.strip()
        if not typed_prefix:
            return MidWordDecision(
                False,
                "empty input",
                current_lang,
                reason_id="candidate.empty",
                outcome=DecisionOutcome.SKIP,
                steps=(
                    self._step(
                        "candidate.empty",
                        StepState.MATCHED,
                        decisive=True,
                    ),
                ),
            )

        steps: list[DecisionTraceStep] = []

        if typed_prefix != typed_prefix.lower():
            steps.append(
                self._step(
                    "midword.case",
                    StepState.NOT_MATCHED,
                    decisive=True,
                    value=typed_prefix,
                )
            )
            return MidWordDecision(
                False,
                "mixed or uppercase input",
                current_lang,
                typed_prefix=typed_prefix,
                reason_id="midword.case",
                outcome=DecisionOutcome.KEEP,
                steps=tuple(steps),
            )
        steps.append(
            self._step(
                "midword.case",
                StepState.MATCHED,
            )
        )

        if current_lang == "en":
            target_lang = "ru"
            if not self._valid_en_layout_prefix(typed_prefix):
                steps.append(
                    self._step(
                        "midword.characters",
                        StepState.NOT_MATCHED,
                        decisive=True,
                        layout=current_lang,
                    )
                )
                return MidWordDecision(
                    False,
                    "non-prefix input",
                    current_lang,
                    target_lang=target_lang,
                    typed_prefix=typed_prefix,
                    reason_id="midword.characters",
                    outcome=DecisionOutcome.SKIP,
                    steps=tuple(steps),
                )
            converted_prefix = "".join(EN_TO_RU.get(c, c) for c in typed_prefix)
        elif current_lang == "ru":
            target_lang = "en"
            if not self._valid_ru_layout_prefix(typed_prefix):
                steps.append(
                    self._step(
                        "midword.characters",
                        StepState.NOT_MATCHED,
                        decisive=True,
                        layout=current_lang,
                    )
                )
                return MidWordDecision(
                    False,
                    "non-prefix input",
                    current_lang,
                    target_lang=target_lang,
                    typed_prefix=typed_prefix,
                    reason_id="midword.characters",
                    outcome=DecisionOutcome.SKIP,
                    steps=tuple(steps),
                )
            converted_prefix = "".join(RU_TO_EN.get(c, c) for c in typed_prefix)
        else:
            steps.append(
                self._step(
                    "midword.layout",
                    StepState.NOT_MATCHED,
                    decisive=True,
                    layout=current_lang,
                )
            )
            return MidWordDecision(
                False,
                f"unknown layout: {current_lang}",
                current_lang,
                typed_prefix=typed_prefix,
                reason_id="midword.layout",
                outcome=DecisionOutcome.SKIP,
                steps=tuple(steps),
            )

        steps.append(
            self._step(
                "midword.characters",
                StepState.MATCHED,
                source_lang=current_lang,
                target_lang=target_lang,
            )
        )

        user_policy = self._lookup_user_policy(typed_prefix, current_lang)
        if user_policy is None:
            steps.append(
                self._step(
                    "midword.user_dictionary.disabled",
                    StepState.SKIPPED,
                )
            )
        elif user_policy.exact_action == "convert":
            if user_policy.has_keep_descendants:
                steps.append(
                    self._step(
                        "midword.user_dictionary.prefix_reserved",
                        StepState.MATCHED,
                        decisive=True,
                        prefix=typed_prefix,
                        exact_action="convert",
                        weight=user_policy.exact_weight,
                        opposite_descendant=True,
                    )
                )
                return MidWordDecision(
                    False,
                    "user dictionary prefix reserved by longer keep decision",
                    current_lang,
                    target_lang=target_lang,
                    typed_prefix=typed_prefix,
                    converted_prefix=converted_prefix,
                    reason_id="midword.user_dictionary.prefix_reserved",
                    outcome=DecisionOutcome.KEEP,
                    steps=tuple(steps),
                )
            steps.append(
                self._step(
                    "midword.user_dictionary.exact_convert",
                    StepState.MATCHED,
                    decisive=True,
                    prefix=typed_prefix,
                    weight=user_policy.exact_weight,
                    threshold=self.user_dict_min_weight,
                )
            )
            return MidWordDecision(
                True,
                "exact user dictionary convert decision",
                current_lang,
                target_lang=target_lang,
                typed_prefix=typed_prefix,
                converted_prefix=converted_prefix,
                reason_id="midword.user_dictionary.exact_convert",
                outcome=DecisionOutcome.CONVERT,
                steps=tuple(steps),
            )
        elif user_policy.exact_action == "keep":
            steps.append(
                self._step(
                    "midword.user_dictionary.exact_keep",
                    StepState.MATCHED,
                    decisive=True,
                    prefix=typed_prefix,
                    weight=user_policy.exact_weight,
                    threshold=-self.user_dict_min_weight,
                )
            )
            return MidWordDecision(
                False,
                "exact user dictionary keep decision",
                current_lang,
                target_lang=target_lang,
                typed_prefix=typed_prefix,
                converted_prefix=converted_prefix,
                reason_id="midword.user_dictionary.exact_keep",
                outcome=DecisionOutcome.KEEP,
                steps=tuple(steps),
            )
        elif user_policy.has_descendants:
            steps.append(
                self._step(
                    "midword.user_dictionary.prefix_reserved",
                    StepState.MATCHED,
                    decisive=True,
                    prefix=typed_prefix,
                    convert_descendants=user_policy.has_convert_descendants,
                    keep_descendants=user_policy.has_keep_descendants,
                )
            )
            return MidWordDecision(
                False,
                "user dictionary prefix reserved",
                current_lang,
                target_lang=target_lang,
                typed_prefix=typed_prefix,
                converted_prefix=converted_prefix,
                reason_id="midword.user_dictionary.prefix_reserved",
                outcome=DecisionOutcome.KEEP,
                steps=tuple(steps),
            )
        else:
            steps.append(
                self._step(
                    "midword.user_dictionary.no_match",
                    StepState.NOT_MATCHED,
                    prefix=typed_prefix,
                    threshold=self.user_dict_min_weight,
                )
            )

        if len(typed_prefix) < self.min_prefix_len:
            steps.append(
                self._step(
                    "midword.prefix_length",
                    StepState.NOT_MATCHED,
                    decisive=True,
                    length=len(typed_prefix),
                    minimum=self.min_prefix_len,
                )
            )
            return MidWordDecision(
                False,
                "prefix below threshold",
                current_lang,
                target_lang=target_lang,
                typed_prefix=typed_prefix,
                converted_prefix=converted_prefix,
                reason_id="midword.prefix_length",
                outcome=DecisionOutcome.SKIP,
                steps=tuple(steps),
            )
        steps.append(
            self._step(
                "midword.prefix_length",
                StepState.MATCHED,
                length=len(typed_prefix),
                minimum=self.min_prefix_len,
            )
        )

        source_sources = self.prefix_dictionary.sources_for_lang(current_lang)
        target_sources = self.prefix_dictionary.sources_for_lang(target_lang)
        dictionary_sources = source_sources + target_sources
        if not (
            self._has_loaded_source(source_sources)
            and self._has_loaded_source(target_sources)
        ):
            steps.append(
                self._prefix_step(
                    "midword.system_dictionary.unavailable",
                    StepState.UNAVAILABLE,
                    count=0,
                    lang=f"{current_lang}->{target_lang}",
                    prefix=typed_prefix,
                    sources=dictionary_sources,
                    decisive=True,
                )
            )
            return MidWordDecision(
                False,
                "system dictionary pair unavailable",
                current_lang,
                target_lang=target_lang,
                typed_prefix=typed_prefix,
                converted_prefix=converted_prefix,
                reason_id="midword.system_dictionary.unavailable",
                outcome=DecisionOutcome.SKIP,
                steps=tuple(steps),
                dictionary_sources=dictionary_sources,
            )

        source_count = self.prefix_dictionary.prefix_count(current_lang, typed_prefix)
        target_count = self.prefix_dictionary.prefix_count(target_lang, converted_prefix)

        if source_count > 0:
            steps.append(
                self._prefix_step(
                    "midword.source_prefix",
                    StepState.MATCHED,
                    count=source_count,
                    lang=current_lang,
                    prefix=typed_prefix,
                    sources=source_sources,
                    decisive=True,
                )
            )
            return MidWordDecision(
                False,
                "source prefix exists",
                current_lang,
                target_lang=target_lang,
                typed_prefix=typed_prefix,
                converted_prefix=converted_prefix,
                source_prefix_count=source_count,
                target_prefix_count=target_count,
                reason_id="midword.source_prefix",
                outcome=DecisionOutcome.KEEP,
                steps=tuple(steps),
                dictionary_sources=dictionary_sources,
            )
        steps.append(
            self._prefix_step(
                "midword.source_prefix",
                StepState.NOT_MATCHED,
                count=source_count,
                lang=current_lang,
                prefix=typed_prefix,
                sources=source_sources,
            )
        )

        if target_count < self.min_target_prefix_count:
            steps.append(
                self._prefix_step(
                    "midword.target_prefix",
                    StepState.NOT_MATCHED,
                    count=target_count,
                    lang=target_lang,
                    prefix=converted_prefix,
                    sources=target_sources,
                    decisive=True,
                    threshold=self.min_target_prefix_count,
                )
            )
            return MidWordDecision(
                False,
                "target prefix not found",
                current_lang,
                target_lang=target_lang,
                typed_prefix=typed_prefix,
                converted_prefix=converted_prefix,
                source_prefix_count=source_count,
                target_prefix_count=target_count,
                reason_id="midword.target_prefix",
                outcome=DecisionOutcome.KEEP,
                steps=tuple(steps),
                dictionary_sources=dictionary_sources,
            )
        steps.append(
            self._prefix_step(
                "midword.target_prefix",
                StepState.MATCHED,
                count=target_count,
                lang=target_lang,
                prefix=converted_prefix,
                sources=target_sources,
                threshold=self.min_target_prefix_count,
            )
        )

        steps.append(
            self._step(
                "midword.switch",
                StepState.MATCHED,
                decisive=True,
                source_count=source_count,
                target_count=target_count,
            )
        )

        return MidWordDecision(
            True,
            "target prefix found and source prefix absent",
            current_lang,
            target_lang=target_lang,
            typed_prefix=typed_prefix,
            converted_prefix=converted_prefix,
            source_prefix_count=source_count,
            target_prefix_count=target_count,
            reason_id="midword.switch",
            outcome=DecisionOutcome.CONVERT,
            steps=tuple(steps),
            dictionary_sources=dictionary_sources,
        )

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

    @classmethod
    def _prefix_step(
        cls,
        rule_id: str,
        state: StepState,
        *,
        count: int,
        lang: str,
        prefix: str,
        sources: tuple[PrefixDictionarySource, ...],
        decisive: bool = False,
        threshold: int | None = None,
    ) -> DecisionTraceStep:
        facts: dict[str, str | int | bool | None] = {
            "count": count,
            "lang": lang,
            "prefix": prefix,
        }
        if threshold is not None:
            facts["threshold"] = threshold
        facts["dictionary_source_count"] = len(sources)
        for index, source in enumerate(sources):
            stem = f"dictionary_{index}"
            facts[f"{stem}_kind"] = source.kind
            facts[f"{stem}_enabled"] = source.enabled
            facts[f"{stem}_loaded"] = source.loaded
            facts[f"{stem}_word_count"] = source.word_count
            facts[f"{stem}_path"] = source.path
            facts[f"{stem}_explicit"] = source.explicit
        return cls._step(
            rule_id,
            state,
            decisive=decisive,
            **facts,
        )

    def _lookup_user_policy(
        self,
        typed_prefix: str,
        current_lang: str,
    ) -> UserPolicyMatch | None:
        """Return exact and descendant user policy with a legacy fallback."""
        if self.user_dict is None:
            return None

        lookup = getattr(self.user_dict, "lookup_policy", None)
        if callable(lookup):
            try:
                match = lookup(
                    typed_prefix,
                    current_lang,
                    min_weight=self.user_dict_min_weight,
                )
            except (AttributeError, TypeError, ValueError):
                match = None
            if isinstance(match, UserPolicyMatch):
                return match

        try:
            weight = int(
                self.user_dict.get_weight(typed_prefix, current_lang)
            )
        except (AttributeError, TypeError, ValueError):
            weight = 0
        if weight >= self.user_dict_min_weight:
            action = "convert"
        elif weight <= -self.user_dict_min_weight:
            action = "keep"
        else:
            action = None
        return UserPolicyMatch(
            prefix=typed_prefix,
            lang=current_lang,
            exact_action=action,
            exact_weight=weight if action is not None else 0,
        )

    @staticmethod
    def _has_loaded_source(
        sources: tuple[PrefixDictionarySource, ...],
    ) -> bool:
        return any(source.enabled and source.loaded for source in sources)

    @staticmethod
    def _valid_en_layout_prefix(prefix: str) -> bool:
        return all(
            ("a" <= c <= "z") or EN_TO_RU.get(c, "").isalpha()
            for c in prefix
        )

    @staticmethod
    def _valid_ru_layout_prefix(prefix: str) -> bool:
        return all(
            ("а" <= c <= "я") or c == "ё" or RU_TO_EN.get(c, "").isalpha()
            for c in prefix
        )
