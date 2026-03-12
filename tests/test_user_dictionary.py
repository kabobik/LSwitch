"""Tests for UserDictionary."""

from __future__ import annotations

import os
import tempfile

import pytest

from lswitch.intelligence.user_dictionary import UserDictionary


@pytest.fixture
def tmp_dict(tmp_path):
    path = str(tmp_path / "user_dict.json")
    return UserDictionary(path=path)


def test_initial_weight_zero(tmp_dict):
    assert tmp_dict.get_weight("ghbdtn", "en") == 0


def test_correction_decrements_weight(tmp_dict):
    tmp_dict.add_correction("ghbdtn", "en")
    assert tmp_dict.get_weight("ghbdtn", "en") == -2


def test_confirmation_increments_weight(tmp_dict):
    tmp_dict.add_confirmation("hello", "en")
    assert tmp_dict.get_weight("hello", "en") == 1


def test_persistence(tmp_path):
    path = str(tmp_path / "dict.json")
    d = UserDictionary(path=path)
    d.add_correction("test", "en")

    d2 = UserDictionary(path=path)
    assert d2.get_weight("test", "en") == -2


def test_add_confirmation_weight_step(tmp_dict):
    tmp_dict.add_confirmation("hello", "en", weight_step=2)
    assert tmp_dict.get_weight("hello", "en") == 2
    tmp_dict.add_confirmation("hello", "en", weight_step=3)
    assert tmp_dict.get_weight("hello", "en") == 5

def _test_migration_from_old_format(tmp_path):
    import json
    path = str(tmp_path / "dict.json")
    old_data = {
        "words": {
            "en:ghbdtn": {"weight": -2},
            "ru:будут": {"weight": 1}
        },
        "settings": {"min_weight": 2}
    }
    with open(path, "w") as f:
        json.dump(old_data, f)
    
    d = UserDictionary(path=path)
    assert d.get_weight("ghbdtn", "en") == -2
    assert d.get_weight("будут", "ru") == 1
    
    # Verify the structure has been flattened
    with open(path, "r") as f:
        new_data = json.load(f)
    assert new_data["words"]["en:ghbdtn"] == -2
    assert "weight" not in str(new_data["words"]["en:ghbdtn"])

