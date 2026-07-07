"""Tests for application-level conversion use cases."""

from __future__ import annotations

from unittest.mock import MagicMock

from lswitch.core.auto_marker import AutoConversionMarker
from lswitch.core.conversion_use_cases import (
    KEY_BACKSPACE,
    KEY_SPACE,
    ManualConversionUseCase,
    PostConversionStateUpdater,
    SpaceAutoConversionUseCase,
    UndoAutoConversionUseCase,
)
from lswitch.core.events import KeyEventData
from lswitch.core.learning_service import PendingManualLearning
from lswitch.core.selection_tracker import SelectionFreshnessTracker
from lswitch.core.states import State, StateContext
from lswitch.core.typed_buffer import TypedBufferService
from lswitch.input.key_mapper import keycode_to_char
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


class _Detector:
    def __init__(self, should: bool):
        self.should = should

    def should_convert(self, word: str, current_lang: str):
        return self.should, "test"


def _context_with_events(codes: list[int]) -> StateContext:
    context = StateContext()
    context.state = State.TYPING
    context.event_buffer = [
        KeyEventData(code=code, value=1, device_name="test")
        for code in codes
    ]
    context.chars_in_buffer = len(context.event_buffer)
    return context


def _space_auto_use_case(*, should_convert: bool = True):
    xkb = MagicMock()
    en_layout = LayoutInfo(name="en", index=0, xkb_name="us")
    ru_layout = LayoutInfo(name="ru", index=1, xkb_name="ru")
    xkb.get_current_layout.return_value = en_layout
    xkb.get_layouts.return_value = [en_layout, ru_layout]
    xkb.keycode_to_char.side_effect = lambda code, _layout: keycode_to_char(code)
    retype_service = MagicMock()
    retype_service.retype_events.return_value = True
    learning_service = MagicMock()
    learning_service.user_dict = object()
    use_case = SpaceAutoConversionUseCase(
        auto_detector=_Detector(should_convert),
        typed_buffer=TypedBufferService(),
        xkb=xkb,
        retype_service=retype_service,
        learning_service=learning_service,
        timing={
            "auto_before_replay_delay": 0,
            "auto_before_space_delay": 0,
        },
    )
    return use_case, xkb, retype_service, learning_service


def test_space_auto_conversion_use_case_retypes_word_and_returns_marker():
    use_case, xkb, retype_service, _learning_service = _space_auto_use_case()
    context = _context_with_events([34, 35, 48])
    original_events = list(context.event_buffer)

    result = use_case.execute(
        context=context,
        threshold=0,
        last_auto_marker=None,
        auto_confirm_enabled=False,
    )

    assert result.space_consumed is True
    assert result.pending_space is True
    assert result.marker is not None
    assert result.marker.original_word == "ghb"
    assert result.marker.original_lang == "en"
    assert result.marker.direction == "en_to_ru"
    assert result.marker_changed is True
    retype_service.retype_events.assert_called_once_with(
        original_events,
        delete_count=4,
        target_layout=xkb.get_layouts.return_value[1],
        before_replay_delay=0,
        backspace_n_times_keyword=True,
    )
    assert context.event_buffer == []
    assert context.chars_in_buffer == 0
    assert context.state == State.IDLE


def test_space_auto_conversion_use_case_consumes_previous_marker_without_conversion():
    use_case, _xkb, retype_service, learning_service = _space_auto_use_case(
        should_convert=False
    )
    context = _context_with_events([34, 35, 48])
    marker = AutoConversionMarker.for_space_conversion(
        original_word="old",
        original_lang="en",
        direction="en_to_ru",
        word_events=[],
    )

    result = use_case.execute(
        context=context,
        threshold=0,
        last_auto_marker=marker,
        auto_confirm_enabled=True,
    )

    assert result.space_consumed is False
    assert result.marker is None
    assert result.marker_changed is True
    learning_service.record_auto_confirmation.assert_called_once_with(marker)
    retype_service.retype_events.assert_not_called()
    assert context.event_buffer


def test_space_auto_conversion_use_case_skips_below_threshold():
    use_case, _xkb, retype_service, learning_service = _space_auto_use_case()
    context = _context_with_events([34, 35, 48])

    result = use_case.execute(
        context=context,
        threshold=10,
        last_auto_marker=AutoConversionMarker.for_space_conversion(
            original_word="old",
            original_lang="en",
            direction="en_to_ru",
            word_events=[],
        ),
        auto_confirm_enabled=True,
    )

    assert result.space_consumed is False
    assert result.marker_changed is False
    learning_service.record_auto_confirmation.assert_not_called()
    retype_service.retype_events.assert_not_called()
