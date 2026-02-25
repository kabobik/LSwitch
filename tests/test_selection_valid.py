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


class TestCheckSelectionChanged:
    def test_check_selection_changed_sets_valid_true(self):
        app = _make_app()
        app.selection.get_selection.return_value = SelectionInfo(
            text="hello", owner_id=42, timestamp=time.time(),
        )

        result = app._check_selection_changed()

        assert result is True
        assert app._selection_valid is True
        assert app._prev_sel_text == "hello"
        assert app._prev_sel_owner_id == 42

    def test_check_selection_changed_no_change(self):
        app = _make_app()
        # First call sets state
        app.selection.get_selection.return_value = SelectionInfo(
            text="hello", owner_id=42, timestamp=time.time(),
        )
        app._check_selection_changed()

        # Reset _selection_valid (as if consumed)
        app._selection_valid = False

        # Same text and owner — no change
        result = app._check_selection_changed()
        assert result is False
        assert app._selection_valid is False

    def test_check_selection_changed_text_changed(self):
        app = _make_app()
        # Set initial state
        app._prev_sel_text = "hello"
        app._prev_sel_owner_id = 42

        # Different text, same owner
        app.selection.get_selection.return_value = SelectionInfo(
            text="world", owner_id=42, timestamp=time.time(),
        )

        result = app._check_selection_changed()
        assert result is True
        assert app._selection_valid is True

    def test_check_selection_changed_owner_changed(self):
        app = _make_app()
        # Set initial state
        app._prev_sel_text = "hello"
        app._prev_sel_owner_id = 42

        # Same text, different owner
        app.selection.get_selection.return_value = SelectionInfo(
            text="hello", owner_id=99, timestamp=time.time(),
        )

        result = app._check_selection_changed()
        assert result is True
        assert app._selection_valid is True

    def test_check_selection_changed_empty_text_returns_false(self):
        app = _make_app()
        app.selection.get_selection.return_value = SelectionInfo(
            text="", owner_id=42, timestamp=time.time(),
        )

        result = app._check_selection_changed()
        assert result is False
        assert app._selection_valid is False

    def test_check_selection_changed_no_selection_adapter(self):
        app = _make_app()
        app.selection = None

        result = app._check_selection_changed()
        assert result is False

    def test_check_selection_changed_exception_returns_false(self):
        app = _make_app()
        app.selection.get_selection.side_effect = RuntimeError("X11 error")

        result = app._check_selection_changed()
        assert result is False
        assert app._selection_valid is False


class TestSelectionValidOnEvents:
    def test_selection_valid_false_after_mouse_click(self):
        app = _make_app()
        app._selection_valid = True

        app._on_mouse_click(_mouse_event())

        assert app._selection_valid is False

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

    def test_do_conversion_checks_selection_before_convert(self):
        """_check_selection_changed() is called before convert(), so if
        PRIMARY changed since last action, _selection_valid becomes True."""
        app = _make_app()
        assert app._selection_valid is False

        # Simulate PRIMARY having new content
        app.selection.get_selection.return_value = SelectionInfo(
            text="ghbdtn", owner_id=1, timestamp=time.time(),
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

        # _check_selection_changed should have set _selection_valid=True
        # before convert was called
        assert len(convert_calls) == 1
        assert convert_calls[0] is True

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
