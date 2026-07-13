"""Tests for optional Hunspell/MySpell dictionary loading."""

from __future__ import annotations

import pytest

from lswitch.intelligence.system_dictionary_loader import SystemDictionaryLoader


def test_system_dictionary_loader_reads_hunspell_dic_words(tmp_path):
    path = tmp_path / "ru_RU.dic"
    path.write_text(
        "\n".join(
            [
                "5",
                "привет/AB",
                "пример",
                "hello",
                "при-вет",
                "# comment",
            ]
        ),
        encoding="utf-8",
    )
    loader = SystemDictionaryLoader(min_word_len=3)

    words = loader.load_words("ru", path)

    assert words == {"привет", "пример"}


def test_system_dictionary_loader_reads_english_words(tmp_path):
    path = tmp_path / "en_US.dic"
    path.write_text("3\nhello/AB\nhelp\nпривет\n", encoding="utf-8")
    loader = SystemDictionaryLoader(min_word_len=3)

    words = loader.load_words("en", path)

    assert words == {"hello", "help"}


def test_system_dictionary_loader_finds_best_candidate(tmp_path):
    (tmp_path / "en_AU.dic").write_text("1\ncolour\n", encoding="utf-8")
    expected = tmp_path / "en_US.dic"
    expected.write_text("1\ncolor\n", encoding="utf-8")
    loader = SystemDictionaryLoader(dictionary_dirs=[tmp_path])

    assert loader.find_dictionary("en") == expected


def test_system_dictionary_loader_uses_explicit_path(tmp_path):
    dictionary_path = tmp_path / "custom.dic"
    dictionary_path.write_text("1\nпривет\n", encoding="utf-8")
    loader = SystemDictionaryLoader(explicit_paths={"ru": dictionary_path})

    loaded = loader.load("ru")

    assert loaded is not None
    assert loaded.path == dictionary_path
    assert loaded.words == {"привет"}
    status = loader.get_status("ru")
    assert status.loaded is True
    assert status.enabled is True
    assert status.explicit is True
    assert status.path == dictionary_path
    assert status.word_count == 1


def test_system_dictionary_loader_returns_none_when_missing(tmp_path):
    loader = SystemDictionaryLoader(dictionary_dirs=[tmp_path])

    assert loader.find_dictionary("ru") is None
    assert loader.load("ru") is None
    status = loader.get_status("ru")
    assert status.enabled is True
    assert status.loaded is False
    assert status.path is None
    assert status.word_count == 0


def test_system_dictionary_loader_reports_auto_discovered_status(tmp_path):
    dictionary_path = tmp_path / "en_US.dic"
    dictionary_path.write_text("2\nhello\nworld\n", encoding="utf-8")
    loader = SystemDictionaryLoader(dictionary_dirs=[tmp_path])

    loader.load("en")

    status = loader.get_status("en")
    assert status.loaded is True
    assert status.explicit is False
    assert status.path == dictionary_path
    assert status.word_count == 2


def test_system_dictionary_loader_reports_disabled_without_loading(tmp_path):
    loader = SystemDictionaryLoader(dictionary_dirs=[tmp_path])

    status = loader.get_status("en", enabled=False)

    assert status.enabled is False
    assert status.loaded is False
    assert status.path is None


def test_system_dictionary_loader_builds_one_immutable_snapshot(tmp_path):
    en_path = tmp_path / "en_US.dic"
    ru_path = tmp_path / "ru_RU.dic"
    en_path.write_text("2\nhello\nworld\n", encoding="utf-8")
    ru_path.write_text("2\nпривет\nпример\n", encoding="utf-8")
    loader = SystemDictionaryLoader(dictionary_dirs=[tmp_path])

    snapshot = loader.load_snapshot()

    assert snapshot.en_words == frozenset({"hello", "world"})
    assert snapshot.ru_words == frozenset({"привет", "пример"})
    assert snapshot.available("en") is True
    assert snapshot.available("ru") is True
    assert snapshot.status_for_lang("en").path == en_path
    assert snapshot.status_for_lang("ru").path == ru_path


def test_disabled_snapshot_does_not_read_dictionary_files(monkeypatch):
    loader = SystemDictionaryLoader()
    loaded_langs = []
    monkeypatch.setattr(loader, "load", loaded_langs.append)

    snapshot = loader.load_snapshot(enabled=False)

    assert loaded_langs == []
    assert snapshot.en_words == frozenset()
    assert snapshot.ru_words == frozenset()
    assert all(not status.enabled for status in snapshot.statuses)


def test_system_dictionary_loader_rejects_missing_explicit_path(tmp_path):
    missing = tmp_path / "missing.dic"
    loader = SystemDictionaryLoader(explicit_paths={"en": missing})

    with pytest.raises(ValueError, match="EN dictionary does not exist"):
        loader.validate_explicit_paths()


def test_system_dictionary_loader_rejects_explicit_directory(tmp_path):
    loader = SystemDictionaryLoader(explicit_paths={"ru": tmp_path})

    with pytest.raises(ValueError, match="RU dictionary is not a regular file"):
        loader.find_dictionary("ru")


def test_system_dictionary_loader_supports_cp1251_files(tmp_path):
    dictionary_path = tmp_path / "ru_RU.dic"
    dictionary_path.write_bytes("1\nпривет\n".encode("cp1251"))
    loader = SystemDictionaryLoader()

    assert loader.load_words("ru", dictionary_path) == {"привет"}
