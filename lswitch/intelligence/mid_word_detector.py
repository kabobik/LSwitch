"""Mid-word layout detector based on prefix dictionary evidence."""

from __future__ import annotations

from dataclasses import dataclass

from lswitch.intelligence.maps import EN_TO_RU, RU_TO_EN
from lswitch.intelligence.prefix_dictionary import PrefixDictionary


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


class MidWordDetector:
    """Decides whether an unfinished word is likely typed in a wrong layout."""

    def __init__(
        self,
        prefix_dictionary: PrefixDictionary,
        *,
        min_prefix_len: int = 4,
        min_target_prefix_count: int = 1,
    ):
        self.prefix_dictionary = prefix_dictionary
        self.min_prefix_len = min_prefix_len
        self.min_target_prefix_count = min_target_prefix_count

    def should_switch(
        self,
        prefix: str | None,
        current_lang: str,
    ) -> MidWordDecision:
        if not isinstance(prefix, str):
            return MidWordDecision(False, "empty or invalid input", current_lang)

        typed_prefix = prefix.strip()
        if not typed_prefix:
            return MidWordDecision(False, "empty input", current_lang)

        if len(typed_prefix) < self.min_prefix_len:
            return MidWordDecision(
                False,
                "prefix below threshold",
                current_lang,
                typed_prefix=typed_prefix,
            )

        if typed_prefix != typed_prefix.lower():
            return MidWordDecision(
                False,
                "mixed or uppercase input",
                current_lang,
                typed_prefix=typed_prefix,
            )

        if current_lang == "en":
            target_lang = "ru"
            if not self._valid_en_layout_prefix(typed_prefix):
                return MidWordDecision(
                    False,
                    "non-prefix input",
                    current_lang,
                    target_lang=target_lang,
                    typed_prefix=typed_prefix,
                )
            converted_prefix = "".join(EN_TO_RU.get(c, c) for c in typed_prefix)
        elif current_lang == "ru":
            target_lang = "en"
            if not self._valid_ru_layout_prefix(typed_prefix):
                return MidWordDecision(
                    False,
                    "non-prefix input",
                    current_lang,
                    target_lang=target_lang,
                    typed_prefix=typed_prefix,
                )
            converted_prefix = "".join(RU_TO_EN.get(c, c) for c in typed_prefix)
        else:
            return MidWordDecision(False, f"unknown layout: {current_lang}", current_lang)

        source_count = self.prefix_dictionary.prefix_count(current_lang, typed_prefix)
        target_count = self.prefix_dictionary.prefix_count(target_lang, converted_prefix)

        if source_count > 0:
            return MidWordDecision(
                False,
                "source prefix exists",
                current_lang,
                target_lang=target_lang,
                typed_prefix=typed_prefix,
                converted_prefix=converted_prefix,
                source_prefix_count=source_count,
                target_prefix_count=target_count,
            )

        if target_count < self.min_target_prefix_count:
            return MidWordDecision(
                False,
                "target prefix not found",
                current_lang,
                target_lang=target_lang,
                typed_prefix=typed_prefix,
                converted_prefix=converted_prefix,
                source_prefix_count=source_count,
                target_prefix_count=target_count,
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
        )

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
