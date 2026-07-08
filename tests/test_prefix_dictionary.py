"""Tests for mid-word prefix dictionary."""

from __future__ import annotations

from lswitch.intelligence.dictionary_service import DictionaryService
from lswitch.intelligence.prefix_dictionary import PrefixDictionary


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


def test_prefix_dictionary_from_dictionary_service_uses_builtin_words():
    service = DictionaryService()
    dictionary = PrefixDictionary.from_dictionary_service(service)

    assert dictionary.in_lang("en", "hello") is True
    assert dictionary.in_lang("ru", "привет") is True
    assert dictionary.has_prefix("en", "hell") is True
    assert dictionary.has_prefix("ru", "прив") is True


def test_dictionary_service_exposes_word_sets_by_language():
    service = DictionaryService()

    assert "hello" in service.words_for_lang("en")
    assert "привет" in service.words_for_lang("ru")
    assert service.words_for_lang("unknown") == set()
