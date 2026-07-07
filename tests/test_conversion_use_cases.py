"""Tests for application-level conversion use cases."""

from __future__ import annotations

from unittest.mock import MagicMock

from lswitch.core.auto_marker import AutoConversionMarker
from lswitch.core.conversion_use_cases import (
    KEY_BACKSPACE,
    KEY_SPACE,
    ManualConversionUseCase,
    PostConversionStateUpdater,
    UndoAutoConversionUseCase,
)
from lswitch.core.events import KeyEventData
from lswitch.core.learning_service import PendingManualLearning
from lswitch.core.selection_tracker import SelectionFreshnessTracker
from lswitch.core.states import StateContext
from lswitch.platform.xkb_adapter import LayoutInfo


def test_undo_auto_conversion_replays_original_events_and_records_correction():
    events = [KeyEventData(code=34, value=1, device_name="test")]
    marker = AutoConversionMarker(
        kind="space",
        original_word="ghbdtn",
        original_lang="en",
        target_lang="ru",
        direction="en_to_ru",
        word_events=events,
        converted_len=6,
        had_space=True,
        created_at=123.0,
    )
    virtual_kb = MagicMock()
    xkb = MagicMock()
    en_layout = LayoutInfo(name="en", index=0, xkb_name="us")
    xkb.get_layouts.return_value = [
        en_layout,
        LayoutInfo(name="ru", index=1, xkb_name="ru"),
    ]
    user_dict = MagicMock()
    use_case = UndoAutoConversionUseCase(
        virtual_kb=virtual_kb,
        xkb=xkb,
        user_dict=user_dict,
        timing={"undo_before_replay_delay": 0},
        debug=True,
    )

    ok = use_case.execute(marker)

    assert ok is True
    user_dict.add_correction.assert_called_once_with("ghbdtn", "en", debug=True)
    virtual_kb.tap_key.assert_any_call(KEY_BACKSPACE, n_times=7)
    xkb.switch_layout.assert_called_once_with(target=en_layout)
    virtual_kb.replay_events.assert_called_once_with(events)
    virtual_kb.tap_key.assert_any_call(KEY_SPACE)


def test_undo_auto_conversion_without_space_does_not_readd_space():
    marker = AutoConversionMarker(
        kind="mid_word",
        original_word="ghb",
        original_lang="en",
        target_lang="ru",
        direction="en_to_ru",
        word_events=[],
        converted_len=3,
        had_space=False,
    )
    virtual_kb = MagicMock()
    xkb = MagicMock()
    xkb.get_layouts.return_value = []
    use_case = UndoAutoConversionUseCase(
        virtual_kb=virtual_kb,
        xkb=xkb,
        timing={"undo_before_replay_delay": 0},
    )

    ok = use_case.execute(marker)

    assert ok is True
    virtual_kb.tap_key.assert_called_once_with(KEY_BACKSPACE, n_times=3)
    virtual_kb.replay_events.assert_called_once_with([])


def test_post_conversion_marks_repeat_for_successful_selection_conversion():
    tracker = SelectionFreshnessTracker(valid=True)
    tracker.set_valid(True)
    updater = PostConversionStateUpdater(tracker)

    sticky = updater.update(
        success=True,
        saved_count=0,
        saved_events=[],
        selection_valid_for_convert=True,
    )

    assert sticky == []
    assert tracker.repeat_valid is True
    assert tracker.repeat_generation == tracker.generation


def test_post_conversion_clears_repeat_on_failure():
    tracker = SelectionFreshnessTracker(repeat_valid=True, repeat_generation=1)
    updater = PostConversionStateUpdater(tracker)

    updater.update(
        success=False,
        saved_count=0,
        saved_events=[],
        selection_valid_for_convert=True,
    )

    assert tracker.repeat_valid is False
    assert tracker.repeat_generation == 0


def test_post_conversion_returns_sticky_events_for_successful_retype_only():
    tracker = SelectionFreshnessTracker()
    updater = PostConversionStateUpdater(tracker)
    events = [KeyEventData(code=34, value=1)]

    sticky = updater.update(
        success=True,
        saved_count=1,
        saved_events=events,
        selection_valid_for_convert=False,
    )

    assert sticky == events
    assert sticky is not events

    selection_sticky = updater.update(
        success=True,
        saved_count=0,
        saved_events=[],
        selection_valid_for_convert=True,
    )

    assert selection_sticky == []


def test_manual_conversion_use_case_records_pending_learning_and_sticky_events():
    conversion_engine = MagicMock()
    conversion_engine.convert.return_value = True
    learning_service = MagicMock()
    learning_service.user_dict = object()
    tracker = SelectionFreshnessTracker()
    use_case = ManualConversionUseCase(
        conversion_engine=conversion_engine,
        learning_service=learning_service,
        post_conversion_updater=PostConversionStateUpdater(tracker),
    )
    events = [KeyEventData(code=34, value=1)]
    pending = PendingManualLearning("ghbdtn", "en", False)

    result = use_case.execute(
        context=StateContext(),
        selection_valid_for_convert=False,
        saved_events=events,
        saved_count=1,
        pending_manual_learning=pending,
    )

    assert result.success is True
    assert result.sticky_events == events
    assert result.sticky_events is not events
    conversion_engine.convert.assert_called_once()
    learning_service.record_manual_conversion.assert_called_once_with(
        "ghbdtn",
        "en",
        False,
    )


def test_manual_conversion_use_case_records_selection_learning_from_last_conversion():
    conversion_engine = MagicMock()
    conversion_engine.convert.return_value = True
    conversion_engine.last_conversion = {
        "mode": "selection",
        "original": "ghbdtn",
        "converted": "привет",
        "target_lang": "ru",
    }
    learning_service = MagicMock()
    learning_service.user_dict = object()
    tracker = SelectionFreshnessTracker(valid=True)
    tracker.set_valid(True)
    use_case = ManualConversionUseCase(
        conversion_engine=conversion_engine,
        learning_service=learning_service,
        post_conversion_updater=PostConversionStateUpdater(tracker),
    )

    result = use_case.execute(
        context=StateContext(),
        selection_valid_for_convert=True,
        saved_events=[],
        saved_count=0,
        pending_manual_learning=None,
    )

    assert result.success is True
    assert result.sticky_events == []
    assert tracker.repeat_valid is True
    learning_service.record_selection_conversion.assert_called_once_with(
        conversion_engine.last_conversion
    )


def test_manual_conversion_use_case_failure_skips_learning_and_clears_repeat():
    conversion_engine = MagicMock()
    conversion_engine.convert.return_value = False
    learning_service = MagicMock()
    learning_service.user_dict = object()
    tracker = SelectionFreshnessTracker(repeat_valid=True, repeat_generation=1)
    use_case = ManualConversionUseCase(
        conversion_engine=conversion_engine,
        learning_service=learning_service,
        post_conversion_updater=PostConversionStateUpdater(tracker),
    )

    result = use_case.execute(
        context=StateContext(),
        selection_valid_for_convert=True,
        saved_events=[],
        saved_count=0,
        pending_manual_learning=PendingManualLearning("word", "en", False),
    )

    assert result.success is False
    assert result.sticky_events == []
    assert tracker.repeat_valid is False
    learning_service.record_manual_conversion.assert_not_called()
    learning_service.record_selection_conversion.assert_not_called()
