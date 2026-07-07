"""Tests for user-dictionary learning side effects."""

from __future__ import annotations

from unittest.mock import MagicMock

from lswitch.core.auto_marker import AutoConversionMarker
from lswitch.core.learning_service import LearningService


def test_record_auto_undo_correction():
    user_dict = MagicMock()
    marker = AutoConversionMarker(
        kind="space",
        original_word="ghbdtn",
        original_lang="en",
        target_lang="ru",
        direction="en_to_ru",
    )
    service = LearningService(user_dict, debug=True)

    ok = service.record_auto_undo_correction(marker)

    assert ok is True
    user_dict.add_correction.assert_called_once_with("ghbdtn", "en", debug=True)


def test_record_auto_confirmation():
    user_dict = MagicMock()
    marker = AutoConversionMarker(
        kind="space",
        original_word="ghbdtn",
        original_lang="en",
        target_lang="ru",
        direction="en_to_ru",
    )
    service = LearningService(user_dict, debug=False)

    ok = service.record_auto_confirmation(marker)

    assert ok is True
    user_dict.add_confirmation.assert_called_once_with("ghbdtn", "en", debug=False)


def test_record_manual_retype_conversion():
    user_dict = MagicMock()
    service = LearningService(user_dict, debug=True, manual_weight_step=2)

    ok = service.record_manual_conversion("ghbdtn", "en", False)

    assert ok is True
    user_dict.add_confirmation.assert_called_once_with(
        "ghbdtn",
        "en",
        debug=True,
        weight_step=2,
    )


def test_record_manual_selection_conversion_keeps_result_word():
    user_dict = MagicMock()
    service = LearningService(user_dict, debug=True, manual_weight_step=2)

    ok = service.record_manual_conversion("ghbdtn", "en", True)

    assert ok is True
    user_dict.add_correction.assert_called_once_with(
        "привет",
        "ru",
        debug=True,
        weight_step=2,
    )


def test_record_selection_conversion_uses_last_conversion_payload():
    user_dict = MagicMock()
    service = LearningService(user_dict, debug=True, manual_weight_step=2)

    ok = service.record_selection_conversion({
        "mode": "selection",
        "original": "ghbdtn",
        "converted": "привет",
        "target_lang": "ru",
    })

    assert ok is True
    user_dict.add_correction.assert_called_once_with(
        "привет",
        "ru",
        debug=True,
        weight_step=2,
    )


def test_record_selection_conversion_ignores_multi_word_text():
    user_dict = MagicMock()
    service = LearningService(user_dict)

    ok = service.record_selection_conversion({
        "mode": "selection",
        "original": "two words",
        "converted": "два слова",
        "target_lang": "ru",
    })

    assert ok is False
    user_dict.add_correction.assert_not_called()


def test_no_user_dictionary_returns_false_without_writes():
    service = LearningService(None)
    marker = AutoConversionMarker(
        kind="space",
        original_word="ghbdtn",
        original_lang="en",
        target_lang="ru",
        direction="en_to_ru",
    )

    assert service.record_auto_undo_correction(marker) is False
    assert service.record_auto_confirmation(marker) is False
    assert service.record_manual_conversion("ghbdtn", "en", False) is False
    assert service.record_selection_conversion({"mode": "selection"}) is False


def test_prepare_pending_manual_learning_from_typed_buffer():
    user_dict = MagicMock()
    service = LearningService(user_dict)

    pending = service.prepare_pending_manual_learning(
        chars_in_buffer=3,
        selection_valid=False,
        has_auto_marker=False,
        layout_info=object(),
        extract_last_word=lambda layout: ("ghb", []),
        selection=None,
        layout_to_lang=lambda layout: "en",
    )

    assert pending is not None
    assert pending.word == "ghb"
    assert pending.lang == "en"
    assert pending.is_selection_conversion is False


def test_prepare_pending_manual_learning_from_selection():
    user_dict = MagicMock()
    service = LearningService(user_dict)
    selection = MagicMock()
    selection.get_selection.return_value = MagicMock(text="ghbdtn")

    pending = service.prepare_pending_manual_learning(
        chars_in_buffer=0,
        selection_valid=True,
        has_auto_marker=False,
        layout_info=None,
        extract_last_word=lambda layout: ("", []),
        selection=selection,
        layout_to_lang=lambda layout: "en",
    )

    assert pending is not None
    assert pending.word == "ghbdtn"
    assert pending.lang == "en"
    assert pending.is_selection_conversion is True


def test_prepare_pending_manual_learning_ignores_auto_marker_and_multiword_selection():
    user_dict = MagicMock()
    service = LearningService(user_dict)
    selection = MagicMock()
    selection.get_selection.return_value = MagicMock(text="two words")

    assert service.prepare_pending_manual_learning(
        chars_in_buffer=3,
        selection_valid=False,
        has_auto_marker=True,
        layout_info=object(),
        extract_last_word=lambda layout: ("ghb", []),
        selection=None,
        layout_to_lang=lambda layout: "en",
    ) is None

    assert service.prepare_pending_manual_learning(
        chars_in_buffer=0,
        selection_valid=True,
        has_auto_marker=False,
        layout_info=None,
        extract_last_word=lambda layout: ("", []),
        selection=selection,
        layout_to_lang=lambda layout: "en",
    ) is None
