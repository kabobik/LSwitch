"""Tests for input event routing."""

from __future__ import annotations

from unittest.mock import MagicMock

from lswitch.core.events import Event, EventType, KeyEventData
from lswitch.core.event_manager import KEY_BACKSPACE, KEY_SPACE
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
        on_key_release=MagicMock(),
        on_mouse_click=MagicMock(),
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


def test_input_router_delegates_remaining_input_events():
    on_key_release = MagicMock()
    on_mouse_click = MagicMock()
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
        on_key_release=on_key_release,
        on_mouse_click=on_mouse_click,
        on_mouse_release=on_mouse_release,
    )

    key_release = _event(EventType.KEY_RELEASE)
    mouse_click = _event(EventType.MOUSE_CLICK)
    mouse_release = _event(EventType.MOUSE_RELEASE)

    router.on_key_release(key_release)
    router.on_mouse_click(mouse_click)
    router.on_mouse_release(mouse_release)

    on_key_release.assert_called_once_with(key_release)
    on_mouse_click.assert_called_once_with(mouse_click)
    on_mouse_release.assert_called_once_with(mouse_release)
