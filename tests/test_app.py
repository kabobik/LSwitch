"""Tests for lswitch.app — LSwitchApp (no real X11 / evdev)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from lswitch.app import LSwitchApp
from lswitch.core.events import Event, EventType, KeyEventData
from lswitch.core.states import State

# Re-use shared mock adapters from conftest
from tests.conftest import MockXKBAdapter, MockSelectionAdapter, MockSystemAdapter


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _make_app(**kwargs) -> LSwitchApp:
    """Create an LSwitchApp with mocked platform components."""
    app = LSwitchApp(headless=True, debug=True, **kwargs)
    # Replace platform components with mocks
    app.xkb = MockXKBAdapter()
    app.selection = MockSelectionAdapter()
    app.system = MockSystemAdapter()
    app.virtual_kb = MagicMock()
    app.conversion_engine = MagicMock()
    app.event_manager = MagicMock()
    app.device_manager = MagicMock()
    return app


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------

class TestLSwitchAppInit:
    """LSwitchApp construction and attribute defaults."""

    def test_default_parameters(self):
        app = LSwitchApp()
        assert app.headless is False
        assert app.debug is False
        assert app._running is False

    def test_custom_parameters(self):
        app = LSwitchApp(headless=True, debug=True)
        assert app.headless is True
        assert app.debug is True

    def test_has_event_bus_and_state_manager(self):
        app = LSwitchApp()
        assert app.event_bus is not None
        assert app.state_manager is not None

    def test_platform_components_initially_none(self):
        app = LSwitchApp()
        assert app.xkb is None
        assert app.selection is None
        assert app.system is None
        assert app.virtual_kb is None
        assert app.device_manager is None
        assert app.conversion_engine is None
        assert app.event_manager is None


class TestWireEventBus:
    """_wire_event_bus subscribes handlers to the EventBus."""

    def test_subscribes_key_press(self):
        app = _make_app()
        app._wire_event_bus()
        # Verify handlers registered
        assert len(app.event_bus._handlers[EventType.KEY_PRESS]) > 0

    def test_subscribes_key_release(self):
        app = _make_app()
        app._wire_event_bus()
        assert len(app.event_bus._handlers[EventType.KEY_RELEASE]) > 0

    def test_subscribes_key_repeat(self):
        app = _make_app()
        app._wire_event_bus()
        assert len(app.event_bus._handlers[EventType.KEY_REPEAT]) > 0

    def test_subscribes_mouse_click(self):
        app = _make_app()
        app._wire_event_bus()
        assert len(app.event_bus._handlers[EventType.MOUSE_CLICK]) > 0


class TestDoConversion:
    """_do_conversion calls ConversionEngine.convert()."""

    def test_calls_convert_when_converting(self):
        app = _make_app()
        app.state_manager.context.state = State.CONVERTING
        app._do_conversion()
        app.conversion_engine.convert.assert_called_once_with(app.state_manager.context)

    def test_does_not_call_convert_when_idle(self):
        app = _make_app()
        app.state_manager.context.state = State.IDLE
        app._do_conversion()
        app.conversion_engine.convert.assert_not_called()

    def test_calls_on_conversion_complete_after_convert(self):
        app = _make_app()
        app.state_manager.context.state = State.CONVERTING
        with patch.object(app.state_manager, 'on_conversion_complete') as mock_complete:
            app._do_conversion()
            mock_complete.assert_called_once()


class TestOnMouseClick:
    """_on_mouse_click delegates to state_manager."""

    def test_calls_state_manager_on_mouse_click(self):
        app = _make_app()
        with patch.object(app.state_manager, 'on_mouse_click') as mock_click:
            event = Event(EventType.MOUSE_CLICK, KeyEventData(code=272, value=1), 0.0)
            app._on_mouse_click(event)
            mock_click.assert_called_once()


class TestStop:
    """stop() handles None components gracefully."""

    def test_stop_with_none_components(self):
        app = LSwitchApp()
        # All platform components are None — must not raise
        app.stop()

    def test_stop_sets_running_false(self):
        app = _make_app()
        app._running = True
        app.stop()
        assert app._running is False

    def test_stop_calls_close_on_device_manager(self):
        app = _make_app()
        app.stop()
        app.device_manager.close.assert_called_once()

    def test_stop_calls_close_on_virtual_kb(self):
        app = _make_app()
        app.stop()
        app.virtual_kb.close.assert_called_once()

    def test_stop_idempotent(self):
        app = _make_app()
        app.stop()
        app.stop()  # second call must not raise


# ------------------------------------------------------------------
# Helpers for event callbacks tests
# ------------------------------------------------------------------

import time
from lswitch.core.event_manager import (
    KEY_LEFTSHIFT, KEY_BACKSPACE, SHIFT_KEYS, NAVIGATION_KEYS,
)

# A regular key code (letter 'A')
KEY_A = 30


def _make_event(event_type: EventType, code: int, value: int = 1, device_name: str = "test"):
    data = KeyEventData(code=code, value=value, device_name=device_name)
    return Event(type=event_type, data=data, timestamp=time.time())


def _wired_app() -> LSwitchApp:
    """Create app with event bus wired."""
    app = _make_app()
    app._wire_event_bus()
    return app


# ------------------------------------------------------------------
# _on_key_press tests
# ------------------------------------------------------------------

class TestOnKeyPress:
    def test_shift_calls_shift_down(self):
        """Shift press → on_shift_down(), NOT on_key_press()."""
        app = _wired_app()
        with patch.object(app.state_manager, 'on_shift_down') as mock_sd, \
             patch.object(app.state_manager, 'on_key_press') as mock_kp:
            event = _make_event(EventType.KEY_PRESS, KEY_LEFTSHIFT)
            app._on_key_press(event)
            mock_sd.assert_called_once()
            mock_kp.assert_not_called()

    def test_regular_key_increments_buffer(self):
        """Regular key press → chars_in_buffer += 1, event_buffer append."""
        app = _wired_app()
        assert app.state_manager.context.chars_in_buffer == 0
        event = _make_event(EventType.KEY_PRESS, KEY_A)
        app._on_key_press(event)
        assert app.state_manager.context.chars_in_buffer == 1
        assert len(app.state_manager.context.event_buffer) == 1
        assert app.state_manager.context.event_buffer[0].code == KEY_A

    def test_resets_backspace_repeats(self):
        """Regular key press → backspace_repeats = 0."""
        app = _wired_app()
        app.state_manager.context.backspace_repeats = 2
        event = _make_event(EventType.KEY_PRESS, KEY_A)
        app._on_key_press(event)
        assert app.state_manager.context.backspace_repeats == 0


# ------------------------------------------------------------------
# _on_key_release tests
# ------------------------------------------------------------------

class TestOnKeyRelease:
    def test_shift_double_triggers_conversion(self):
        """Shift release with double-shift → _do_conversion called."""
        app = _wired_app()
        with patch.object(app.state_manager, 'on_shift_up', return_value=True), \
             patch.object(app, '_do_conversion') as mock_conv:
            event = _make_event(EventType.KEY_RELEASE, KEY_LEFTSHIFT, value=0)
            app._on_key_release(event)
            mock_conv.assert_called_once()

    def test_navigation_resets_state(self):
        """Navigation key release → state_manager.on_navigation()."""
        app = _wired_app()
        nav_key = next(iter(NAVIGATION_KEYS))  # pick any navigation key
        with patch.object(app.state_manager, 'on_navigation') as mock_nav:
            event = _make_event(EventType.KEY_RELEASE, nav_key, value=0)
            app._on_key_release(event)
            mock_nav.assert_called_once()

    def test_backspace_decrements_buffer(self):
        """Backspace release → chars_in_buffer -= 1."""
        app = _wired_app()
        app.state_manager.context.chars_in_buffer = 5
        event = _make_event(EventType.KEY_RELEASE, KEY_BACKSPACE, value=0)
        app._on_key_release(event)
        assert app.state_manager.context.chars_in_buffer == 4

    def test_backspace_resets_repeats(self):
        """Backspace release → backspace_repeats = 0."""
        app = _wired_app()
        app.state_manager.context.backspace_repeats = 5
        event = _make_event(EventType.KEY_RELEASE, KEY_BACKSPACE, value=0)
        app._on_key_release(event)
        assert app.state_manager.context.backspace_repeats == 0

    def test_backspace_no_negative(self):
        """Backspace release с пустым буфером → chars_in_buffer не уходит в минус."""
        app = _wired_app()
        assert app.state_manager.context.chars_in_buffer == 0
        event = _make_event(EventType.KEY_RELEASE, KEY_BACKSPACE, value=0)
        app._on_key_release(event)
        assert app.state_manager.context.chars_in_buffer == 0


# ------------------------------------------------------------------
# _on_key_repeat tests
# ------------------------------------------------------------------

class TestOnKeyRepeat:
    def test_backspace_increments_counter(self):
        """Each backspace repeat → backspace_repeats += 1."""
        app = _wired_app()
        assert app.state_manager.context.backspace_repeats == 0
        event = _make_event(EventType.KEY_REPEAT, KEY_BACKSPACE, value=2)
        app._on_key_repeat(event)
        assert app.state_manager.context.backspace_repeats == 1
        app._on_key_repeat(event)
        assert app.state_manager.context.backspace_repeats == 2

    def test_backspace_hold_detection(self):
        """3+ backspace repeats → on_backspace_hold()."""
        app = _wired_app()
        event = _make_event(EventType.KEY_REPEAT, KEY_BACKSPACE, value=2)
        with patch.object(app.state_manager, 'on_backspace_hold') as mock_hold:
            # First two repeats — no hold yet
            app._on_key_repeat(event)
            app._on_key_repeat(event)
            mock_hold.assert_not_called()
            # Third repeat — triggers hold
            app._on_key_repeat(event)
            mock_hold.assert_called_once()

    def test_backspace_repeats_reset_between_sessions(self):
        """Hold backspace → release → type → hold again → no false positive.

        This is the KEY test for the backspace_repeats accumulation bug.
        """
        app = _wired_app()
        bs_repeat = _make_event(EventType.KEY_REPEAT, KEY_BACKSPACE, value=2)
        bs_release = _make_event(EventType.KEY_RELEASE, KEY_BACKSPACE, value=0)
        key_a = _make_event(EventType.KEY_PRESS, KEY_A, value=1)

        # Session 1: 2 backspace repeats
        app._on_key_repeat(bs_repeat)
        app._on_key_repeat(bs_repeat)
        assert app.state_manager.context.backspace_repeats == 2

        # Release backspace → resets
        app._on_key_release(bs_release)
        assert app.state_manager.context.backspace_repeats == 0

        # Type regular key (also resets, belt-and-suspenders)
        app._on_key_press(key_a)
        assert app.state_manager.context.backspace_repeats == 0

        # Session 2: 1 backspace repeat → must be 1, NOT 3
        app._on_key_repeat(bs_repeat)
        assert app.state_manager.context.backspace_repeats == 1

        with patch.object(app.state_manager, 'on_backspace_hold') as mock_hold:
            # Still only 1 repeat — should NOT trigger hold
            mock_hold.assert_not_called()
