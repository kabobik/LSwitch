"""Tests for text_converter (pure functions)."""

from __future__ import annotations

from lswitch.core.text_converter import convert_text, detect_language


def test_en_to_ru():
    assert convert_text("ghbdtn") == "привет"


def test_ru_to_en():
    assert convert_text("привет") == "ghbdtn"


def test_preserves_case():
    assert convert_text("Ghbdtn") == "Привет"


def test_detect_en():
    assert detect_language("hello") == "en"


def test_detect_ru():
    assert detect_language("привет") == "ru"


def test_unknown_chars_pass_through():
    assert convert_text("123") == "123"
