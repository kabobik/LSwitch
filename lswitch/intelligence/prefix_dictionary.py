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
                    kind="builtin",
                    enabled=True,
                    loaded=True,
                    word_count=len(normalized_en),
                ),
            ),
            "ru": (
                PrefixDictionarySource(
                    lang="ru",
                    kind="builtin",
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
        system_loader=None,
        include_system: bool = False,
    ) -> "PrefixDictionary":
        words_by_lang = {
            "en": dictionary.words_for_lang("en"),
            "ru": dictionary.words_for_lang("ru"),
        }
        sources: dict[str, list[PrefixDictionarySource]] = {
            lang: [
                PrefixDictionarySource(
                    lang=lang,
                    kind="builtin",
                    enabled=True,
                    loaded=True,
                    word_count=len(words),
                )
            ]
            for lang, words in words_by_lang.items()
        }
        if system_loader is not None:
            for lang in ("en", "ru"):
                loaded = system_loader.load(lang) if include_system else None
                if loaded is not None:
                    words_by_lang[lang].update(loaded.words)
                status = cls._system_source_status(
                    system_loader,
                    lang,
                    enabled=include_system,
                    loaded=loaded,
                )
                sources[lang].append(status)
        return cls(
            en_words=words_by_lang["en"],
            ru_words=words_by_lang["ru"],
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
    def _system_source_status(
        system_loader,
        lang: str,
        *,
        enabled: bool,
        loaded,
    ) -> PrefixDictionarySource:
        get_status = getattr(system_loader, "get_status", None)
        status = get_status(lang, enabled=enabled) if callable(get_status) else None
        path = getattr(status, "path", None)
        if path is None and loaded is not None:
            path = getattr(loaded, "path", None)
        word_count = getattr(status, "word_count", None)
        if word_count is None:
            word_count = len(getattr(loaded, "words", ())) if loaded is not None else 0
        loaded_flag = getattr(status, "loaded", None)
        if loaded_flag is None:
            loaded_flag = loaded is not None
        return PrefixDictionarySource(
            lang=lang,
            kind="system",
            enabled=bool(getattr(status, "enabled", enabled)),
            loaded=bool(loaded_flag),
            word_count=int(word_count),
            path=str(path) if path is not None else None,
            explicit=bool(getattr(status, "explicit", False)),
        )
