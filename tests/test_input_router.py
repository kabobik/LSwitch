"""Tests for input event routing."""

from __future__ import annotations

from unittest.mock import MagicMock

from lswitch.core.events import Event, EventType, KeyEventData
from lswitch.core.event_manager import KEY_BACKSPACE, KEY_ENTER, KEY_SPACE
from lswitch.core.input_router import InputEventRouter
from lswitch.core.selection_tracker import SelectionFreshnessTracker
from lswitch.core.state_manager import StateManager
from lswitch.core.typed_buffer import TypedBufferService

KEY_A = 30
KEY_LEFTSHIFT = 42


def _event(event_type: EventType) -> Event:
    return Event(
        type=event_type,
        data=KeyEventData(code=30, value=1, device_name="test"),
        timestamp=0.0,
    )


def _router(
    *,
    auto_conversion_enabled=None,
    try_auto_conversion_at_space=None,
    get_pending_auto_space=None,
    set_pending_auto_space=None,
    clear_last_retype_events=None,
    clear_last_auto_marker=None,
    inject_deferred_space=None,
    request_conversion=None,
    prime_selection_baseline_on_click=None,
):
    state_manager = StateManager()
    typed_buffer = TypedBufferService()
    selection_tracker = SelectionFreshnessTracker(valid=True, repeat_valid=True)
    router = InputEventRouter(
        state_manager=state_manager,
        typed_buffer=typed_buffer,
        selection_tracker=selection_tracker,
        decode_buffer=lambda: typed_buffer.decode(state_manager.context.event_buffer),
        auto_conversion_enabled=auto_conversion_enabled or (lambda: False),
        try_auto_conversion_at_space=try_auto_conversion_at_space or (lambda: False),
        get_pending_auto_space=get_pending_auto_space or (lambda: False),
        set_pending_auto_space=set_pending_auto_space or (lambda value: None),
        clear_last_retype_events=clear_last_retype_events or (lambda: None),
        clear_last_auto_marker=clear_last_auto_marker or (lambda: None),
        inject_deferred_space=inject_deferred_space or (lambda: None),
        request_conversion=request_conversion or (lambda: None),
        prime_selection_baseline_on_click=(
            prime_selection_baseline_on_click or (lambda: None)
        ),
        on_mouse_release=MagicMock(),
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

    try_auto_conversion_at_space.assert_called_once()
    assert state_manager.context.event_buffer == []
    assert selection_tracker.repeat_valid is False


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


def test_input_router_delegates_remaining_input_events():
    on_mouse_release = MagicMock()
    router = InputEventRouter(
        state_manager=StateManager(),
        typed_buffer=TypedBufferService(),
        selection_tracker=SelectionFreshnessTracker(),
        decode_buffer=lambda: "",
        auto_conversion_enabled=lambda: False,
        try_auto_conversion_at_space=lambda: False,
        get_pending_auto_space=lambda: False,
        set_pending_auto_space=lambda value: None,
        clear_last_retype_events=lambda: None,
        clear_last_auto_marker=lambda: None,
        inject_deferred_space=lambda: None,
        request_conversion=lambda: None,
        prime_selection_baseline_on_click=lambda: None,
        on_mouse_release=on_mouse_release,
    )

    mouse_release = _event(EventType.MOUSE_RELEASE)

    router.on_mouse_release(mouse_release)

    on_mouse_release.assert_called_once_with(mouse_release)
