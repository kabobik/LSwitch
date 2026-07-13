"""Tests for input event routing."""

from __future__ import annotations

from unittest.mock import MagicMock

from lswitch.core.decision_trace import (
    DecisionAttempt,
    DecisionOutcome,
    DecisionTraceRecorder,
    ExecutionOutcome,
    TraceLifecycle,
    TraceTrigger,
)
from lswitch.core.events import Event, EventType, KeyEventData
from lswitch.core.event_manager import KEY_BACKSPACE, KEY_ENTER, KEY_SPACE
from lswitch.core.input_router import (
    InputConversionPort,
    InputEventRouter,
    InputSelectionPort,
)
from lswitch.core.selection_tracker import SelectionFreshnessTracker
from lswitch.core.state_manager import StateManager
from lswitch.core.typed_buffer import TypedBufferService
from lswitch.platform.selection_adapter import SelectionInfo

KEY_A = 30
KEY_LEFTSHIFT = 42


def _event(event_type: EventType, code: int = KEY_A) -> Event:
    value = 0 if event_type == EventType.KEY_RELEASE else 1
    return Event(
        type=event_type,
        data=KeyEventData(code=code, value=value, device_name="test"),
        timestamp=0.0,
    )


def _router(
    *,
    auto_conversion_enabled=None,
    try_auto_conversion_at_space=None,
    mid_word_auto_conversion_enabled=None,
    try_mid_word_auto_conversion=None,
    get_pending_auto_space=None,
    set_pending_auto_space=None,
    clear_last_retype_events=None,
    clear_last_auto_marker=None,
    inject_deferred_space=None,
    request_conversion=None,
    close_trace_session=None,
    prime_selection_baseline_on_click=None,
    read_mouse_release_selection=None,
):
    state_manager = StateManager()
    typed_buffer = TypedBufferService()
    selection_tracker = SelectionFreshnessTracker(valid=True, repeat_valid=True)
    router = InputEventRouter(
        state_manager=state_manager,
        typed_buffer=typed_buffer,
        selection_tracker=selection_tracker,
        conversion=InputConversionPort(
            decode_buffer=lambda: typed_buffer.decode(
                state_manager.context.event_buffer
            ),
            auto_conversion_enabled=auto_conversion_enabled or (lambda: False),
            try_auto_conversion_at_space=(
                try_auto_conversion_at_space
                or (lambda correlation_id: False)
            ),
            mid_word_auto_conversion_enabled=(
                mid_word_auto_conversion_enabled or (lambda: False)
            ),
            try_mid_word_auto_conversion=(
                try_mid_word_auto_conversion
                or (lambda correlation_id: False)
            ),
            get_pending_auto_space=get_pending_auto_space or (lambda: False),
            set_pending_auto_space=set_pending_auto_space or (lambda value: None),
            clear_last_retype_events=clear_last_retype_events or (lambda: None),
            clear_last_auto_marker=clear_last_auto_marker or (lambda: None),
            inject_deferred_space=inject_deferred_space or (lambda: None),
            request_conversion=request_conversion or (lambda: None),
            close_trace_session=(
                close_trace_session or (lambda correlation_id: None)
            ),
        ),
        selection=InputSelectionPort(
            prime_baseline_on_click=(
                prime_selection_baseline_on_click or (lambda: None)
            ),
            read_mouse_release_selection=(
                read_mouse_release_selection or (lambda: None)
            ),
        ),
    )
    return router, state_manager, selection_tracker


def test_input_router_handles_regular_key_press():
    clear_last_retype_events = MagicMock()
    router, state_manager, selection_tracker = _router(
        clear_last_retype_events=clear_last_retype_events
    )

    router.on_key_press(_event(EventType.KEY_PRESS))

    assert state_manager.context.chars_in_buffer == 1
    assert state_manager.context.event_buffer[0].code == KEY_A
    assert selection_tracker.valid is False
    assert selection_tracker.repeat_valid is False
    clear_last_retype_events.assert_called_once()


def test_input_router_tries_mid_word_auto_conversion_after_regular_key_release():
    try_mid_word_auto_conversion = MagicMock(return_value=True)
    router, state_manager, selection_tracker = _router(
        mid_word_auto_conversion_enabled=lambda: True,
        try_mid_word_auto_conversion=try_mid_word_auto_conversion,
    )

    router.on_key_press(_event(EventType.KEY_PRESS))

    try_mid_word_auto_conversion.assert_not_called()
    router.on_key_release(_event(EventType.KEY_RELEASE))

    try_mid_word_auto_conversion.assert_called_once_with(1)
    assert state_manager.context.chars_in_buffer == 1
    assert selection_tracker.repeat_valid is False


def test_input_router_waits_until_all_pressed_text_keys_are_released():
    try_mid_word_auto_conversion = MagicMock(return_value=False)
    router, _state_manager, _selection_tracker = _router(
        mid_word_auto_conversion_enabled=lambda: True,
        try_mid_word_auto_conversion=try_mid_word_auto_conversion,
    )
    key_b = 48

    router.on_key_press(_event(EventType.KEY_PRESS, KEY_A))
    router.on_key_press(_event(EventType.KEY_PRESS, key_b))
    router.on_key_release(_event(EventType.KEY_RELEASE, KEY_A))

    try_mid_word_auto_conversion.assert_not_called()

    router.on_key_release(_event(EventType.KEY_RELEASE, key_b))

    try_mid_word_auto_conversion.assert_called_once_with(1)


def test_input_router_reuses_word_session_for_prefix_attempts():
    try_mid_word_auto_conversion = MagicMock(return_value=False)
    router, _state_manager, _selection_tracker = _router(
        mid_word_auto_conversion_enabled=lambda: True,
        try_mid_word_auto_conversion=try_mid_word_auto_conversion,
    )
    key_b = 48

    router.on_key_press(_event(EventType.KEY_PRESS, KEY_A))
    router.on_key_release(_event(EventType.KEY_RELEASE, KEY_A))
    router.on_key_press(_event(EventType.KEY_PRESS, key_b))
    router.on_key_release(_event(EventType.KEY_RELEASE, key_b))

    assert [call.args[0] for call in try_mid_word_auto_conversion.call_args_list] == [
        1,
        1,
    ]
    assert router.active_word_session_id == 1


def test_space_flow_uses_and_closes_current_word_session():
    try_auto_conversion_at_space = MagicMock(return_value=False)
    close_trace_session = MagicMock()
    router, _state_manager, _selection_tracker = _router(
        auto_conversion_enabled=lambda: True,
        try_auto_conversion_at_space=try_auto_conversion_at_space,
        close_trace_session=close_trace_session,
    )

    router.on_key_press(_event(EventType.KEY_PRESS, KEY_A))
    router.on_key_press(_event(EventType.KEY_PRESS, KEY_SPACE))

    try_auto_conversion_at_space.assert_called_once_with(1)
    close_trace_session.assert_called_once_with(1)
    assert router.active_word_session_id is None


def test_next_word_gets_a_new_session_after_space_boundary():
    try_mid_word_auto_conversion = MagicMock(return_value=False)
    router, _state_manager, _selection_tracker = _router(
        mid_word_auto_conversion_enabled=lambda: True,
        try_mid_word_auto_conversion=try_mid_word_auto_conversion,
    )

    router.on_key_press(_event(EventType.KEY_PRESS, KEY_A))
    router.on_key_release(_event(EventType.KEY_RELEASE, KEY_A))
    router.on_key_press(_event(EventType.KEY_PRESS, KEY_SPACE))
    router.on_key_press(_event(EventType.KEY_PRESS, KEY_A))
    router.on_key_release(_event(EventType.KEY_RELEASE, KEY_A))

    assert [call.args[0] for call in try_mid_word_auto_conversion.call_args_list] == [
        1,
        2,
    ]


def test_successful_mid_word_switch_finalizes_segment_but_keeps_word_session():
    try_mid_word_auto_conversion = MagicMock(return_value=True)
    close_trace_session = MagicMock()
    router, _state_manager, _selection_tracker = _router(
        mid_word_auto_conversion_enabled=lambda: True,
        try_mid_word_auto_conversion=try_mid_word_auto_conversion,
        close_trace_session=close_trace_session,
    )

    router.on_key_press(_event(EventType.KEY_PRESS, KEY_A))
    router.on_key_release(_event(EventType.KEY_RELEASE, KEY_A))

    close_trace_session.assert_called_once_with(1)
    assert router.active_word_session_id == 1


def test_text_after_mid_word_switch_keeps_correlation_until_space():
    try_mid_word_auto_conversion = MagicMock(side_effect=[True, False])
    close_trace_session = MagicMock()
    router, _state_manager, _selection_tracker = _router(
        mid_word_auto_conversion_enabled=lambda: True,
        try_mid_word_auto_conversion=try_mid_word_auto_conversion,
        close_trace_session=close_trace_session,
    )
    key_b = 48

    router.on_key_press(_event(EventType.KEY_PRESS, KEY_A))
    router.on_key_release(_event(EventType.KEY_RELEASE, KEY_A))
    router.on_key_press(_event(EventType.KEY_PRESS, key_b))
    router.on_key_release(_event(EventType.KEY_RELEASE, key_b))

    assert [call.args[0] for call in try_mid_word_auto_conversion.call_args_list] == [
        1,
        1,
    ]

    router.on_key_press(_event(EventType.KEY_PRESS, KEY_SPACE))

    assert close_trace_session.call_args_list[-1].args == (1,)
    assert router.active_word_session_id is None


def test_mid_word_conversion_tail_and_boundary_trace_lifecycle():
    recorder = DecisionTraceRecorder(enabled=True)
    attempts = iter(
        (
            DecisionAttempt(
                candidate="рудд",
                converted_candidate="hell",
                outcome=DecisionOutcome.CONVERT,
            ),
            DecisionAttempt(candidate="o", outcome=DecisionOutcome.KEEP),
            DecisionAttempt(candidate="n", outcome=DecisionOutcome.KEEP),
        )
    )
    call_number = 0

    def try_mid_word(correlation_id):
        nonlocal call_number
        call_number += 1
        attempt = next(attempts)
        recorder.upsert_attempt(
            correlation_id,
            TraceTrigger.MID_WORD,
            attempt,
        )
        if call_number == 1:
            recorder.finalize_session(
                correlation_id,
                TraceTrigger.MID_WORD,
                execution=ExecutionOutcome.SUCCEEDED,
            )
            return True
        return False

    router, _state_manager, _selection_tracker = _router(
        mid_word_auto_conversion_enabled=lambda: True,
        try_mid_word_auto_conversion=try_mid_word,
        close_trace_session=recorder.close_session,
    )
    key_b = 48

    router.on_key_press(_event(EventType.KEY_PRESS, KEY_A))
    router.on_key_release(_event(EventType.KEY_RELEASE, KEY_A))
    router.on_key_press(_event(EventType.KEY_PRESS, key_b))
    router.on_key_release(_event(EventType.KEY_RELEASE, key_b))

    converted, tail = recorder.snapshot()
    assert converted.correlation_id == tail.correlation_id == 1
    assert converted.lifecycle is TraceLifecycle.FINALIZED
    assert tail.lifecycle is TraceLifecycle.ACTIVE

    router.on_key_press(_event(EventType.KEY_PRESS, KEY_SPACE))

    assert recorder.snapshot()[1].lifecycle is TraceLifecycle.FINALIZED

    router.on_key_press(_event(EventType.KEY_PRESS, KEY_A))
    router.on_key_release(_event(EventType.KEY_RELEASE, KEY_A))

    next_word = recorder.snapshot()[2]
    assert next_word.correlation_id == 2
    assert next_word.lifecycle is TraceLifecycle.ACTIVE


def test_input_router_cancels_deferred_mid_word_check_at_space_boundary():
    try_mid_word_auto_conversion = MagicMock(return_value=False)
    router, _state_manager, _selection_tracker = _router(
        mid_word_auto_conversion_enabled=lambda: True,
        try_mid_word_auto_conversion=try_mid_word_auto_conversion,
    )
    space = Event(
        type=EventType.KEY_PRESS,
        data=KeyEventData(code=KEY_SPACE, value=1, device_name="test"),
        timestamp=0.0,
    )

    router.on_key_press(_event(EventType.KEY_PRESS))
    router.on_key_press(space)
    router.on_key_release(_event(EventType.KEY_RELEASE))

    try_mid_word_auto_conversion.assert_not_called()


def test_input_router_cancels_deferred_mid_word_check_after_key_repeat():
    try_mid_word_auto_conversion = MagicMock(return_value=False)
    router, _state_manager, _selection_tracker = _router(
        mid_word_auto_conversion_enabled=lambda: True,
        try_mid_word_auto_conversion=try_mid_word_auto_conversion,
    )
    repeat = Event(
        type=EventType.KEY_REPEAT,
        data=KeyEventData(code=KEY_A, value=2, device_name="test"),
        timestamp=0.0,
    )

    router.on_key_press(_event(EventType.KEY_PRESS))
    router.on_key_repeat(repeat)
    router.on_key_release(_event(EventType.KEY_RELEASE))

    try_mid_word_auto_conversion.assert_not_called()


def test_input_router_handles_backspace_press():
    router, state_manager, selection_tracker = _router()
    router.on_key_press(_event(EventType.KEY_PRESS))
    state_manager.context.backspace_repeats = 2
    backspace = Event(
        type=EventType.KEY_PRESS,
        data=KeyEventData(code=KEY_BACKSPACE, value=1, device_name="test"),
        timestamp=0.0,
    )

    router.on_key_press(backspace)

    assert state_manager.context.event_buffer == []
    assert state_manager.context.backspace_repeats == 0
    assert selection_tracker.valid is False
    assert selection_tracker.repeat_valid is False


def test_input_router_consumes_space_on_auto_conversion():
    try_auto_conversion_at_space = MagicMock(return_value=True)
    router, state_manager, selection_tracker = _router(
        auto_conversion_enabled=lambda: True,
        try_auto_conversion_at_space=try_auto_conversion_at_space,
    )
    space = Event(
        type=EventType.KEY_PRESS,
        data=KeyEventData(code=KEY_SPACE, value=1, device_name="test"),
        timestamp=0.0,
    )

    router.on_key_press(space)

    try_auto_conversion_at_space.assert_called_once_with(0)
    assert state_manager.context.event_buffer == []
    assert selection_tracker.repeat_valid is False


def test_input_router_does_not_try_mid_word_auto_conversion_after_space_fallback():
    try_mid_word_auto_conversion = MagicMock(return_value=False)
    router, state_manager, _selection_tracker = _router(
        auto_conversion_enabled=lambda: False,
        mid_word_auto_conversion_enabled=lambda: True,
        try_mid_word_auto_conversion=try_mid_word_auto_conversion,
    )
    space = Event(
        type=EventType.KEY_PRESS,
        data=KeyEventData(code=KEY_SPACE, value=1, device_name="test"),
        timestamp=0.0,
    )

    router.on_key_press(space)

    try_mid_word_auto_conversion.assert_not_called()
    assert state_manager.context.event_buffer[0].code == KEY_SPACE


def test_input_router_cancels_pending_auto_space_on_rollover():
    set_pending_auto_space = MagicMock()
    router, _state_manager, _selection_tracker = _router(
        get_pending_auto_space=lambda: True,
        set_pending_auto_space=set_pending_auto_space,
    )

    router.on_key_press(_event(EventType.KEY_PRESS))

    set_pending_auto_space.assert_called_once_with(False)


def test_input_router_keeps_selection_valid_on_shift_press():
    router, _state_manager, selection_tracker = _router()
    shift = Event(
        type=EventType.KEY_PRESS,
        data=KeyEventData(code=KEY_LEFTSHIFT, value=1, device_name="test"),
        timestamp=0.0,
    )

    router.on_key_press(shift)

    assert selection_tracker.valid is True


def test_input_router_handles_backspace_repeat_and_hold():
    router, state_manager, _selection_tracker = _router()
    router.on_key_press(_event(EventType.KEY_PRESS))
    hold = MagicMock()
    state_manager.on_backspace_hold = hold
    repeat = Event(
        type=EventType.KEY_REPEAT,
        data=KeyEventData(code=KEY_BACKSPACE, value=2, device_name="test"),
        timestamp=0.0,
    )

    router.on_key_repeat(repeat)
    router.on_key_repeat(repeat)
    hold.assert_not_called()
    router.on_key_repeat(repeat)

    assert state_manager.context.backspace_repeats == 3
    assert state_manager.context.event_buffer == []
    hold.assert_called_once()


def test_input_router_injects_deferred_space_on_space_release():
    set_pending_auto_space = MagicMock()
    inject_deferred_space = MagicMock()
    router, _state_manager, _selection_tracker = _router(
        get_pending_auto_space=lambda: True,
        set_pending_auto_space=set_pending_auto_space,
        inject_deferred_space=inject_deferred_space,
    )
    space = Event(
        type=EventType.KEY_RELEASE,
        data=KeyEventData(code=KEY_SPACE, value=0, device_name="test"),
        timestamp=0.0,
    )

    router.on_key_release(space)

    set_pending_auto_space.assert_called_once_with(False)
    inject_deferred_space.assert_called_once()


def test_input_router_requests_conversion_on_double_shift_release():
    request_conversion = MagicMock()
    router, state_manager, _selection_tracker = _router(
        request_conversion=request_conversion
    )
    state_manager.on_shift_up = MagicMock(return_value=True)
    shift = Event(
        type=EventType.KEY_RELEASE,
        data=KeyEventData(code=KEY_LEFTSHIFT, value=0, device_name="test"),
        timestamp=0.0,
    )

    router.on_key_release(shift)

    request_conversion.assert_called_once()


def test_input_router_resets_state_on_navigation_release():
    clear_last_auto_marker = MagicMock()
    clear_last_retype_events = MagicMock()
    router, state_manager, selection_tracker = _router(
        clear_last_auto_marker=clear_last_auto_marker,
        clear_last_retype_events=clear_last_retype_events,
    )
    state_manager.on_navigation = MagicMock()
    enter = Event(
        type=EventType.KEY_RELEASE,
        data=KeyEventData(code=KEY_ENTER, value=0, device_name="test"),
        timestamp=0.0,
    )

    router.on_key_release(enter)

    clear_last_auto_marker.assert_called_once()
    clear_last_retype_events.assert_called_once()
    assert selection_tracker.valid is False
    assert selection_tracker.repeat_valid is False
    state_manager.on_navigation.assert_called_once()


def test_input_router_handles_backspace_release():
    router, state_manager, _selection_tracker = _router()
    state_manager.context.chars_in_buffer = 3
    state_manager.context.backspace_repeats = 5
    backspace = Event(
        type=EventType.KEY_RELEASE,
        data=KeyEventData(code=KEY_BACKSPACE, value=0, device_name="test"),
        timestamp=0.0,
    )

    router.on_key_release(backspace)

    assert state_manager.context.chars_in_buffer == 2
    assert state_manager.context.backspace_repeats == 0


def test_input_router_handles_mouse_click():
    clear_last_auto_marker = MagicMock()
    clear_last_retype_events = MagicMock()
    prime_selection_baseline_on_click = MagicMock()
    router, state_manager, selection_tracker = _router(
        clear_last_auto_marker=clear_last_auto_marker,
        clear_last_retype_events=clear_last_retype_events,
        prime_selection_baseline_on_click=prime_selection_baseline_on_click,
    )
    state_manager.on_mouse_click = MagicMock()
    mouse_click = _event(EventType.MOUSE_CLICK)

    router.on_mouse_click(mouse_click)

    clear_last_auto_marker.assert_called_once()
    clear_last_retype_events.assert_called_once()
    prime_selection_baseline_on_click.assert_called_once()
    assert selection_tracker.valid is False
    assert selection_tracker.repeat_valid is False
    state_manager.on_mouse_click.assert_called_once()


def test_input_router_ignores_mouse_release_without_selection_info():
    router, _state_manager, selection_tracker = _router(
        read_mouse_release_selection=lambda: None
    )
    mouse_release = _event(EventType.MOUSE_RELEASE)

    router.on_mouse_release(mouse_release)

    assert selection_tracker.valid is True


def test_input_router_initializes_mouse_release_selection_baseline():
    router, _state_manager, selection_tracker = _router(
        read_mouse_release_selection=lambda: SelectionInfo(
            text="word",
            owner_id=42,
            timestamp=0.0,
        )
    )
    selection_tracker.baseline_initialized = False
    selection_tracker.set_valid(False)

    router.on_mouse_release(_event(EventType.MOUSE_RELEASE))

    assert selection_tracker.prev_text == "word"
    assert selection_tracker.prev_owner_id == 42
    assert selection_tracker.valid is False


def test_input_router_marks_fresh_mouse_release_selection():
    router, _state_manager, selection_tracker = _router(
        read_mouse_release_selection=lambda: SelectionInfo(
            text="new",
            owner_id=2,
            timestamp=0.0,
        )
    )
    selection_tracker.update_baseline("old", 1)

    router.on_mouse_release(_event(EventType.MOUSE_RELEASE))

    assert selection_tracker.valid is True
    assert selection_tracker.prev_text == "new"
    assert selection_tracker.prev_owner_id == 2
