"""Tests for input event routing."""

from __future__ import annotations

from unittest.mock import MagicMock

from lswitch.core.events import Event, EventType, KeyEventData
from lswitch.core.input_router import InputEventRouter


def _event(event_type: EventType) -> Event:
    return Event(
        type=event_type,
        data=KeyEventData(code=30, value=1, device_name="test"),
        timestamp=0.0,
    )


def test_input_router_delegates_input_events():
    on_key_press = MagicMock()
    on_key_release = MagicMock()
    on_key_repeat = MagicMock()
    on_mouse_click = MagicMock()
    on_mouse_release = MagicMock()
    router = InputEventRouter(
        on_key_press=on_key_press,
        on_key_release=on_key_release,
        on_key_repeat=on_key_repeat,
        on_mouse_click=on_mouse_click,
        on_mouse_release=on_mouse_release,
    )

    key_press = _event(EventType.KEY_PRESS)
    key_release = _event(EventType.KEY_RELEASE)
    key_repeat = _event(EventType.KEY_REPEAT)
    mouse_click = _event(EventType.MOUSE_CLICK)
    mouse_release = _event(EventType.MOUSE_RELEASE)

    router.on_key_press(key_press)
    router.on_key_release(key_release)
    router.on_key_repeat(key_repeat)
    router.on_mouse_click(mouse_click)
    router.on_mouse_release(mouse_release)

    on_key_press.assert_called_once_with(key_press)
    on_key_release.assert_called_once_with(key_release)
    on_key_repeat.assert_called_once_with(key_repeat)
    on_mouse_click.assert_called_once_with(mouse_click)
    on_mouse_release.assert_called_once_with(mouse_release)
