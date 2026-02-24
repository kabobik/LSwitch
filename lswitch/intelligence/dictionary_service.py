"""DictionaryService — word lookup for EN and RU."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class DictionaryService:
    """Provides word existence checks for EN and RU.

    Data sets are loaded lazily to keep import time fast.
    """

    def __init__(self):
        self._ru_words: set[str] | None = None
        self._en_words: set[str] | None = None

    def _load_ru(self) -> set[str]:
        if self._ru_words is None:
            try:
                from lswitch.intelligence.ru_words import RUSSIAN_WORDS
                self._ru_words = RUSSIAN_WORDS
            except ImportError:
                self._ru_words = set()
        return self._ru_words

    def _load_en(self) -> set[str]:
        if self._en_words is None:
            try:
                from lswitch.intelligence.en_words import ENGLISH_WORDS
                self._en_words = ENGLISH_WORDS
            except ImportError:
                self._en_words = set()
        return self._en_words

    def in_ru(self, word: str) -> bool:
        return word.lower() in self._load_ru()

    def in_en(self, word: str) -> bool:
        return word.lower() in self._load_en()

    def in_any(self, word: str) -> bool:
        return self.in_ru(word) or self.in_en(word)

    def should_convert(self, word: str, current_layout: str) -> tuple[bool, str]:
        """Determine whether *word* typed in *current_layout* should be converted.

        Decision priorities (from TECHNICAL_SPEC_v2.md §6.2):
          1. Word is already correct for current layout → don't convert.
          2. Converted word exists in target layout's dictionary → convert.
          3. Otherwise → don't convert.

        Args:
            word: the word as typed (e.g. "ghbdtn" or "привет").
            current_layout: layout the word was typed in ("en" or "ru").

        Returns:
            (should_convert: bool, reason: str)
        """
        from lswitch.intelligence.maps import EN_TO_RU, RU_TO_EN

        word_lower = word.lower() if isinstance(word, str) else ""
        if not word_lower:
            return (False, "empty or invalid input")

        if current_layout == "en":
            # Priority 1: already a correct English word → keep it
            if self.in_en(word_lower):
                return (False, "already correct English word")
            # Priority 2: convert EN→RU and check Russian dictionary
            converted = "".join(EN_TO_RU.get(c, c) for c in word_lower)
            if self.in_ru(converted):
                return (True, f"converted to Russian word '{converted}'")
            return (False, "not found in any dictionary")

        elif current_layout == "ru":
            # Priority 1: already a correct Russian word → keep it
            if self.in_ru(word_lower):
                return (False, "already correct Russian word")
            # Priority 2: convert RU→EN and check English dictionary
            converted = "".join(RU_TO_EN.get(c, c) for c in word_lower)
            if self.in_en(converted):
                return (True, f"converted to English word '{converted}'")
            return (False, "not found in any dictionary")

        return (False, f"unknown layout: {current_layout}")
