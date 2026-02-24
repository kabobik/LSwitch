"""Tests for atomic JSON persistence."""

from __future__ import annotations

import os

from lswitch.intelligence.persistence import load_json, save_json


def test_save_and_load(tmp_path):
    path = str(tmp_path / "data.json")
    data = {"key": "value", "num": 42}
    save_json(path, data)
    loaded = load_json(path)
    assert loaded == data


def test_load_missing_returns_default(tmp_path):
    path = str(tmp_path / "missing.json")
    assert load_json(path) == {}
    assert load_json(path, {"x": 1}) == {"x": 1}


def test_save_is_atomic(tmp_path):
    path = str(tmp_path / "atomic.json")
    save_json(path, {"v": 1})
    save_json(path, {"v": 2})
    assert load_json(path) == {"v": 2}

    # No leftover .tmp files
    tmp_files = [f for f in os.listdir(tmp_path) if f.endswith(".tmp")]
    assert tmp_files == []
