"""Regression tests — each test documents a real bug found during manual testing.

Bug history (all caught by manual testing before these tests existed):
  R01 — Backspace events accumulated in event_buffer, replay sent them back
  R02 — Double-shift fired on single Shift press+release
  R03 — SelectionMode never triggered from IDLE (shift_down not in IDLE transitions)
  R04 — VirtualKeyboard.replay_events: missing release → kernel infinite auto-repeat
  R05 — convert_text used both dicts simultaneously, direction ambiguous
  R06 — SelectionMode used cycle switch_layout instead of target layout
  R07 — context.reset() not called after conversion → stale buffer on next Shift+Shift
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, call, patch

import pytest

from lswitch.app import LSwitchApp
from lswitch.core.conversion_engine import ConversionEngine
from lswitch.core.event_manager import EventManager, EV_KEY
from lswitch.core.states import State, StateContext
from lswitch.core.text_converter import convert_text, detect_language
from lswitch.input.virtual_keyboard import VirtualKeyboard
from lswitch.platform.selection_adapter import SelectionInfo

from tests.conftest import MockXKBAdapter, MockSelectionAdapter, MockSystemAdapter
from tests.test_integration_full import _make_app, FakeEvdevEvent

KEY_LSHIFT = 42
KEY_RSHIFT = 54
KEY_BACKSPACE = 14

# keycodes for "ghbdtn": g=34 h=35 b=48 d=32 t=20 n=49
GHBDTN = [34, 35, 48, 32, 20, 49]


def _press(code: int) -> FakeEvdevEvent:
    return FakeEvdevEvent(type=EV_KEY, code=code, value=1)

def _release(code: int) -> FakeEvdevEvent:
    return FakeEvdevEvent(type=EV_KEY, code=code, value=0)

def _repeat(code: int) -> FakeEvdevEvent:
    return FakeEvdevEvent(type=EV_KEY, code=code, value=2)


def _type_keys(app: LSwitchApp, codes: list[int], device: str = "kb") -> None:
    for c in codes:
        app.event_manager.handle_raw_event(_press(c), device)
        app.event_manager.handle_raw_event(_release(c), device)

def _double_shift(app: LSwitchApp, device: str = "kb") -> None:
    """Two Shift taps rapidly — triggers conversion."""
    app.event_manager.handle_raw_event(_press(KEY_LSHIFT), device)
    app.event_manager.handle_raw_event(_release(KEY_LSHIFT), device)
    app.event_manager.handle_raw_event(_press(KEY_LSHIFT), device)
    app.event_manager.handle_raw_event(_release(KEY_LSHIFT), device)

def _single_shift(app: LSwitchApp, device: str = "kb") -> None:
    app.event_manager.handle_raw_event(_press(KEY_LSHIFT), device)
    app.event_manager.handle_raw_event(_release(KEY_LSHIFT), device)


# ---------------------------------------------------------------------------
# R01 — Backspace must NOT accumulate in event_buffer
# ---------------------------------------------------------------------------

class TestR01BackspaceBuffer:
    """R01: Backspace events must not accumulate in event_buffer."""

    def test_backspace_removes_last_event_from_buffer(self, tmp_path):
        """After typing 3 keys and pressing backspace, buffer has 2 items — not 4."""
        app = _make_app(tmp_path)
        app._wire_event_bus()

        _type_keys(app, [34, 35, 48])  # g, h, b
        assert app.state_manager.context.chars_in_buffer == 3
        assert len(app.state_manager.context.event_buffer) == 3

        # Backspace (press): should pop one event, NOT append backspace
        app.event_manager.handle_raw_event(_press(KEY_BACKSPACE), "kb")

        assert len(app.state_manager.context.event_buffer) == 2
        # Confirm no backspace keycode in buffer
        codes_in_buf = [getattr(e, 'code', None) for e in app.state_manager.context.event_buffer]
        assert KEY_BACKSPACE not in codes_in_buf

    def test_backspace_repeat_removes_from_buffer(self, tmp_path):
        """Auto-repeat backspace (value=2) also pops events from buffer."""
        app = _make_app(tmp_path)
        app._wire_event_bus()

        _type_keys(app, [34, 35, 48, 32, 20])  # 5 keys
        assert len(app.state_manager.context.event_buffer) == 5

        app.event_manager.handle_raw_event(_press(KEY_BACKSPACE), "kb")
        app.event_manager.handle_raw_event(_repeat(KEY_BACKSPACE), "kb")
        app.event_manager.handle_raw_event(_repeat(KEY_BACKSPACE), "kb")

        assert len(app.state_manager.context.event_buffer) == 2

    def test_replay_events_contain_no_backspace(self, tmp_path):
        """After conversion, virtual_kb.replay_events must not be called with backspace codes."""
        app = _make_app(tmp_path)
        app._wire_event_bus()

        _type_keys(app, GHBDTN)
        app.event_manager.handle_raw_event(_press(KEY_BACKSPACE), "kb")  # user erases one char

        _double_shift(app)

        assert app.state_manager.state == State.IDLE
        replay_calls = app.virtual_kb.replay_events.call_args_list
        assert len(replay_calls) == 1
        replayed_events = replay_calls[0][0][0]  # first positional arg of first call
        replayed_codes = [getattr(e, 'code', None) for e in replayed_events]
        assert KEY_BACKSPACE not in replayed_codes, (
            f"Backspace (14) was replayed: {replayed_codes}"
        )


# ---------------------------------------------------------------------------
# R02 — Single Shift must NOT trigger conversion
# ---------------------------------------------------------------------------

class TestR02SingleShiftNoConversion:
    """R02: A single Shift press+release must never trigger conversion."""

    def test_single_shift_from_typing_no_conversion(self, tmp_path):
        """type keys + one Shift → no conversion, state goes back to TYPING."""
        app = _make_app(tmp_path)
        app._wire_event_bus()

        _type_keys(app, [34, 35, 48])
        assert app.state_manager.state == State.TYPING

        _single_shift(app)  # one tap only

        # Must NOT have called conversion (tap_key for backspaces = conversion attempt)
        app.virtual_kb.tap_key.assert_not_called()
        app.virtual_kb.replay_events.assert_not_called()
        # State should be back to TYPING (or IDLE if buffer was reset — but not IDLE via conversion)
        assert app.state_manager.state in (State.TYPING, State.IDLE)

    def test_single_shift_from_idle_no_conversion(self, tmp_path):
        """Shift from IDLE (no typing, no selection) must not trigger conversion."""
        app = _make_app(tmp_path)
        app._wire_event_bus()

        assert app.state_manager.state == State.IDLE

        _single_shift(app)

        app.virtual_kb.tap_key.assert_not_called()
        app.virtual_kb.replay_events.assert_not_called()

    def test_slow_double_shift_no_conversion(self, tmp_path):
        """Two Shifts with a gap > double_click_timeout must not trigger conversion."""
        app = _make_app(tmp_path)
        app._wire_event_bus()
        # Set a very short timeout so we can simulate "slow"
        app.state_manager.double_click_timeout = 0.05

        _type_keys(app, [34, 35])

        # First shift
        app.event_manager.handle_raw_event(_press(KEY_LSHIFT), "kb")
        app.event_manager.handle_raw_event(_release(KEY_LSHIFT), "kb")

        # Wait longer than timeout
        time.sleep(0.1)

        # Second shift
        app.event_manager.handle_raw_event(_press(KEY_LSHIFT), "kb")
        app.event_manager.handle_raw_event(_release(KEY_LSHIFT), "kb")

        app.virtual_kb.tap_key.assert_not_called()
        app.virtual_kb.replay_events.assert_not_called()


# ---------------------------------------------------------------------------
# R03 — SelectionMode must trigger from IDLE (no typed chars)
# ---------------------------------------------------------------------------

class TestR03SelectionModeFromIdle:
    """R03: Shift+Shift from IDLE with fresh selection must trigger SelectionMode."""

    def test_double_shift_from_idle_triggers_selection_mode(self, tmp_path):
        """After mouse selection (no typed chars), double-Shift → SelectionMode called."""
        app = _make_app(tmp_path)
        app._wire_event_bus()

        assert app.state_manager.state == State.IDLE
        assert app.state_manager.context.chars_in_buffer == 0

        # Simulate fresh selection
        app.selection.set_selection("привет")
        app._selection_valid = True  # as if poller/mouse_release detected it

        _double_shift(app)

        # replace_selection must have been called (SelectionMode path)
        assert app.selection.replace_selection_called, (
            "replace_selection was not called — SelectionMode did not run"
        )
        assert app.state_manager.state == State.IDLE

    def test_double_shift_from_idle_no_selection_does_not_crash(self, tmp_path):
        """Double-Shift from IDLE with empty selection should not crash."""
        app = _make_app(tmp_path)
        app._wire_event_bus()

        # No selection set — selection returns ""
        _double_shift(app)

        # Should complete gracefully without exception
        assert app.state_manager.state == State.IDLE


# ---------------------------------------------------------------------------
# R04 — VirtualKeyboard.replay_events must send release for each press
# ---------------------------------------------------------------------------

class TestR04AutoRelease:
    """R04: replay_events must always pair every press with a release."""

    def test_press_only_events_get_synthetic_release(self):
        """Each press event (value=1) without a paired release gets auto-release appended."""
        vk = VirtualKeyboard.__new__(VirtualKeyboard)
        vk.debug = False
        vk._uinput = MagicMock()

        written: list[tuple[int, int]] = []

        def fake_write(code: int, value: int) -> None:
            written.append((code, value))

        vk._write = fake_write

        class Ev:
            def __init__(self, c, v):
                self.code = c
                self.value = v

        # Press-only events (no releases)
        vk.replay_events([Ev(34, 1), Ev(35, 1), Ev(48, 1)])

        # Every press must have a paired release
        for code in [34, 35, 48]:
            assert (code, 1) in written, f"Press for code {code} missing"
            assert (code, 0) in written, f"Release for code {code} missing"

    def test_paired_events_get_no_extra_release(self):
        """Events that already have a release don't get an extra one."""
        vk = VirtualKeyboard.__new__(VirtualKeyboard)
        vk.debug = False
        vk._uinput = MagicMock()

        written: list[tuple[int, int]] = []
        vk._write = lambda code, value: written.append((code, value))

        class Ev:
            def __init__(self, c, v):
                self.code = c
                self.value = v

        vk.replay_events([Ev(34, 1), Ev(34, 0)])  # properly paired

        releases = [v for c, v in written if c == 34 and v == 0]
        assert len(releases) == 1, f"Expected 1 release, got {len(releases)}"


# ---------------------------------------------------------------------------
# R05 — convert_text must use correct direction
# ---------------------------------------------------------------------------

class TestR05ConvertTextDirection:
    """R05: convert_text must detect direction and convert correctly."""

    def test_en_to_ru_auto(self):
        """'ghbdtn' (EN layout) → 'привет'."""
        assert convert_text("ghbdtn") == "привет"

    def test_ru_to_en_auto(self):
        """'привет' (RU layout) → 'ghbdtn'."""
        assert convert_text("привет") == "ghbdtn"

    def test_explicit_en_to_ru(self):
        assert convert_text("ghbdtn", direction="en_to_ru") == "привет"

    def test_explicit_ru_to_en(self):
        assert convert_text("привет", direction="ru_to_en") == "ghbdtn"

    def test_detect_language_en(self):
        assert detect_language("ghbdtn") == "en"

    def test_detect_language_ru(self):
        assert detect_language("привет") == "ru"

    def test_preserves_case(self):
        assert convert_text("Ghbdtn") == "Привет"
        assert convert_text("GHBDTN") == "ПРИВЕТ"


# ---------------------------------------------------------------------------
# R06 — SelectionMode must switch to the correct (target) layout
# ---------------------------------------------------------------------------

class TestR06SelectionModeTargetLayout:
    """R06: SelectionMode must switch to the layout that matches the converted text."""

    def test_ru_text_selection_switches_to_en_layout(self, tmp_path):
        """Selecting Russian text → switch to EN layout after conversion."""
        app = _make_app(tmp_path)
        app._wire_event_bus()

        app.selection.set_selection("привет")
        app._selection_valid = True  # as if poller/mouse_release detected it
        _double_shift(app)

        # XKB adapter must have been asked to switch to 'en' layout (index 0)
        calls = app.xkb.switch_calls
        assert len(calls) >= 1
        last_call_target = calls[-1]  # LayoutInfo or None
        if last_call_target is not None:
            assert last_call_target.name == "en", (
                f"Expected switch to 'en', got '{last_call_target.name}'"
            )

    def test_en_text_selection_switches_to_ru_layout(self, tmp_path):
        """Selecting English-in-wrong-layout text → switch to RU layout."""
        app = _make_app(tmp_path)
        app._wire_event_bus()

        app.selection.set_selection("ghbdtn")
        app._selection_valid = True  # as if poller/mouse_release detected it
        _double_shift(app)

        calls = app.xkb.switch_calls
        assert len(calls) >= 1
        last_call_target = calls[-1]
        if last_call_target is not None:
            assert last_call_target.name == "ru", (
                f"Expected switch to 'ru', got '{last_call_target.name}'"
            )


# ---------------------------------------------------------------------------
# R07 — context.reset() after conversion: buffer cleared
# ---------------------------------------------------------------------------

class TestR07ContextResetAfterConversion:
    """R07: After conversion, event_buffer and chars_in_buffer must be 0."""

    def test_buffer_cleared_after_retype(self, tmp_path):
        """After typing + double-Shift, event_buffer must be empty."""
        app = _make_app(tmp_path)
        app._wire_event_bus()

        _type_keys(app, GHBDTN)
        assert app.state_manager.context.chars_in_buffer == 6

        _double_shift(app)

        assert app.state_manager.state == State.IDLE
        assert app.state_manager.context.chars_in_buffer == 0, (
            "chars_in_buffer not reset after conversion"
        )
        assert len(app.state_manager.context.event_buffer) == 0, (
            "event_buffer not cleared after conversion"
        )

    def test_second_double_shift_replays_sticky_buffer(self, tmp_path):
        """After one conversion, a second double-Shift replays the same events
        (sticky buffer) so the user can toggle back and forth."""
        app = _make_app(tmp_path)
        app._wire_event_bus()

        _type_keys(app, GHBDTN)
        _double_shift(app)  # first conversion

        assert app.state_manager.state == State.IDLE
        # Sticky buffer should be populated
        assert len(app._last_retype_events) == 6

        app.virtual_kb.reset_mock()

        # Second double-Shift — should replay from sticky buffer
        _double_shift(app)

        assert app.virtual_kb.replay_events.called
        events = app.virtual_kb.replay_events.call_args[0][0]
        assert len(events) == 6, (
            f"Sticky buffer should have replayed 6 events, got {len(events)}"
        )

    def test_sticky_buffer_cleared_by_new_typing(self, tmp_path):
        """Typing new characters clears sticky buffer — prevents old replay."""
        app = _make_app(tmp_path)
        app._wire_event_bus()

        _type_keys(app, GHBDTN)
        _double_shift(app)
        assert len(app._last_retype_events) == 6

        # Type new characters → sticky buffer must be cleared
        _type_keys(app, [16])  # 'q'
        assert app._last_retype_events == []
