"""DictionaryService — word lookup for EN and RU."""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DictionaryDecision:
    """Structured full-word dictionary evidence."""

    should_convert: bool
    reason_id: str
    reason: str
    word: str
    current_lang: str
    target_lang: str | None = None
    converted_word: str | None = None
    source_match: bool | None = None
    target_match: bool | None = None
    source_available: bool | None = None
    target_available: bool | None = None


class DictionaryService:
    """Provides word existence checks for EN and RU.

    Data sets are loaded lazily to keep import time fast.
    """

    def __init__(self):
        self._ru_words: set[str] | None = None
        self._en_words: set[str] | None = None
        self._ru_available: bool | None = None
        self._en_available: bool | None = None

    def _load_ru(self) -> set[str]:
        if self._ru_words is None:
            try:
                from lswitch.intelligence.ru_words import RUSSIAN_WORDS
                self._ru_words = RUSSIAN_WORDS
                self._ru_available = True
            except ImportError:
                self._ru_words = set()
                self._ru_available = False
        return self._ru_words

    def _load_en(self) -> set[str]:
        if self._en_words is None:
            try:
                from lswitch.intelligence.en_words import ENGLISH_WORDS
                self._en_words = ENGLISH_WORDS
                self._en_available = True
            except ImportError:
                self._en_words = set()
                self._en_available = False
        return self._en_words

    def in_ru(self, word: str) -> bool:
        return word.lower() in self._load_ru()

    def in_en(self, word: str) -> bool:
        return word.lower() in self._load_en()

    def in_any(self, word: str) -> bool:
        return self.in_ru(word) or self.in_en(word)

    def words_for_lang(self, lang: str) -> set[str]:
        if lang == "en":
            return set(self._load_en())
        if lang == "ru":
            return set(self._load_ru())
        return set()

    def evaluate(self, word: str, current_layout: str) -> DictionaryDecision:
        """Return structured full-word dictionary evidence."""
        from lswitch.intelligence.maps import EN_TO_RU, RU_TO_EN

        word_lower = word.lower() if isinstance(word, str) else ""
        if not word_lower:
            return DictionaryDecision(
                should_convert=False,
                reason_id="dictionary.candidate.invalid",
                reason="empty or invalid input",
                word=word_lower,
                current_lang=current_layout,
            )

        if current_layout == "en":
            source_words = self._load_en()
            source_available = bool(self._en_available)
            if word_lower in source_words:
                return DictionaryDecision(
                    should_convert=False,
                    reason_id="dictionary.source.match",
                    reason="already correct English word",
                    word=word_lower,
                    current_lang="en",
                    target_lang="ru",
                    source_match=True,
                    source_available=source_available,
                )

            converted = "".join(EN_TO_RU.get(c, c) for c in word_lower)
            target_words = self._load_ru()
            target_available = bool(self._ru_available)
            if converted in target_words:
                return DictionaryDecision(
                    should_convert=True,
                    reason_id="dictionary.target.match",
                    reason=f"converted to Russian word '{converted}'",
                    word=word_lower,
                    current_lang="en",
                    target_lang="ru",
                    converted_word=converted,
                    source_match=False,
                    target_match=True,
                    source_available=source_available,
                    target_available=target_available,
                )
            return DictionaryDecision(
                should_convert=False,
                reason_id="dictionary.no_match",
                reason="not found in any dictionary",
                word=word_lower,
                current_lang="en",
                target_lang="ru",
                converted_word=converted,
                source_match=False,
                target_match=False,
                source_available=source_available,
                target_available=target_available,
            )

        if current_layout == "ru":
            source_words = self._load_ru()
            source_available = bool(self._ru_available)
            if word_lower in source_words:
                return DictionaryDecision(
                    should_convert=False,
                    reason_id="dictionary.source.match",
                    reason="already correct Russian word",
                    word=word_lower,
                    current_lang="ru",
                    target_lang="en",
                    source_match=True,
                    source_available=source_available,
                )

            converted = "".join(RU_TO_EN.get(c, c) for c in word_lower)
            target_words = self._load_en()
            target_available = bool(self._en_available)
            if converted in target_words:
                return DictionaryDecision(
                    should_convert=True,
                    reason_id="dictionary.target.match",
                    reason=f"converted to English word '{converted}'",
                    word=word_lower,
                    current_lang="ru",
                    target_lang="en",
                    converted_word=converted,
                    source_match=False,
                    target_match=True,
                    source_available=source_available,
                    target_available=target_available,
                )
            return DictionaryDecision(
                should_convert=False,
                reason_id="dictionary.no_match",
                reason="not found in any dictionary",
                word=word_lower,
                current_lang="ru",
                target_lang="en",
                converted_word=converted,
                source_match=False,
                target_match=False,
                source_available=source_available,
                target_available=target_available,
            )

        return DictionaryDecision(
            should_convert=False,
            reason_id="dictionary.layout.unknown",
            reason=f"unknown layout: {current_layout}",
            word=word_lower,
            current_lang=current_layout,
        )

    def should_convert(self, word: str, current_layout: str) -> tuple[bool, str]:
        """Compatibility wrapper around evaluate()."""
        decision = self.evaluate(word, current_layout)
        return decision.should_convert, decision.reason
