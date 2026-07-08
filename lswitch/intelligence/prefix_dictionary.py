"""PrefixDictionary - word and prefix lookup for mid-word detection."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable


class PrefixDictionary:
    """Stores full-word and prefix indexes per language."""

    def __init__(
        self,
        *,
        en_words: Iterable[str] | None = None,
        ru_words: Iterable[str] | None = None,
        min_prefix_len: int = 1,
    ):
        self.min_prefix_len = max(1, min_prefix_len)
        self._words = {
            "en": self._normalize_words(en_words or ()),
            "ru": self._normalize_words(ru_words or ()),
        }
        self._prefix_counts = {
            lang: self._build_prefix_counts(words)
            for lang, words in self._words.items()
        }

    @classmethod
    def from_dictionary_service(
        cls,
        dictionary,
        *,
        min_prefix_len: int = 1,
        system_loader=None,
        include_system: bool = False,
    ) -> "PrefixDictionary":
        en_words = dictionary.words_for_lang("en")
        ru_words = dictionary.words_for_lang("ru")
        if include_system and system_loader is not None:
            en_words = cls._merge_system_words(en_words, system_loader, "en")
            ru_words = cls._merge_system_words(ru_words, system_loader, "ru")
        return cls(
            en_words=en_words,
            ru_words=ru_words,
            min_prefix_len=min_prefix_len,
        )

    def in_lang(self, lang: str, word: str | None) -> bool:
        normalized = self._normalize_token(word)
        if not normalized:
            return False
        return normalized in self._words.get(lang, set())

    def has_prefix(self, lang: str, prefix: str | None) -> bool:
        return self.prefix_count(lang, prefix) > 0

    def prefix_count(self, lang: str, prefix: str | None) -> int:
        normalized = self._normalize_token(prefix)
        if not normalized or len(normalized) < self.min_prefix_len:
            return 0
        return self._prefix_counts.get(lang, Counter()).get(normalized, 0)

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

    def _build_prefix_counts(self, words: set[str]) -> Counter:
        counts: Counter[str] = Counter()
        for word in words:
            for end in range(self.min_prefix_len, len(word) + 1):
                counts[word[:end]] += 1
        return counts

    @staticmethod
    def _merge_system_words(words: set[str], system_loader, lang: str) -> set[str]:
        merged = set(words)
        loaded = system_loader.load(lang)
        if loaded is not None:
            merged.update(loaded.words)
        return merged
