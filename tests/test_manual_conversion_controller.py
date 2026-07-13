"""Tests for manual conversion orchestration controller."""

from __future__ import annotations

from unittest.mock import MagicMock

from lswitch.core.auto_marker import AutoConversionMarker
from lswitch.core.events import KeyEventData
from lswitch.core.learning_service import LearningService
from lswitch.core.manual_conversion_controller import ManualConversionController
from lswitch.core.selection_tracker import SelectionFreshnessTracker
from lswitch.core.state_manager import StateManager
from lswitch.core.states import State
from lswitch.core.typed_buffer import TypedBufferService
from lswitch.platform.xkb_adapter import LayoutInfo


def _controller(
    *,
    state_manager=None,
    selection_tracker=None,
    typed_buffer=None,
    learning_service=None,
    conversion_engine=None,
    virtual_kb=None,
    xkb=None,
    update_selection_baseline=None,
):
    state_manager = state_manager or StateManager()
    selection_tracker = selection_tracker or SelectionFreshnessTracker()
    typed_buffer = typed_buffer or TypedBufferService()
    learning_service = learning_service or LearningService(None)
    conversion_engine = conversion_engine or MagicMock()
    virtual_kb = virtual_kb or MagicMock()
    xkb = xkb or MagicMock()
    xkb.get_current_layout.return_value = LayoutInfo("en", 0, "us")
    xkb.get_layouts.return_value = [
        LayoutInfo("en", 0, "us"),
        LayoutInfo("ru", 1, "ru"),
    ]
    xkb.keycode_to_char.side_effect = lambda code, _layout: {
        34: "g",
        35: "h",
    }.get(code, "")
    typed_buffer_decode = typed_buffer.decode
    return ManualConversionController(
        state_manager=state_manager,
        selection_tracker=selection_tracker,
        typed_buffer=typed_buffer,
        learning_service=learning_service,
        conversion_engine=conversion_engine,
        virtual_kb=virtual_kb,
        xkb=xkb,
        selection=None,
        timing={"undo_before_replay_delay": 0},
        debug=True,
        decode_events=typed_buffer_decode,
        extract_last_word=lambda _layout: (
            "gh",
            list(state_manager.context.event_buffer),
        ),
        update_selection_baseline=update_selection_baseline or (lambda: None),
    )


def test_manual_conversion_controller_ignores_non_converting_state():
    marker = object()
    sticky_events = [KeyEventData(code=34, value=1)]
    conversion_engine = MagicMock()
    controller = _controller(conversion_engine=conversion_engine)

    result = controller.execute(
        last_auto_marker=marker,
        sticky_events=sticky_events,
    )

    assert result.last_auto_marker is marker
    assert result.sticky_events is sticky_events
    conversion_engine.convert.assert_not_called()


def test_manual_conversion_controller_runs_retype_conversion_and_finalizes():
    state_manager = StateManager()
    state_manager.context.state = State.CONVERTING
    state_manager.context.event_buffer = [
        KeyEventData(code=34, value=1, device_name="test"),
        KeyEventData(code=35, value=1, device_name="test"),
    ]
    state_manager.context.chars_in_buffer = 2
    selection_tracker = SelectionFreshnessTracker()
    conversion_engine = MagicMock()
    conversion_engine.convert.return_value = True
    update_selection_baseline = MagicMock()
    controller = _controller(
        state_manager=state_manager,
        selection_tracker=selection_tracker,
        conversion_engine=conversion_engine,
        update_selection_baseline=update_selection_baseline,
    )

    result = controller.execute(last_auto_marker=None, sticky_events=[])

    assert result.last_auto_marker is None
    assert [event.code for event in result.sticky_events] == [34, 35]
    conversion_engine.convert.assert_called_once()
    update_selection_baseline.assert_called_once()
    assert selection_tracker.valid is False
    assert state_manager.state == State.IDLE


def test_manual_conversion_controller_undoes_recent_auto_without_baseline_update():
    state_manager = StateManager()
    state_manager.context.state = State.CONVERTING
    marker = AutoConversionMarker(
        kind="space",
        original_word="gh",
        original_lang="en",
        target_lang="ru",
        direction="en_to_ru",
        word_events=[KeyEventData(code=34, value=1, device_name="test")],
        converted_len=2,
        had_space=True,
    )
    virtual_kb = MagicMock()
    update_selection_baseline = MagicMock()
    controller = _controller(
        state_manager=state_manager,
        virtual_kb=virtual_kb,
        update_selection_baseline=update_selection_baseline,
    )

    result = controller.execute(last_auto_marker=marker, sticky_events=[])

    assert result.last_auto_marker is None
    virtual_kb.tap_key.assert_any_call(14, n_times=3)
    virtual_kb.tap_key.assert_any_call(57)
    update_selection_baseline.assert_not_called()
    assert state_manager.state == State.IDLE
