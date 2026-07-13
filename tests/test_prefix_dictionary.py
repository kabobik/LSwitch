"""Tests for mid-word prefix dictionary."""

from __future__ import annotations

from pathlib import Path

from lswitch.intelligence.dictionary_service import DictionaryService
from lswitch.intelligence.prefix_dictionary import PrefixDictionary
from lswitch.intelligence.system_dictionary_loader import (
    SystemDictionaryStatus,
    SystemLexiconSnapshot,
)


def test_prefix_dictionary_counts_prefixes_per_language():
    dictionary = PrefixDictionary(
        en_words={"hello", "help", "world"},
        ru_words={"привет", "пример"},
    )

    assert dictionary.in_lang("en", "HELLO") is True
    assert dictionary.in_lang("ru", "hello") is False
    assert dictionary.has_prefix("en", "hel") is True
    assert dictionary.prefix_count("en", "hel") == 2
    assert dictionary.prefix_count("ru", "при") == 2
    assert dictionary.prefix_count("ru", "прив") == 1
    assert dictionary.prefix_count("en", "missing") == 0


def test_prefix_dictionary_respects_min_prefix_len():
    dictionary = PrefixDictionary(en_words={"hello"}, min_prefix_len=3)

    assert dictionary.has_prefix("en", "he") is False
    assert dictionary.has_prefix("en", "hel") is True


def test_prefix_dictionary_from_dictionary_service_uses_injected_words():
    service = DictionaryService(
        en_words={"hello"},
        ru_words={"привет"},
    )
    dictionary = PrefixDictionary.from_dictionary_service(service)

    assert dictionary.in_lang("en", "hello") is True
    assert dictionary.in_lang("ru", "привет") is True
    assert dictionary.has_prefix("en", "hell") is True
    assert dictionary.has_prefix("ru", "прив") is True


def test_prefix_dictionary_uses_one_system_snapshot():
    snapshot = SystemLexiconSnapshot(
        en_words=frozenset({"customword"}),
        ru_words=frozenset({"кастомный"}),
        statuses=(
            SystemDictionaryStatus(
                lang="en",
                enabled=True,
                path=Path("/dictionaries/en.dic"),
                word_count=1,
            ),
            SystemDictionaryStatus(
                lang="ru",
                enabled=True,
                path=Path("/dictionaries/ru.dic"),
                word_count=1,
            ),
        ),
    )
    dictionary = PrefixDictionary.from_system_snapshot(snapshot)

    assert dictionary.in_lang("en", "customword") is True
    assert dictionary.has_prefix("ru", "каст") is True
    en_sources = dictionary.sources_for_lang("en")
    assert [source.kind for source in en_sources] == ["system"]
    assert en_sources[0].enabled is True
    assert en_sources[0].loaded is True
    assert en_sources[0].word_count == 1


def test_dictionary_service_exposes_word_sets_by_language():
    service = DictionaryService(
        en_words={"hello"},
        ru_words={"привет"},
    )

    assert "hello" in service.words_for_lang("en")
    assert "привет" in service.words_for_lang("ru")
    assert service.words_for_lang("unknown") == set()
