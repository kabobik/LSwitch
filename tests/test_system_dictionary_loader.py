"""Tests for optional Hunspell/MySpell dictionary loading."""

from __future__ import annotations

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


def test_system_dictionary_loader_returns_none_when_missing(tmp_path):
    loader = SystemDictionaryLoader(dictionary_dirs=[tmp_path])

    assert loader.find_dictionary("ru") is None
    assert loader.load("ru") is None


def test_system_dictionary_loader_supports_cp1251_files(tmp_path):
    dictionary_path = tmp_path / "ru_RU.dic"
    dictionary_path.write_bytes("1\nпривет\n".encode("cp1251"))
    loader = SystemDictionaryLoader()

    assert loader.load_words("ru", dictionary_path) == {"привет"}
