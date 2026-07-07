"""User-dictionary learning side effects."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from lswitch.core.auto_marker import AutoConversionMarker

if TYPE_CHECKING:
    from lswitch.intelligence.user_dictionary import UserDictionary

logger = logging.getLogger(__name__)


class LearningService:
    """Centralizes writes to the self-learning user dictionary."""

    def __init__(
        self,
        user_dict: "UserDictionary | None" = None,
        *,
        debug: bool = False,
        manual_weight_step: int = 2,
    ):
        self.user_dict = user_dict
        self.debug = debug
        self.manual_weight_step = manual_weight_step

    def record_auto_undo_correction(self, marker: AutoConversionMarker) -> bool:
        if self.user_dict is None:
            return False
        self.user_dict.add_correction(
            marker.original_word,
            marker.original_lang,
            debug=self.debug,
        )
        logger.info(
            "Correction: '%s' (%s) — keep +2",
            marker.original_word,
            marker.original_lang,
        )
        return True

    def record_auto_confirmation(self, marker: AutoConversionMarker) -> bool:
        if self.user_dict is None:
            return False
        self.user_dict.add_confirmation(
            marker.original_word,
            marker.original_lang,
            debug=self.debug,
        )
        return True

    def record_manual_conversion(
        self,
        manual_word: str,
        manual_lang: str,
        is_selection_conversion: bool,
    ) -> bool:
        if self.user_dict is None:
            return False
        if is_selection_conversion:
            from lswitch.core.text_converter import convert_text

            target_lang = "ru" if manual_lang == "en" else "en"
            converted_word = convert_text(
                manual_word,
                direction=f"{manual_lang}_to_{target_lang}",
            )
            self.user_dict.add_correction(
                converted_word,
                target_lang,
                debug=self.debug,
                weight_step=self.manual_weight_step,
            )
            logger.info(
                "Selection manual conversion: '%s' (%s) -> keeping result '%s' (%s) +%d",
                manual_word,
                manual_lang,
                converted_word,
                target_lang,
                self.manual_weight_step,
            )
            return True

        self.user_dict.add_confirmation(
            manual_word,
            manual_lang,
            debug=self.debug,
            weight_step=self.manual_weight_step,
        )
        logger.info(
            "Manual conversion: '%s' (%s) — convert +%d",
            manual_word,
            manual_lang,
            self.manual_weight_step,
        )
        return True

    def record_selection_conversion(self, conversion: dict | None) -> bool:
        if self.user_dict is None or not isinstance(conversion, dict):
            return False
        if conversion.get("mode") not in {"selection", "selection_expand"}:
            return False

        original = str(conversion.get("original") or "").strip()
        converted = str(conversion.get("converted") or "").strip()
        if not (
            self.is_single_word_for_learning(original)
            and self.is_single_word_for_learning(converted)
        ):
            return False

        target_lang = conversion.get("target_lang")
        if target_lang not in {"en", "ru"}:
            from lswitch.core.text_converter import detect_language

            target_lang = "en" if detect_language(converted) == "en" else "ru"

        self.user_dict.add_correction(
            converted,
            target_lang,
            debug=self.debug,
            weight_step=self.manual_weight_step,
        )
        logger.info(
            "Selection manual conversion: '%s' -> keeping result '%s' (%s) +%d",
            original,
            converted,
            target_lang,
            self.manual_weight_step,
        )
        return True

    @staticmethod
    def is_single_word_for_learning(text: str) -> bool:
        stripped = text.strip()
        return bool(stripped and not any(ch.isspace() for ch in stripped))
