"""DictionaryService — word lookup for EN and RU."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lswitch.intelligence.system_dictionary_loader import (
        SystemDictionaryStatus,
        SystemLexiconSnapshot,
    )

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
    """Provides lookup over one injected immutable system lexicon snapshot."""

    def __init__(
        self,
        *,
        en_words=None,
        ru_words=None,
        availability: dict[str, bool] | None = None,
        statuses: tuple["SystemDictionaryStatus", ...] = (),
    ):
        self._en_words = frozenset(self._normalize_words(en_words or ()))
        self._ru_words = frozenset(self._normalize_words(ru_words or ()))
        available = availability or {}
        self._en_available = bool(
            available.get("en", en_words is not None)
        )
        self._ru_available = bool(
            available.get("ru", ru_words is not None)
        )
        self._statuses = tuple(statuses)

    @classmethod
    def from_system_snapshot(
        cls,
        snapshot: "SystemLexiconSnapshot",
    ) -> "DictionaryService":
        return cls(
            en_words=snapshot.en_words,
            ru_words=snapshot.ru_words,
            availability={
                "en": snapshot.available("en"),
                "ru": snapshot.available("ru"),
            },
            statuses=snapshot.statuses,
        )

    def in_ru(self, word: str) -> bool:
        return word.lower() in self._ru_words

    def in_en(self, word: str) -> bool:
        return word.lower() in self._en_words

    def in_any(self, word: str) -> bool:
        return self.in_ru(word) or self.in_en(word)

    def words_for_lang(self, lang: str) -> set[str]:
        if lang == "en":
            return set(self._en_words)
        if lang == "ru":
            return set(self._ru_words)
        return set()

    def is_available(self, lang: str) -> bool:
        if lang == "en":
            return self._en_available
        if lang == "ru":
            return self._ru_available
        return False

    def status_for_lang(self, lang: str):
        return next(
            (status for status in self._statuses if status.lang == lang),
            None,
        )

    def evaluate_source(
        self,
        word: str,
        current_layout: str,
    ) -> DictionaryDecision:
        """Check only exact source membership for the boundary veto."""
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
            source_words = self._en_words
            source_available = self._en_available
            target_lang = "ru"
            language_name = "English"
        elif current_layout == "ru":
            source_words = self._ru_words
            source_available = self._ru_available
            target_lang = "en"
            language_name = "Russian"
        else:
            return DictionaryDecision(
                should_convert=False,
                reason_id="dictionary.layout.unknown",
                reason=f"unknown layout: {current_layout}",
                word=word_lower,
                current_lang=current_layout,
            )

        source_match = word_lower in source_words
        return DictionaryDecision(
            should_convert=False,
            reason_id=(
                "dictionary.source.match"
                if source_match
                else "dictionary.source.no_match"
            ),
            reason=(
                f"already correct {language_name} word"
                if source_match
                else "not found in source dictionary"
            ),
            word=word_lower,
            current_lang=current_layout,
            target_lang=target_lang,
            source_match=source_match,
            source_available=bool(source_available),
        )

    def evaluate(self, word: str, current_layout: str) -> DictionaryDecision:
        """Return legacy source/target evidence for compatibility callers."""
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
            source_words = self._en_words
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
            target_words = self._ru_words
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
            source_words = self._ru_words
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
            target_words = self._en_words
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

    @staticmethod
    def _normalize_words(words) -> set[str]:
        return {
            word.strip().lower()
            for word in words
            if isinstance(word, str) and word.strip()
        }
