"""Tests for auto-conversion (space-triggered, AutoDetector wiring in LSwitchApp)."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, call, patch

import pytest

from lswitch.app import LSwitchApp
from lswitch.core.events import Event, EventType, KeyEventData
from lswitch.core.states import State
from lswitch.platform.xkb_adapter import LayoutInfo

from tests.conftest import MockXKBAdapter, MockSelectionAdapter, MockSystemAdapter

# ---------------------------------------------------------------------------
# Constants (evdev keycodes matching key_mapper.py)
# ---------------------------------------------------------------------------
KEY_G = 34  # "g"
KEY_H = 35  # "h"
KEY_B = 48  # "b"
KEY_D = 32  # "d"
KEY_T = 20  # "t"
KEY_N = 49  # "n" → together: "ghbdtn"

KEY_P = 25  # "p"
KEY_R = 19  # "r"
KEY_E = 18  # "e"
KEY_I = 23  # "i"
KEY_V = 47  # "v"
KEY_E2 = 18  # "e" (same as KEY_E) → "privet" = [25, 19, 23, 47, 18, 20]

KEY_A = 30  # "a"
KEY_SPACE = 57
KEY_BACKSPACE = 14


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _event(code: int, value: int = 1) -> Event:
    data = KeyEventData(code=code, value=value, device_name="test")
    return Event(type=EventType.KEY_PRESS, data=data, timestamp=time.time())


class _MockAutoDetector:
    """Minimal AutoDetector stub: unconditionally says convert/no-convert."""

    def __init__(self, should: bool = True, reason: str = "test"):
        self._should = should
        self._reason = reason

    def should_convert(self, word: str, current_layout: str) -> tuple[bool, str]:
        return self._should, self._reason


def _make_app(auto_switch: bool = True, threshold: int = 0) -> LSwitchApp:
    """App with all mocks and auto_switch configured."""
    app = LSwitchApp(headless=True, debug=True)
    app.xkb = MockXKBAdapter(layouts=["en", "ru"])
    app.selection = MockSelectionAdapter()
    app.system = MockSystemAdapter()
    app.virtual_kb = MagicMock()
    app.conversion_engine = MagicMock()
    app.event_manager = MagicMock()
    app.device_manager = MagicMock()
    # Patch config
    app.config._config['auto_switch'] = auto_switch
    app.config._config['auto_switch_threshold'] = threshold
    return app


def _fill_buffer(app: LSwitchApp, keycodes: list[int]) -> None:
    """Populate event_buffer and chars_in_buffer manually."""
    for code in keycodes:
        ev = _event(code)
        app.state_manager.context.event_buffer.append(ev.data)
        app.state_manager.context.chars_in_buffer += 1
    app.state_manager.context.state = State.TYPING


# ---------------------------------------------------------------------------
# _extract_last_word_events
# ---------------------------------------------------------------------------

class TestExtractLastWordEvents:
    """Unit tests for _extract_last_word_events()."""

    def test_empty_buffer_returns_empty(self):
        app = _make_app()
        word, events = app._extract_last_word_events()
        assert word == ""
        assert events == []

    def test_single_word(self):
        """Buffer = [g, h, b, d, t, n] → word = 'ghbdtn', 6 events."""
        app = _make_app()
        _fill_buffer(app, [KEY_G, KEY_H, KEY_B, KEY_D, KEY_T, KEY_N])
        word, events = app._extract_last_word_events()
        assert word == "ghbdtn"
        assert len(events) == 6

    def test_stops_at_space_in_buffer(self):
        """Buffer has a space event → only extract chars AFTER last space."""
        app = _make_app()
        # "hello " (simulated with KEY_A×5 + KEY_SPACE) + "ghbdtn"
        for code in [KEY_A] * 5:
            ev = _event(code)
            app.state_manager.context.event_buffer.append(ev.data)
            app.state_manager.context.chars_in_buffer += 1
        # Space event in buffer
        space_data = KeyEventData(code=KEY_SPACE, value=1, device_name="test")
        app.state_manager.context.event_buffer.append(space_data)
        app.state_manager.context.chars_in_buffer += 1
        # Last word "ghbdtn"
        _fill_buffer(app, [KEY_G, KEY_H, KEY_B, KEY_D, KEY_T, KEY_N])
        word, events = app._extract_last_word_events()
        assert word == "ghbdtn"
        assert len(events) == 6

    def test_stops_at_non_alpha_char(self):
        """Buffer ends with non-alpha (digit key) → stops there."""
        app = _make_app()
        # key 2 = "2" (digit, non-alpha)
        digit_data = KeyEventData(code=2, value=1, device_name="test")
        app.state_manager.context.event_buffer.append(digit_data)
        app.state_manager.context.chars_in_buffer += 1
        _fill_buffer(app, [KEY_G, KEY_H, KEY_B])
        word, events = app._extract_last_word_events()
        assert word == "ghb"
        assert len(events) == 3

    def test_events_in_correct_order(self):
        """Events returned are in original typing order (not reversed)."""
        app = _make_app()
        _fill_buffer(app, [KEY_G, KEY_H, KEY_B])
        word, events = app._extract_last_word_events()
        assert [e.code for e in events] == [KEY_G, KEY_H, KEY_B]


# ---------------------------------------------------------------------------
# _layout_to_lang
# ---------------------------------------------------------------------------

class TestLayoutToLang:
    def test_none_returns_en(self):
        app = _make_app()
        assert app._layout_to_lang(None) == "en"

    def test_en_layout(self):
        app = _make_app()
        layout = LayoutInfo(name="en", index=0, xkb_name="us")
        assert app._layout_to_lang(layout) == "en"

    def test_ru_layout(self):
        app = _make_app()
        layout = LayoutInfo(name="ru", index=1, xkb_name="ru")
        assert app._layout_to_lang(layout) == "ru"

    def test_unknown_layout_defaults_to_en(self):
        app = _make_app()
        layout = LayoutInfo(name="de", index=2, xkb_name="de")
        assert app._layout_to_lang(layout) == "en"


# ---------------------------------------------------------------------------
# _try_auto_conversion_at_space
# ---------------------------------------------------------------------------

class TestTryAutoConversionAtSpace:
    def test_empty_buffer_returns_false(self):
        app = _make_app(auto_switch=True, threshold=0)
        app.auto_detector = _MockAutoDetector(should=True)
        result = app._try_auto_conversion_at_space()
        assert result is False

    def test_below_threshold_returns_false(self):
        """chars_in_buffer < threshold → no conversion."""
        app = _make_app(auto_switch=True, threshold=10)
        app.auto_detector = _MockAutoDetector(should=True)
        _fill_buffer(app, [KEY_G, KEY_H, KEY_B])  # buf=3 chars < threshold=10
        result = app._try_auto_conversion_at_space()
        assert result is False

    def test_above_threshold_returns_true(self):
        """chars_in_buffer >= threshold → conversion proceeds."""
        app = _make_app(auto_switch=True, threshold=3)
        app.auto_detector = _MockAutoDetector(should=True)
        _fill_buffer(app, [KEY_G, KEY_H, KEY_B, KEY_D, KEY_T, KEY_N])  # buf=6 >= threshold=3
        with patch.object(app, '_do_auto_conversion_at_space'):
            result = app._try_auto_conversion_at_space()
        assert result is True

    def test_detector_says_no_returns_false(self):
        app = _make_app(auto_switch=True, threshold=0)
        app.auto_detector = _MockAutoDetector(should=False)
        _fill_buffer(app, [KEY_G, KEY_H, KEY_B, KEY_D, KEY_T, KEY_N])
        result = app._try_auto_conversion_at_space()
        assert result is False

    def test_detector_says_yes_returns_true(self):
        app = _make_app(auto_switch=True, threshold=0)
        app.auto_detector = _MockAutoDetector(should=True)
        _fill_buffer(app, [KEY_G, KEY_H, KEY_B, KEY_D, KEY_T, KEY_N])  # "ghbdtn"
        with patch.object(app, '_do_auto_conversion_at_space') as mock_do:
            result = app._try_auto_conversion_at_space()
        assert result is True
        mock_do.assert_called_once()

    def test_word_too_short_returns_false(self):
        """Words < 3 chars are always skipped, regardless of threshold."""
        app = _make_app(auto_switch=True, threshold=0)
        app.auto_detector = _MockAutoDetector(should=True)
        _fill_buffer(app, [KEY_G, KEY_H])  # "gh" — 2 chars < MIN_WORD_LEN=3
        result = app._try_auto_conversion_at_space()
        assert result is False

    def test_no_auto_detector_returns_false(self):
        app = _make_app(auto_switch=True, threshold=0)
        app.auto_detector = None
        _fill_buffer(app, [KEY_G, KEY_H, KEY_B, KEY_D, KEY_T, KEY_N])
        result = app._try_auto_conversion_at_space()
        assert result is False

    def test_detector_exception_returns_false(self):
        app = _make_app(auto_switch=True, threshold=0)
        bad_detector = MagicMock()
        bad_detector.should_convert.side_effect = RuntimeError("crash")
        app.auto_detector = bad_detector
        _fill_buffer(app, [KEY_G, KEY_H, KEY_B, KEY_D, KEY_T, KEY_N])
        result = app._try_auto_conversion_at_space()
        assert result is False


# ---------------------------------------------------------------------------
# _do_auto_conversion_at_space
# ---------------------------------------------------------------------------

class TestDoAutoConversionAtSpace:
    def _setup(self):
        app = _make_app(auto_switch=True, threshold=0)
        # Add 6 events for "ghbdtn"
        word_events = []
        for code in [KEY_G, KEY_H, KEY_B, KEY_D, KEY_T, KEY_N]:
            ev = _event(code)
            app.state_manager.context.event_buffer.append(ev.data)
            app.state_manager.context.chars_in_buffer += 1
            word_events.append(ev.data)
        app.state_manager.context.state = State.TYPING
        return app, word_events

    def test_sends_backspaces_word_plus_one(self):
        """Deletes word_len + 1 chars (word + the space that landed in app)."""
        app, word_events = self._setup()
        app._do_auto_conversion_at_space(6, word_events, "en_to_ru")
        app.virtual_kb.tap_key.assert_any_call(KEY_BACKSPACE, n_times=7)

    def test_switches_to_ru_layout(self):
        """Direction en_to_ru → switches to 'ru' layout."""
        app, word_events = self._setup()
        app._do_auto_conversion_at_space(6, word_events, "en_to_ru")
        ru_layout = app.xkb.get_layouts()[1]  # index 1 = "ru"
        assert app.xkb.switch_calls[-1] == ru_layout

    def test_replays_word_events(self):
        """replay_events called with the word events."""
        app, word_events = self._setup()
        app._do_auto_conversion_at_space(6, word_events, "en_to_ru")
        app.virtual_kb.replay_events.assert_called_once_with(word_events)

    def test_re_adds_space(self):
        """After replay, taps Space to restore the word boundary."""
        app, word_events = self._setup()
        app._do_auto_conversion_at_space(6, word_events, "en_to_ru")
        app.virtual_kb.tap_key.assert_any_call(KEY_SPACE)

    def test_resets_context_to_idle(self):
        """Context is reset and state is IDLE after conversion."""
        app, word_events = self._setup()
        app._do_auto_conversion_at_space(6, word_events, "en_to_ru")
        assert app.state_manager.context.chars_in_buffer == 0
        assert app.state_manager.context.event_buffer == []
        assert app.state_manager.context.state == State.IDLE

    def test_context_reset_on_exception(self):
        """Even if VirtualKeyboard raises, context is reset."""
        app, word_events = self._setup()
        app.virtual_kb.tap_key.side_effect = RuntimeError("hw error")
        app._do_auto_conversion_at_space(6, word_events, "en_to_ru")
        assert app.state_manager.context.chars_in_buffer == 0
        assert app.state_manager.context.state == State.IDLE

    def test_ru_to_en_switches_to_en_layout(self):
        """Direction ru_to_en → switches to 'en' layout."""
        app, word_events = self._setup()
        # Set current layout to ru
        app.xkb._current = 1
        app._do_auto_conversion_at_space(6, word_events, "ru_to_en")
        en_layout = app.xkb.get_layouts()[0]  # index 0 = "en"
        assert app.xkb.switch_calls[-1] == en_layout


# ---------------------------------------------------------------------------
# Space key integration in _on_key_press
# ---------------------------------------------------------------------------

class TestSpaceKeyHandling:
    def test_space_added_to_buffer_when_auto_switch_disabled(self):
        """auto_switch=False → space goes to buffer normally."""
        app = _make_app(auto_switch=False, threshold=0)
        app._wire_event_bus()
        event = _event(KEY_SPACE)
        app._on_key_press(event)
        assert app.state_manager.context.chars_in_buffer == 1
        assert app.state_manager.context.event_buffer[0].code == KEY_SPACE

    def test_space_added_to_buffer_when_no_word_to_convert(self):
        """auto_switch=True but empty buffer → space goes to buffer."""
        app = _make_app(auto_switch=True, threshold=0)
        app.auto_detector = _MockAutoDetector(should=False)
        app._wire_event_bus()
        event = _event(KEY_SPACE)
        app._on_key_press(event)
        assert app.state_manager.context.chars_in_buffer == 1

    def test_space_triggers_auto_conversion(self):
        """auto_switch=True, detector says yes → _try_auto_conversion_at_space fires."""
        app = _make_app(auto_switch=True, threshold=0)
        app.auto_detector = _MockAutoDetector(should=True)
        app._wire_event_bus()
        _fill_buffer(app, [KEY_G, KEY_H, KEY_B, KEY_D, KEY_T, KEY_N])
        with patch.object(app, '_try_auto_conversion_at_space', return_value=True) as mock_try:
            event = _event(KEY_SPACE)
            app._on_key_press(event)
            mock_try.assert_called_once()

    def test_space_not_in_buffer_after_successful_auto_conversion(self):
        """When auto-conversion fires, space is NOT added to event_buffer."""
        app = _make_app(auto_switch=True, threshold=0)
        app.auto_detector = _MockAutoDetector(should=True)
        app._wire_event_bus()
        _fill_buffer(app, [KEY_G, KEY_H, KEY_B, KEY_D, KEY_T, KEY_N])
        with patch.object(app, '_do_auto_conversion_at_space'):
            # _try_auto_conversion_at_space will return True (detector says yes)
            event = _event(KEY_SPACE)
            app._on_key_press(event)
        # Buffer was reset by _do_auto_conversion_at_space (mocked here, so still 6)
        # The key assertion: no SPACE key in event_buffer
        space_in_buf = any(ev.code == KEY_SPACE for ev in app.state_manager.context.event_buffer)
        assert not space_in_buf

    def test_auto_detector_none_space_goes_to_buffer(self):
        """auto_switch=True but auto_detector=None → safe fallback, space in buffer."""
        app = _make_app(auto_switch=True, threshold=0)
        app.auto_detector = None
        app._wire_event_bus()
        event = _event(KEY_SPACE)
        app._on_key_press(event)
        assert app.state_manager.context.chars_in_buffer == 1

    def test_auto_detector_initialized_to_none_at_construction(self):
        """auto_detector is None until _init_platform() is called."""
        app = LSwitchApp(headless=True)
        assert app.auto_detector is None


# ---------------------------------------------------------------------------
# Integration: full word boundary auto-detect, end-to-end (mocked VirtualKeyboard)
# ---------------------------------------------------------------------------

class TestAutoConvertEndToEnd:
    """Integration test: type "ghbdtn", press Space, expect conversion actions."""

    def _run(self) -> LSwitchApp:
        app = _make_app(auto_switch=True, threshold=0)
        app.auto_detector = _MockAutoDetector(should=True, reason="dict: converted found")
        app._wire_event_bus()
        # Type "ghbdtn"
        for code in [KEY_G, KEY_H, KEY_B, KEY_D, KEY_T, KEY_N]:
            app._on_key_press(_event(code))
        # Press Space → triggers auto-conversion
        app._on_key_press(_event(KEY_SPACE))
        return app

    def test_backspace_sent_for_word_plus_space(self):
        """7 backspaces sent = 6 (word) + 1 (space that landed in app)."""
        app = self._run()
        app.virtual_kb.tap_key.assert_any_call(KEY_BACKSPACE, n_times=7)

    def test_layout_switched_to_ru(self):
        """Layout switched to 'ru' (en_to_ru, current layout was 'en')."""
        app = self._run()
        ru_layout = app.xkb.get_layouts()[1]
        assert app.xkb.switch_calls[-1] == ru_layout

    def test_replay_events_called(self):
        """replay_events called once with the 6 word events."""
        app = self._run()
        assert app.virtual_kb.replay_events.call_count == 1
        replayed_events = app.virtual_kb.replay_events.call_args[0][0]
        assert len(replayed_events) == 6

    def test_space_re_added(self):
        """Space tapped to restore word boundary after converted word."""
        app = self._run()
        app.virtual_kb.tap_key.assert_any_call(KEY_SPACE)

    def test_context_idle_after_conversion(self):
        """State machine is IDLE and buffer is empty after conversion."""
        app = self._run()
        assert app.state_manager.context.state == State.IDLE
        assert app.state_manager.context.chars_in_buffer == 0
        assert app.state_manager.context.event_buffer == []

    def test_no_conversion_when_word_is_english(self):
        """Correct layout → detector says no → no conversion, space in buffer."""
        app = _make_app(auto_switch=True, threshold=0)
        app.auto_detector = _MockAutoDetector(should=False)
        app._wire_event_bus()
        for code in [KEY_H, KEY_E, KEY_A]:  # "hea" — 3 alpha chars
            app._on_key_press(_event(code))
        app._on_key_press(_event(KEY_SPACE))
        # Space should be in buffer (no conversion fired)
        assert any(ev.code == KEY_SPACE for ev in app.state_manager.context.event_buffer)
        app.virtual_kb.replay_events.assert_not_called()
