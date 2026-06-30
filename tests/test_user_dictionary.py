"""Tests for UserDictionary."""

from __future__ import annotations

import tomllib

import pytest

from lswitch.intelligence.user_dictionary import UserDictionary


@pytest.fixture
def tmp_dict(tmp_path):
    path = str(tmp_path / "user_dict.toml")
    return UserDictionary(path=path)


def test_initial_weight_zero(tmp_dict):
    assert tmp_dict.get_weight("ghbdtn", "en") == 0


def test_correction_adds_keep_weight(tmp_dict):
    tmp_dict.add_correction("ghbdtn", "en")

    assert tmp_dict.get_weight("ghbdtn", "en") == -2
    assert tmp_dict.data["keep"]["en"]["ghbdtn"] == 2


def test_confirmation_adds_convert_weight(tmp_dict):
    tmp_dict.add_confirmation("hello", "en")

    assert tmp_dict.get_weight("hello", "en") == 1
    assert tmp_dict.data["convert"]["en"]["hello"] == 1


def test_persistence(tmp_path):
    path = str(tmp_path / "dict.toml")
    d = UserDictionary(path=path)
    d.add_correction("test", "en")

    saved = (tmp_path / "dict.toml").read_text(encoding="utf-8")
    assert "[keep.en]" in saved
    assert '"test" = 2' in saved

    d2 = UserDictionary(path=path)
    assert d2.get_weight("test", "en") == -2


def test_add_confirmation_weight_step(tmp_dict):
    tmp_dict.add_confirmation("hello", "en", weight_step=2)
    assert tmp_dict.get_weight("hello", "en") == 2
    tmp_dict.add_confirmation("hello", "en", weight_step=3)
    assert tmp_dict.get_weight("hello", "en") == 5
    assert tmp_dict.data["convert"]["en"]["hello"] == 5


def test_convert_and_keep_weights_are_collapsed_to_difference(tmp_dict):
    tmp_dict.add_confirmation("hello", "en", weight_step=3)
    tmp_dict.add_correction("hello", "en", weight_step=2)

    assert tmp_dict.get_weight("hello", "en") == 1
    assert tmp_dict.data["convert"]["en"]["hello"] == 1
    assert "hello" not in tmp_dict.data["keep"]["en"]


def test_opposite_weights_cancel_completely(tmp_dict):
    tmp_dict.add_confirmation("привет", "ru", weight_step=2)
    tmp_dict.add_correction("привет", "ru", weight_step=2)

    assert tmp_dict.get_weight("привет", "ru") == 0
    assert "привет" not in tmp_dict.data["convert"]["ru"]
    assert "привет" not in tmp_dict.data["keep"]["ru"]


def test_larger_opposite_weight_flips_side(tmp_dict):
    tmp_dict.add_confirmation("привет", "ru", weight_step=2)
    tmp_dict.add_correction("привет", "ru", weight_step=4)

    assert tmp_dict.get_weight("привет", "ru") == -2
    assert "привет" not in tmp_dict.data["convert"]["ru"]
    assert tmp_dict.data["keep"]["ru"]["привет"] == 2


def test_loads_toml_structure(tmp_path):
    path = tmp_path / "dict.toml"
    path.write_text(
        """
        [convert.en]
        "ghbdtn" = 2

        [keep.ru]
        "привет" = 3
        """,
        encoding="utf-8",
    )

    d = UserDictionary(path=str(path))

    assert d.get_weight("ghbdtn", "en") == 2
    assert d.get_weight("привет", "ru") == -3


def test_load_collapses_existing_counterweights(tmp_path):
    path = tmp_path / "dict.toml"
    path.write_text(
        """
        [convert.ru]
        "привет" = 2
        "мир" = 5

        [keep.ru]
        "привет" = 2
        "мир" = 3
        """,
        encoding="utf-8",
    )

    d = UserDictionary(path=str(path))

    assert d.get_weight("привет", "ru") == 0
    assert "привет" not in d.data["convert"]["ru"]
    assert "привет" not in d.data["keep"]["ru"]
    assert d.get_weight("мир", "ru") == 2
    assert d.data["convert"]["ru"]["мир"] == 2
    assert "мир" not in d.data["keep"]["ru"]


def test_saved_toml_is_valid(tmp_dict, tmp_path):
    tmp_dict.add_confirmation("ghbdtn", "en", weight_step=2)
    tmp_dict.add_correction("hello", "en", weight_step=2)

    with open(tmp_dict.path, "rb") as f:
        parsed = tomllib.load(f)

    assert parsed["convert"]["en"]["ghbdtn"] == 2
    assert parsed["keep"]["en"]["hello"] == 2


def test_saved_toml_omits_cancelled_counterweights(tmp_dict, tmp_path):
    tmp_dict.add_confirmation("привет", "ru", weight_step=2)
    tmp_dict.add_correction("привет", "ru", weight_step=2)

    saved = (tmp_path / "user_dict.toml").read_text(encoding="utf-8")

    assert '"привет"' not in saved
