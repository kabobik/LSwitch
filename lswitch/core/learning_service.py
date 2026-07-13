"""User-dictionary learning side effects."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from lswitch.core.auto_marker import AutoConversionMarker

if TYPE_CHECKING:
    from lswitch.intelligence.user_dictionary import UserDictionary

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PendingManualLearning:
    word: str
    lang: str
    is_selection_conversion: bool = False


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

    def prepare_pending_manual_learning(
        self,
        *,
        chars_in_buffer: int,
        selection_valid: bool,
        has_auto_marker: bool,
        layout_info,
        extract_last_word,
        selection,
        layout_to_lang,
    ) -> PendingManualLearning | None:
        if self.user_dict is None or has_auto_marker:
            return None

        if chars_in_buffer > 0:
            try:
                manual_lang = layout_to_lang(layout_info)
                manual_word, _ = extract_last_word(layout_info)
                if manual_word and manual_lang:
                    return PendingManualLearning(
                        word=manual_word,
                        lang=manual_lang,
                        is_selection_conversion=False,
                    )
            except Exception:
                return None

        if chars_in_buffer == 0 and selection_valid:
            try:
                from lswitch.core.text_converter import detect_language

                sel_obj = selection.get_selection() if selection else None
                if sel_obj and sel_obj.text:
                    sel_text = sel_obj.text.strip()
                    if self.is_single_word_for_learning(sel_text):
                        manual_lang = "en" if detect_language(sel_text) == "en" else "ru"
                        return PendingManualLearning(
                            word=sel_text,
                            lang=manual_lang,
                            is_selection_conversion=True,
                        )
            except Exception as exc:
                logger.debug("Selection word extraction failed: %s", exc)

        return None

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
