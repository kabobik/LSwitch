"""Tests for automatic conversion marker model."""

from __future__ import annotations

from lswitch.core.auto_marker import AutoConversionMarker


def test_space_marker_exposes_typed_fields_and_legacy_keys():
    events = [object(), object()]

    marker = AutoConversionMarker.for_space_conversion(
        original_word="ghbdtn",
        original_lang="en",
        direction="en_to_ru",
        word_events=events,
    )

    assert marker.kind == "space"
    assert marker.original_word == "ghbdtn"
    assert marker.original_lang == "en"
    assert marker.target_lang == "ru"
    assert marker.converted_len == 2
    assert marker["word"] == "ghbdtn"
    assert marker["lang"] == "en"
    assert marker["direction"] == "en_to_ru"
    assert "time" in marker
    assert marker.get("missing", "fallback") == "fallback"


def test_mid_word_marker_has_no_space_and_copies_events():
    events = [object(), object()]

    marker = AutoConversionMarker.for_mid_word_conversion(
        original_word="gh",
        original_lang="en",
        direction="en_to_ru",
        word_events=events,
    )

    assert marker.kind == "mid_word"
    assert marker.original_word == "gh"
    assert marker.original_lang == "en"
    assert marker.target_lang == "ru"
    assert marker.word_events == events
    assert marker.word_events is not events
    assert marker.converted_len == 2
    assert marker.had_space is False


def test_marker_from_legacy_dict_and_mutable_time_alias():
    marker = AutoConversionMarker.from_legacy({
        "word": "gp",
        "lang": "en",
        "direction": "en_to_ru",
        "word_events": [1, 2],
        "converted_len": 2,
        "time": 123.0,
    })

    marker["time"] -= 23.0

    assert marker.original_word == "gp"
    assert marker.original_lang == "en"
    assert marker.target_lang == "ru"
    assert marker.created_at == 100.0
    assert marker.copy()["time"] == 100.0
