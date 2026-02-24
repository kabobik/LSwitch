"""Integration test: EventManager + StateManager + ConversionEngine wired via EventBus."""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from lswitch.core.event_bus import EventBus
from lswitch.core.event_manager import (
    EventManager,
    KEY_LEFTSHIFT,
    KEY_RIGHTSHIFT,
    NAVIGATION_KEYS,
)
from lswitch.core.events import Event, EventType, KeyEventData
from lswitch.core.state_manager import StateManager
from lswitch.core.states import State, StateContext
from lswitch.core.conversion_engine import ConversionEngine
from lswitch.platform.selection_adapter import SelectionInfo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

EV_KEY = 1


def _ev(code: int, value: int, type_: int = EV_KEY):
    """Minimal evdev-like event."""
    return SimpleNamespace(type=type_, code=code, value=value)


class _MiniSystem:
    """Wires EventBus ↔ StateManager ↔ ConversionEngine with mock adapters."""

    def __init__(self):
        self.bus = EventBus()
        self.event_mgr = EventManager(self.bus, debug=True)
        self.state_mgr = StateManager(double_click_timeout=0.4, debug=True)

        # Mock adapters
        self.mock_xkb = MagicMock()
        self.mock_selection = MagicMock()
        self.mock_selection.has_fresh_selection.return_value = False
        self.mock_selection.get_selection.return_value = SelectionInfo(text="", owner_id=0, timestamp=0.0)
        self.mock_vk = MagicMock()
        self.mock_dict = MagicMock()
        self.mock_system = MagicMock()

        self.engine = ConversionEngine(
            xkb=self.mock_xkb,
            selection=self.mock_selection,
            virtual_kb=self.mock_vk,
            dictionary=self.mock_dict,
            system=self.mock_system,
            debug=True,
        )

        self.convert_called = 0
        self._wire()

    def _wire(self):
        """Subscribe StateManager handlers to EventBus."""
        self.bus.subscribe(EventType.KEY_PRESS, self._on_key_press)
        self.bus.subscribe(EventType.KEY_RELEASE, self._on_key_release)
        self.bus.subscribe(EventType.KEY_REPEAT, self._on_key_repeat)
        self.bus.subscribe(EventType.MOUSE_CLICK, self._on_mouse_click)

    def _on_key_press(self, event: Event):
        data: KeyEventData = event.data
        code = data.code

        # Feed into state manager
        self.state_mgr.on_key_press(code)

        # Accumulate into context buffer (simulating what a real system does)
        self.state_mgr.context.event_buffer.append(_ev(code, 1))
        self.state_mgr.context.chars_in_buffer += 1

        # Shift press
        if code in {KEY_LEFTSHIFT, KEY_RIGHTSHIFT}:
            # Undo char count — shift isn't a character
            self.state_mgr.context.chars_in_buffer -= 1
            self.state_mgr.on_shift_down()

    def _on_key_release(self, event: Event):
        data: KeyEventData = event.data
        code = data.code

        # Navigation resets
        if code in NAVIGATION_KEYS:
            self.state_mgr.on_navigation()
            return

        # Shift release → check double-shift
        if code in {KEY_LEFTSHIFT, KEY_RIGHTSHIFT}:
            prev_state = self.state_mgr.state
            is_double = self.state_mgr.on_shift_up()
            # Trigger conversion only when the transition INTO CONVERTING
            # actually happened (prev was not already CONVERTING).
            if is_double and prev_state != State.CONVERTING and self.state_mgr.state == State.CONVERTING:
                self._do_convert()

    def _on_key_repeat(self, event: Event):
        data: KeyEventData = event.data
        if data.code == 14:  # KEY_BACKSPACE
            self.state_mgr.context.backspace_repeats += 1
            if self.state_mgr.context.backspace_repeats >= 3:
                self.state_mgr.on_backspace_hold()

    def _on_mouse_click(self, event: Event):
        self.state_mgr.on_mouse_click()

    def _do_convert(self):
        self.convert_called += 1
        self.engine.convert(self.state_mgr.context)
        self.state_mgr.on_conversion_complete()

    # ---- high-level simulation helpers ----

    def type_keys(self, keycodes: list[int]):
        """Simulate pressing and releasing a list of keycodes."""
        for kc in keycodes:
            self.event_mgr.handle_raw_event(_ev(kc, 1))  # press
            self.event_mgr.handle_raw_event(_ev(kc, 0))  # release

    def quick_shift_tap(self):
        """Simulate a single Shift press+release (first tap of a potential double-shift)."""
        self.event_mgr.handle_raw_event(_ev(KEY_LEFTSHIFT, 1))
        self.event_mgr.handle_raw_event(_ev(KEY_LEFTSHIFT, 0))

    def double_shift_tap(self):
        """Simulate two quick Shift taps — triggers conversion.

        Design: first tap records last_shift_time, second tap detects
        delta < timeout and fires shift_up_double → CONVERTING.
        """
        self.quick_shift_tap()  # first tap: shift_up_single, records last_shift_time
        self.quick_shift_tap()  # second tap: delta < timeout → shift_up_double


# ---------------------------------------------------------------------------
# 1. Набор текста → двойной Shift → конвертация → IDLE
# ---------------------------------------------------------------------------

class TestTypeThenDoubleShiftConverts:
    def test_typing_then_double_shift_triggers_conversion(self):
        sys = _MiniSystem()

        # Type "ghbdtn" (keycodes for g=34, h=35, b=48, d=32, t=20, n=49)
        sys.type_keys([34, 35, 48, 32, 20, 49])

        assert sys.state_mgr.state == State.TYPING

        # Double shift (two taps)
        sys.double_shift_tap()

        # Conversion should have been triggered
        assert sys.convert_called == 1
        # State should return to IDLE after conversion
        assert sys.state_mgr.state == State.IDLE

    def test_state_transitions_during_conversion(self):
        sys = _MiniSystem()

        # IDLE → type → TYPING
        sys.event_mgr.handle_raw_event(_ev(34, 1))  # key press
        assert sys.state_mgr.state == State.TYPING
        sys.event_mgr.handle_raw_event(_ev(34, 0))  # key release

        # TYPING → shift down → SHIFT_PRESSED
        sys.event_mgr.handle_raw_event(_ev(KEY_LEFTSHIFT, 1))
        assert sys.state_mgr.state == State.SHIFT_PRESSED

        # First Shift up → shift_up_single → back to TYPING (records last_shift_time)
        sys.event_mgr.handle_raw_event(_ev(KEY_LEFTSHIFT, 0))
        assert sys.state_mgr.state == State.TYPING

        # Second Shift tap quickly → shift_up_double → CONVERTING → complete → IDLE
        sys.event_mgr.handle_raw_event(_ev(KEY_LEFTSHIFT, 1))
        sys.event_mgr.handle_raw_event(_ev(KEY_LEFTSHIFT, 0))

        assert sys.state_mgr.state == State.IDLE  # conversion + complete → IDLE
        assert sys.convert_called == 1


# ---------------------------------------------------------------------------
# 2. Двойной Shift во время конвертации → игнорируется
# ---------------------------------------------------------------------------

class TestDoubleShiftDuringConversion:
    def test_second_double_shift_during_converting_ignored(self):
        sys = _MiniSystem()

        # Override _do_convert to NOT call on_conversion_complete
        # so state stays in CONVERTING
        original_convert = sys._do_convert

        def converting_but_stay(self_ref=sys):
            self_ref.convert_called += 1
            # Don't call on_conversion_complete — stay in CONVERTING

        sys._do_convert = converting_but_stay

        # Type and trigger first conversion
        sys.type_keys([34, 35])
        sys.double_shift_tap()

        assert sys.convert_called == 1
        assert sys.state_mgr.state == State.CONVERTING

        # Try second double-shift while CONVERTING
        sys.event_mgr.handle_raw_event(_ev(KEY_LEFTSHIFT, 1))
        sys.event_mgr.handle_raw_event(_ev(KEY_LEFTSHIFT, 0))

        # Should still be 1 — second shift was ignored
        assert sys.convert_called == 1
        assert sys.state_mgr.state == State.CONVERTING


# ---------------------------------------------------------------------------
# 3. Навигация сбрасывает буфер
# ---------------------------------------------------------------------------

class TestNavigationResetsBuffer:
    def test_navigation_resets_to_idle(self):
        sys = _MiniSystem()

        # Type some keys
        sys.type_keys([16, 17, 18])
        assert sys.state_mgr.state == State.TYPING
        assert sys.state_mgr.context.chars_in_buffer > 0

        # Press navigation key (arrow up = 103)
        sys.event_mgr.handle_raw_event(_ev(103, 1))   # press
        sys.event_mgr.handle_raw_event(_ev(103, 0))   # release → triggers navigation

        assert sys.state_mgr.state == State.IDLE
        assert sys.state_mgr.context.chars_in_buffer == 0
        assert len(sys.state_mgr.context.event_buffer) == 0


# ---------------------------------------------------------------------------
# 4. Backspace hold → selection mode
# ---------------------------------------------------------------------------

class TestBackspaceHoldSelectionMode:
    def test_backspace_hold_then_shift_uses_selection(self):
        sys = _MiniSystem()

        # Set up selection so conversion can succeed
        sys.mock_selection.has_fresh_selection.return_value = False
        sys.mock_selection.get_selection.return_value = SelectionInfo(
            text="ghbdtn", owner_id=1, timestamp=time.time()
        )

        # Type a few keys
        sys.type_keys([16, 17, 18])
        assert sys.state_mgr.state == State.TYPING

        # Simulate backspace hold: 3+ repeats
        for _ in range(4):
            sys.event_mgr.handle_raw_event(_ev(14, 2))  # backspace repeat

        assert sys.state_mgr.state == State.BACKSPACE_HOLD
        assert sys.state_mgr.context.backspace_hold_active is True

        # Quick shift tap from BACKSPACE_HOLD → conversion
        sys.double_shift_tap()

        assert sys.convert_called == 1
        # Engine should have chosen "selection" mode for backspace_hold_active
        assert sys.state_mgr.state == State.IDLE
        # Verify selection mode was used (replace_selection called), NOT retype (tap_key)
        sys.mock_selection.replace_selection.assert_called_once()
        sys.mock_vk.tap_key.assert_not_called()

    def test_backspace_hold_chooses_selection_mode(self):
        sys = _MiniSystem()

        ctx = StateContext()
        ctx.state = State.CONVERTING
        ctx.backspace_hold_active = True
        ctx.chars_in_buffer = 5

        mode = sys.engine.choose_mode(ctx)
        assert mode == "selection"
