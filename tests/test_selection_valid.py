"""Tests for _selection_valid logic in LSwitchApp (app.py)."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from lswitch.app import LSwitchApp
from lswitch.core.events import Event, EventType
from lswitch.core.states import State, StateContext
from lswitch.platform.selection_adapter import SelectionInfo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_app() -> LSwitchApp:
    """Create LSwitchApp with mocked platform components (no real X11)."""
    app = LSwitchApp(headless=True, debug=True)

    # Inject mocks instead of calling _init_platform()
    app.xkb = MagicMock()
    app.selection = MagicMock()
    app.virtual_kb = MagicMock()
    app.system = MagicMock()
    app.device_manager = MagicMock()

    # Selection mock defaults
    app.selection.get_selection.return_value = SelectionInfo(
        text="", owner_id=0, timestamp=0.0,
    )

    # ConversionEngine with mocks
    from lswitch.core.conversion_engine import ConversionEngine
    from lswitch.intelligence.dictionary_service import DictionaryService

    dictionary = MagicMock()
    app.conversion_engine = ConversionEngine(
        xkb=app.xkb,
        selection=app.selection,
        virtual_kb=app.virtual_kb,
        dictionary=dictionary,
        system=app.system,
        debug=True,
    )

    # Wire event bus
    app._wire_event_bus()

    return app


def _key_event(code: int, device_name: str = "test-kbd") -> Event:
    """Create a KEY_PRESS or KEY_RELEASE Event with KeyEventData-like data."""
    data = MagicMock()
    data.code = code
    data.device_name = device_name
    data.shifted = False
    data.value = 1
    return Event(type=EventType.KEY_PRESS, data=data, timestamp=time.time())


def _key_release_event(code: int, device_name: str = "test-kbd") -> Event:
    data = MagicMock()
    data.code = code
    data.device_name = device_name
    data.shifted = False
    data.value = 0
    return Event(type=EventType.KEY_RELEASE, data=data, timestamp=time.time())


def _mouse_event() -> Event:
    data = MagicMock()
    return Event(type=EventType.MOUSE_CLICK, data=data, timestamp=time.time())


def _mouse_release_event() -> Event:
    data = MagicMock()
    return Event(type=EventType.MOUSE_RELEASE, data=data, timestamp=time.time())


# Key constants (matching evdev)
KEY_Q = 16
KEY_W = 17
KEY_E = 18
KEY_BACKSPACE = 14
KEY_SPACE = 57
KEY_ENTER = 28
KEY_LEFT = 105
KEY_RIGHT = 106
KEY_UP = 103
KEY_DOWN = 108
KEY_LEFTSHIFT = 42
KEY_RIGHTSHIFT = 54


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSelectionValidInitial:
    def test_selection_valid_false_initially(self):
        app = _make_app()
        assert app._selection_valid is False

    def test_prev_sel_text_empty_initially(self):
        app = _make_app()
        assert app._prev_sel_text == ""

    def test_prev_sel_owner_id_zero_initially(self):
        app = _make_app()
        assert app._prev_sel_owner_id == 0


class TestMouseRelease:
    """Tests for _on_mouse_release — detects drag-select and sets fresh."""

    def test_mouse_release_detects_new_selection(self):
        """PRIMARY changed between click (baseline) and release → fresh=True."""
        app = _make_app()
        app._prev_sel_text = ""
        app._prev_sel_owner_id = 0

        app.selection.get_selection.return_value = SelectionInfo(
            text="hello", owner_id=42, timestamp=time.time(),
        )

        app._on_mouse_release(_mouse_release_event())

        assert app._selection_valid is True
        assert app._prev_sel_text == "hello"
        assert app._prev_sel_owner_id == 42

    def test_mouse_release_no_change(self):
        """PRIMARY unchanged between click and release → stays False."""
        app = _make_app()
        app._prev_sel_text = "hello"
        app._prev_sel_owner_id = 42

        app.selection.get_selection.return_value = SelectionInfo(
            text="hello", owner_id=42, timestamp=time.time(),
        )

        app._on_mouse_release(_mouse_release_event())

        assert app._selection_valid is False

    def test_mouse_release_updates_baseline(self):
        """Baseline is always updated on release regardless of change."""
        app = _make_app()
        app._prev_sel_text = "old"
        app._prev_sel_owner_id = 1

        app.selection.get_selection.return_value = SelectionInfo(
            text="old", owner_id=1, timestamp=time.time(),
        )

        app._on_mouse_release(_mouse_release_event())

        assert app._prev_sel_text == "old"
        assert app._prev_sel_owner_id == 1

    def test_mouse_release_empty_primary(self):
        """Empty PRIMARY on release → baseline updated, NOT fresh."""
        app = _make_app()
        app._prev_sel_text = "old"
        app._prev_sel_owner_id = 1

        app.selection.get_selection.return_value = SelectionInfo(
            text="", owner_id=0, timestamp=time.time(),
        )

        app._on_mouse_release(_mouse_release_event())

        assert app._selection_valid is False
        assert app._prev_sel_text == ""

    def test_mouse_release_no_selection_adapter(self):
        """No crash when selection adapter is None."""
        app = _make_app()
        app.selection = None

        app._on_mouse_release(_mouse_release_event())  # should not crash

    def test_mouse_release_exception_no_crash(self):
        """Exception during get_selection → no crash, state unchanged."""
        app = _make_app()
        app.selection.get_selection.side_effect = RuntimeError("X11 error")

        app._on_mouse_release(_mouse_release_event())  # should not crash
        assert app._selection_valid is False

    def test_drag_select_click_then_release(self):
        """Full drag-select scenario: click resets fresh, release sets it back."""
        app = _make_app()
        app._prev_sel_text = ""
        app._prev_sel_owner_id = 0

        # Click at start of drag → resets sel_valid
        app._on_mouse_click(_mouse_event())
        assert app._selection_valid is False

        # Release at end of drag → new PRIMARY detected
        app.selection.get_selection.return_value = SelectionInfo(
            text="selected text", owner_id=1, timestamp=time.time(),
        )
        app._on_mouse_release(_mouse_release_event())

        assert app._selection_valid is True
        assert app._prev_sel_text == "selected text"

    def test_owner_change_detected(self):
        """Owner changed with same text → still fresh."""
        app = _make_app()
        app._prev_sel_text = "hello"
        app._prev_sel_owner_id = 42

        app.selection.get_selection.return_value = SelectionInfo(
            text="hello", owner_id=99, timestamp=time.time(),
        )

        app._on_mouse_release(_mouse_release_event())

        assert app._selection_valid is True


class TestPollerCallback:
    """Tests for _on_poller_primary_changed — sets fresh=True, does NOT update baseline."""

    def test_poller_callback_sets_fresh_true(self):
        app = _make_app()
        assert app._selection_valid is False

        app._on_poller_primary_changed("привет", 42)

        assert app._selection_valid is True

    def test_poller_callback_does_not_update_baseline(self):
        """Poller must NOT update _prev_sel_text / _prev_sel_owner_id.
        Baseline is only updated by _on_mouse_release and _do_conversion."""
        app = _make_app()
        app._prev_sel_text = "old"
        app._prev_sel_owner_id = 1

        app._on_poller_primary_changed("new", 42)

        # fresh is set, but baseline stays old
        assert app._selection_valid is True
        assert app._prev_sel_text == "old"
        assert app._prev_sel_owner_id == 1

    def test_poller_fresh_survives_until_click(self):
        """Poller sets fresh → it persists until mouse click resets it."""
        app = _make_app()
        app._on_poller_primary_changed("text", 1)
        assert app._selection_valid is True

        # Click resets
        app._on_mouse_click(_mouse_event())
        assert app._selection_valid is False


class TestSelectionValidOnEvents:
    def test_selection_valid_false_after_mouse_click(self):
        app = _make_app()
        app._selection_valid = True

        app._on_mouse_click(_mouse_event())

        assert app._selection_valid is False

    def test_mouse_click_does_not_read_primary(self):
        """_on_mouse_click must NOT call get_selection() — avoids race condition
        that can cause PRIMARY to be dropped in Cinnamon/GTK apps."""
        app = _make_app()

        app._on_mouse_click(_mouse_event())

        app.selection.get_selection.assert_not_called()

    def test_cross_window_stale_selection(self):
        """Cross-window scenario: select in Window A (poller sets fresh),
        click in Window B (resets fresh), Shift+Shift → NOT fresh."""
        app = _make_app()

        # Poller detected selection in Window A
        app._on_poller_primary_changed("hello", 99)
        assert app._selection_valid is True

        # Click in Window B resets fresh
        app._on_mouse_click(_mouse_event())
        assert app._selection_valid is False

        # Shift+Shift: fresh is False → retype/skip, not selection mode

    def test_drag_select_via_mouse_release(self):
        """Drag-select: click (resets) → release with new PRIMARY → fresh."""
        app = _make_app()

        app._on_mouse_click(_mouse_event())
        assert app._selection_valid is False

        app.selection.get_selection.return_value = SelectionInfo(
            text="new selection", owner_id=1, timestamp=time.time(),
        )
        app._on_mouse_release(_mouse_release_event())

        assert app._selection_valid is True
        assert app._prev_sel_text == "new selection"

    def test_selection_valid_false_after_navigation(self):
        app = _make_app()
        app._selection_valid = True

        # Arrow keys are navigation keys
        app._on_key_release(_key_release_event(KEY_UP))

        assert app._selection_valid is False

    def test_selection_valid_false_after_enter(self):
        app = _make_app()
        app._selection_valid = True

        app._on_key_release(_key_release_event(KEY_ENTER))

        assert app._selection_valid is False

    def test_selection_valid_false_after_key_press(self):
        app = _make_app()
        app._selection_valid = True

        app._on_key_press(_key_event(KEY_Q))

        assert app._selection_valid is False

    def test_selection_valid_false_after_space(self):
        app = _make_app()
        app._selection_valid = True

        app._on_key_press(_key_event(KEY_SPACE))

        assert app._selection_valid is False

    def test_selection_valid_false_after_backspace(self):
        app = _make_app()
        app._selection_valid = True

        app._on_key_press(_key_event(KEY_BACKSPACE))

        assert app._selection_valid is False

    def test_selection_valid_preserved_on_shift(self):
        """Shift press/release should NOT reset _selection_valid."""
        app = _make_app()
        app._selection_valid = True

        app._on_key_press(_key_event(KEY_LEFTSHIFT))

        assert app._selection_valid is True

    def test_modifier_keys_not_added_to_buffer(self):
        """Alt, Ctrl, Meta and other modifiers must not enter the event buffer."""
        KEY_LEFTALT = 56
        KEY_LEFTCTRL = 29
        KEY_LEFTMETA = 125
        KEY_F5 = 63
        KEY_DELETE = 111

        for code in (KEY_LEFTALT, KEY_LEFTCTRL, KEY_LEFTMETA, KEY_F5, KEY_DELETE):
            app = _make_app()
            app._on_key_press(_key_event(code))
            assert app.state_manager.context.chars_in_buffer == 0, \
                f"key code {code} should not be buffered"
            assert len(app.state_manager.context.event_buffer) == 0, \
                f"key code {code} should not appear in event_buffer"

    def test_regular_key_still_buffered(self):
        """Sanity check: regular letter keys ARE still added to the buffer."""
        app = _make_app()

        app._on_key_press(_key_event(KEY_Q))

        assert app.state_manager.context.chars_in_buffer == 1
        assert len(app.state_manager.context.event_buffer) == 1


class TestDoConversionUsesSelectionValid:
    def test_do_conversion_uses_selection_valid(self):
        app = _make_app()
        app._selection_valid = True

        # Put state machine into CONVERTING
        app.state_manager.context.state = State.CONVERTING
        app.state_manager._state = State.CONVERTING

        # Mock convert to track arguments
        original_convert = app.conversion_engine.convert
        convert_calls = []

        def mock_convert(ctx, selection_valid=False):
            convert_calls.append(selection_valid)
            return True

        app.conversion_engine.convert = mock_convert

        app._do_conversion()

        # selection_valid should have been True when convert was called
        assert len(convert_calls) == 1
        assert convert_calls[0] is True
        # After conversion, _selection_valid should be consumed (False)
        assert app._selection_valid is False

    def test_do_conversion_resets_selection_valid_even_on_failure(self):
        app = _make_app()
        app._selection_valid = True

        # Put state machine into CONVERTING
        app.state_manager.context.state = State.CONVERTING
        app.state_manager._state = State.CONVERTING

        # Mock convert to raise
        def mock_convert(ctx, selection_valid=False):
            raise RuntimeError("conversion failed")

        app.conversion_engine.convert = mock_convert

        # Exception propagates but _selection_valid is reset in finally
        with pytest.raises(RuntimeError):
            app._do_conversion()

        assert app._selection_valid is False

    def test_do_conversion_updates_baseline_after_convert(self):
        """After conversion, baseline is updated to current PRIMARY
        to prevent re-conversion of the same text."""
        app = _make_app()
        app._selection_valid = True

        app.state_manager.context.state = State.CONVERTING
        app.state_manager._state = State.CONVERTING

        # PRIMARY will return new text after conversion
        app.selection.get_selection.return_value = SelectionInfo(
            text="конвертированный", owner_id=1, timestamp=time.time(),
        )

        def mock_convert(ctx, selection_valid=False):
            return True

        app.conversion_engine.convert = mock_convert
        app._do_conversion()

        assert app._prev_sel_text == "конвертированный"
        assert app._prev_sel_owner_id == 1
        assert app._selection_valid is False

    def test_do_conversion_no_selection_change_stays_false(self):
        """If PRIMARY hasn't changed, _selection_valid stays False."""
        app = _make_app()
        assert app._selection_valid is False

        # Empty PRIMARY
        app.selection.get_selection.return_value = SelectionInfo(
            text="", owner_id=0, timestamp=0.0,
        )

        # Put state machine into CONVERTING
        app.state_manager.context.state = State.CONVERTING
        app.state_manager._state = State.CONVERTING

        convert_calls = []

        def mock_convert(ctx, selection_valid=False):
            convert_calls.append(selection_valid)
            return True

        app.conversion_engine.convert = mock_convert

        app._do_conversion()

        assert len(convert_calls) == 1
        assert convert_calls[0] is False


class TestStickyRetypeBuffer:
    """Test sticky buffer: repeat Shift+Shift toggles retype conversion."""

    def test_sticky_buffer_saved_after_retype(self):
        """After successful retype, _last_retype_events is populated."""
        app = _make_app()

        # Fill buffer with "hello" keycodes
        ctx = app.state_manager.context
        for code in [35, 18, 38, 38, 24]:
            ev = MagicMock()
            ev.code = code
            ev.shifted = False
            ctx.event_buffer.append(ev)
        ctx.chars_in_buffer = 5

        app.state_manager.context.state = State.CONVERTING
        app.state_manager._state = State.CONVERTING

        def mock_convert(context, selection_valid=False):
            return True

        app.conversion_engine.convert = mock_convert
        app._do_conversion()

        assert len(app._last_retype_events) == 5
        assert [e.code for e in app._last_retype_events] == [35, 18, 38, 38, 24]

    def test_sticky_buffer_restores_on_empty_buffer(self):
        """When buffer is empty but sticky has events, they are restored."""
        app = _make_app()

        # Simulate saved sticky buffer from previous conversion
        saved = []
        for code in [35, 18, 38, 38, 24]:
            ev = MagicMock()
            ev.code = code
            ev.shifted = False
            saved.append(ev)
        app._last_retype_events = saved

        # Buffer is empty (reset by previous conversion)
        ctx = app.state_manager.context
        ctx.chars_in_buffer = 0
        ctx.event_buffer = []

        app.state_manager.context.state = State.CONVERTING
        app.state_manager._state = State.CONVERTING

        convert_calls = []

        def mock_convert(context, selection_valid=False):
            # At this point context should have restored events
            convert_calls.append(context.chars_in_buffer)
            return True

        app.conversion_engine.convert = mock_convert
        app._do_conversion()

        # convert should have been called with 5 chars
        assert len(convert_calls) == 1
        assert convert_calls[0] == 5
        # sticky buffer should still be populated for next repeat
        assert len(app._last_retype_events) == 5

    def test_sticky_cleared_on_regular_key(self):
        app = _make_app()
        app._last_retype_events = [MagicMock()]

        app._on_key_press(_key_event(KEY_Q))

        assert app._last_retype_events == []

    def test_sticky_cleared_on_space(self):
        app = _make_app()
        app._last_retype_events = [MagicMock()]

        app._on_key_press(_key_event(KEY_SPACE))

        assert app._last_retype_events == []

    def test_sticky_cleared_on_backspace(self):
        app = _make_app()
        app._last_retype_events = [MagicMock()]

        app._on_key_press(_key_event(KEY_BACKSPACE))

        assert app._last_retype_events == []

    def test_sticky_cleared_on_navigation(self):
        app = _make_app()
        app._last_retype_events = [MagicMock()]

        app._on_key_release(_key_release_event(KEY_LEFT))

        assert app._last_retype_events == []

    def test_sticky_cleared_on_enter(self):
        app = _make_app()
        app._last_retype_events = [MagicMock()]

        app._on_key_release(_key_release_event(KEY_ENTER))

        assert app._last_retype_events == []

    def test_sticky_cleared_on_mouse_click(self):
        app = _make_app()
        app._last_retype_events = [MagicMock()]

        app._on_mouse_click(_mouse_event())

        assert app._last_retype_events == []

    def test_sticky_preserved_on_shift(self):
        """Shift must NOT clear sticky buffer — it's needed for Shift+Shift."""
        app = _make_app()
        app._last_retype_events = [MagicMock()]

        app._on_key_press(_key_event(KEY_LEFTSHIFT))

        assert len(app._last_retype_events) == 1

    def test_sticky_preserved_on_modifier(self):
        """Modifier keys (Alt etc) must NOT clear sticky buffer."""
        KEY_LEFTALT = 56
        app = _make_app()
        app._last_retype_events = [MagicMock()]

        app._on_key_press(_key_event(KEY_LEFTALT))

        assert len(app._last_retype_events) == 1

    def test_sticky_not_saved_for_selection_mode(self):
        """Selection conversion should NOT populate sticky buffer."""
        app = _make_app()
        app._selection_valid = True

        ctx = app.state_manager.context
        ctx.chars_in_buffer = 0
        ctx.event_buffer = []

        app.state_manager.context.state = State.CONVERTING
        app.state_manager._state = State.CONVERTING

        def mock_convert(context, selection_valid=False):
            return True

        app.conversion_engine.convert = mock_convert
        app._do_conversion()

        assert app._last_retype_events == []