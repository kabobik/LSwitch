"""PrefixDictionary - word and prefix lookup for mid-word detection."""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class PrefixDictionarySource:
    """Lightweight metadata for a word source included in the prefix index."""

    lang: str
    kind: str
    enabled: bool
    loaded: bool
    word_count: int = 0
    path: str | None = None
    explicit: bool = False


class PrefixDictionary:
    """Provides full-word and prefix lookup over compact sorted word indexes."""

    def __init__(
        self,
        *,
        en_words: Iterable[str] | None = None,
        ru_words: Iterable[str] | None = None,
        min_prefix_len: int = 1,
        sources: dict[str, Iterable[PrefixDictionarySource]] | None = None,
    ):
        self.min_prefix_len = max(1, min_prefix_len)
        normalized_en = tuple(sorted(self._normalize_words(en_words or ())))
        normalized_ru = tuple(sorted(self._normalize_words(ru_words or ())))
        self._words = {
            "en": normalized_en,
            "ru": normalized_ru,
        }
        default_sources = {
            "en": (
                PrefixDictionarySource(
                    lang="en",
                    kind="memory",
                    enabled=True,
                    loaded=True,
                    word_count=len(normalized_en),
                ),
            ),
            "ru": (
                PrefixDictionarySource(
                    lang="ru",
                    kind="memory",
                    enabled=True,
                    loaded=True,
                    word_count=len(normalized_ru),
                ),
            ),
        }
        self._sources = {
            lang: tuple((sources or default_sources).get(lang, ()))
            for lang in ("en", "ru")
        }

    @classmethod
    def from_dictionary_service(
        cls,
        dictionary,
        *,
        min_prefix_len: int = 1,
    ) -> "PrefixDictionary":
        words_by_lang = {
            "en": dictionary.words_for_lang("en"),
            "ru": dictionary.words_for_lang("ru"),
        }
        sources: dict[str, tuple[PrefixDictionarySource, ...]] = {
            lang: (
                PrefixDictionarySource(
                    lang=lang,
                    kind="memory",
                    enabled=cls._dictionary_available(dictionary, lang),
                    loaded=cls._dictionary_available(dictionary, lang),
                    word_count=len(words),
                ),
            )
            for lang, words in words_by_lang.items()
        }
        return cls(
            en_words=words_by_lang["en"],
            ru_words=words_by_lang["ru"],
            min_prefix_len=min_prefix_len,
            sources=sources,
        )

    @classmethod
    def from_system_snapshot(
        cls,
        snapshot,
        *,
        min_prefix_len: int = 1,
    ) -> "PrefixDictionary":
        sources: dict[str, tuple[PrefixDictionarySource, ...]] = {}
        for lang in ("en", "ru"):
            status = snapshot.status_for_lang(lang)
            sources[lang] = (
                PrefixDictionarySource(
                    lang=lang,
                    kind="system",
                    enabled=bool(getattr(status, "enabled", False)),
                    loaded=bool(getattr(status, "loaded", False)),
                    word_count=int(getattr(status, "word_count", 0)),
                    path=(
                        str(status.path)
                        if getattr(status, "path", None) is not None
                        else None
                    ),
                    explicit=bool(getattr(status, "explicit", False)),
                ),
            )
        return cls(
            en_words=snapshot.en_words,
            ru_words=snapshot.ru_words,
            min_prefix_len=min_prefix_len,
            sources=sources,
        )

    def in_lang(self, lang: str, word: str | None) -> bool:
        normalized = self._normalize_token(word)
        if not normalized:
            return False
        words = self._words.get(lang, ())
        index = bisect_left(words, normalized)
        return index < len(words) and words[index] == normalized

    def has_prefix(self, lang: str, prefix: str | None) -> bool:
        return self.prefix_count(lang, prefix) > 0

    def prefix_count(self, lang: str, prefix: str | None) -> int:
        normalized = self._normalize_token(prefix)
        if not normalized or len(normalized) < self.min_prefix_len:
            return 0
        words = self._words.get(lang, ())
        start = bisect_left(words, normalized)
        end = bisect_left(words, normalized + "\U0010ffff")
        return end - start

    def sources_for_lang(self, lang: str) -> tuple[PrefixDictionarySource, ...]:
        """Return immutable metadata for sources used by one language index."""
        return self._sources.get(lang, ())

    @staticmethod
    def _normalize_token(token: str | None) -> str:
        if not isinstance(token, str):
            return ""
        return token.strip().lower()

    def _normalize_words(self, words: Iterable[str]) -> set[str]:
        normalized = {
            word.strip().lower()
            for word in words
            if isinstance(word, str) and word.strip()
        }
        return normalized

    @staticmethod
    def _dictionary_available(dictionary, lang: str) -> bool:
        is_available = getattr(dictionary, "is_available", None)
        return bool(is_available(lang)) if callable(is_available) else True
