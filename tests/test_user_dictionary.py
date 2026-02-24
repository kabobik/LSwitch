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
    assert tmp_dict.get_weight("ghbdtn", "en") == -1


def test_confirmation_increments_weight(tmp_dict):
    tmp_dict.add_confirmation("hello", "en")
    assert tmp_dict.get_weight("hello", "en") == 1


def test_persistence(tmp_path):
    path = str(tmp_path / "dict.json")
    d = UserDictionary(path=path)
    d.add_correction("test", "en")

    d2 = UserDictionary(path=path)
    assert d2.get_weight("test", "en") == -1
