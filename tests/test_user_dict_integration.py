"""Integration tests: UserDictionary ↔ AutoDetector ↔ app.py correction/confirmation loop."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from lswitch.app import LSwitchApp
from lswitch.core.events import Event, EventType, KeyEventData
from lswitch.core.states import State
from lswitch.intelligence.auto_detector import AutoDetector
from lswitch.intelligence.user_dictionary import UserDictionary
from lswitch.platform.xkb_adapter import LayoutInfo

from tests.conftest import MockXKBAdapter, MockSelectionAdapter, MockSystemAdapter

# ---------------------------------------------------------------------------
# Key constants (evdev keycodes)
# ---------------------------------------------------------------------------
KEY_G = 34
KEY_H = 35
KEY_B = 48
KEY_D = 32
KEY_T = 20
KEY_N = 49
KEY_A = 30
KEY_SPACE = 57
KEY_BACKSPACE = 14
KEY_LEFTSHIFT = 42
KEY_RIGHTSHIFT = 54

WORD_GHBDTN = [KEY_G, KEY_H, KEY_B, KEY_D, KEY_T, KEY_N]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _event(code: int, value: int = 1) -> Event:
    data = KeyEventData(code=code, value=value, device_name="test")
    return Event(type=EventType.KEY_PRESS, data=data, timestamp=time.time())


def _release(code: int) -> Event:
    data = KeyEventData(code=code, value=0, device_name="test")
    return Event(type=EventType.KEY_RELEASE, data=data, timestamp=time.time())


class _MockAutoDetector:
    """Stub that always says convert."""

    def __init__(self, should: bool = True, reason: str = "test"):
        self._should = should
        self._reason = reason

    def should_convert(self, word: str, current_layout: str) -> tuple[bool, str]:
        return self._should, self._reason


def _make_app(auto_switch: bool = True, user_dict_enabled: bool = False,
              threshold: int = 0) -> LSwitchApp:
    app = LSwitchApp(headless=True, debug=True)
    app.xkb = MockXKBAdapter(layouts=["en", "ru"])
    app.selection = MockSelectionAdapter()
    app.system = MockSystemAdapter()
    app.virtual_kb = MagicMock()
    app.conversion_engine = MagicMock()
    app.event_manager = MagicMock()
    app.device_manager = MagicMock()
    app.config._config['auto_switch'] = auto_switch
    app.config._config['auto_switch_threshold'] = threshold
    app.config._config['user_dict_enabled'] = user_dict_enabled
    return app


def _fill_buffer(app: LSwitchApp, keycodes: list[int]) -> None:
    for code in keycodes:
        ev = _event(code)
        app.state_manager.context.event_buffer.append(ev.data)
        app.state_manager.context.chars_in_buffer += 1
    app.state_manager.context.state = State.TYPING


def _make_user_dict_in_memory() -> UserDictionary:
    """Create an in-memory UserDictionary (no disk I/O)."""
    ud = UserDictionary.__new__(UserDictionary)
    ud.path = ":memory:"
    ud.data = {"words": {}, "settings": dict(UserDictionary.DEFAULT_SETTINGS)}
    ud.flush = MagicMock()  # suppress file writes
    return ud


def _do_double_shift(app: LSwitchApp):
    """Simulate a quick double-Shift via the state manager."""
    app.state_manager.on_shift_down()
    is_double = app.state_manager.on_shift_up()
    if not is_double:
        time.sleep(0.01)
        app.state_manager.on_shift_down()
        is_double = app.state_manager.on_shift_up()
    return is_double


# ===========================================================================
# Tests
# ===========================================================================


class TestAutoConversionSavesMarker:
    """After auto-conversion at space, _last_auto_marker is set."""

    def test_marker_saved_after_auto_conversion(self):
        app = _make_app(auto_switch=True)
        app.auto_detector = _MockAutoDetector(should=True)
        app._wire_event_bus()

        _fill_buffer(app, WORD_GHBDTN)
        app._on_key_press(_event(KEY_SPACE))

        assert app._last_auto_marker is not None
        assert app._last_auto_marker['word'] == 'ghbdtn'
        assert app._last_auto_marker['lang'] == 'en'
        assert app._last_auto_marker['direction'] == 'en_to_ru'
        assert 'time' in app._last_auto_marker

    def test_marker_none_when_no_conversion(self):
        app = _make_app(auto_switch=True)
        app.auto_detector = _MockAutoDetector(should=False)
        app._wire_event_bus()

        _fill_buffer(app, WORD_GHBDTN)
        app._on_key_press(_event(KEY_SPACE))

        assert app._last_auto_marker is None


class TestDoubleShiftAfterAutoCallsCorrection:
    """Double-Shift after auto-conversion calls user_dict.add_correction."""

    def test_correction_called(self):
        app = _make_app(auto_switch=True)
        ud = _make_user_dict_in_memory()
        app.user_dict = ud
        app.auto_detector = _MockAutoDetector(should=True)
        app._wire_event_bus()

        # Trigger auto-conversion
        _fill_buffer(app, WORD_GHBDTN)
        app._on_key_press(_event(KEY_SPACE))
        assert app._last_auto_marker is not None

        # Now simulate double-Shift (manual undo)
        # Set state to CONVERTING so _do_conversion proceeds
        app.state_manager.context.state = State.CONVERTING
        app.state_manager._state = State.CONVERTING
        app._do_conversion()

        # Correction should have been called
        assert ud.get_weight('ghbdtn', 'en') == -1
        # Marker cleared
        assert app._last_auto_marker is None

    def test_correction_fires_after_long_delay(self):
        """Marker fires even if user returns after a long time (no TTL)."""
        app = _make_app(auto_switch=True)
        ud = _make_user_dict_in_memory()
        app.user_dict = ud
        app.auto_detector = _MockAutoDetector(should=True)
        app._wire_event_bus()

        _fill_buffer(app, WORD_GHBDTN)
        app._on_key_press(_event(KEY_SPACE))

        # Simulate user returning after a very long time
        app._last_auto_marker['time'] -= 3600.0

        app.state_manager.context.state = State.CONVERTING
        app.state_manager._state = State.CONVERTING
        app._do_conversion()

        # Correction must still fire — no timeout
        assert ud.get_weight('ghbdtn', 'en') == -1
        assert app._last_auto_marker is None

    def test_no_correction_when_no_user_dict(self):
        """user_dict is None → marker is cleared but no crash."""
        app = _make_app(auto_switch=True)
        app.user_dict = None
        app.auto_detector = _MockAutoDetector(should=True)
        app._wire_event_bus()

        _fill_buffer(app, WORD_GHBDTN)
        app._on_key_press(_event(KEY_SPACE))

        app.state_manager.context.state = State.CONVERTING
        app.state_manager._state = State.CONVERTING
        app._do_conversion()

        assert app._last_auto_marker is None


class TestCorrectionSetsProtection:
    """add_correction sets protected_until so word is temporarily protected."""

    def test_protected_until_set(self):
        ud = _make_user_dict_in_memory()
        ud.add_correction('ghbdtn', 'en')

        key = ud._key('ghbdtn', 'en')
        entry = ud.data['words'][key]
        assert 'protected_until' in entry
        assert entry['protected_until'] > time.time()
        assert entry['weight'] == -1

    def test_is_protected_returns_true_after_correction(self):
        ud = _make_user_dict_in_memory()
        ud.add_correction('ghbdtn', 'en')

        assert ud.is_protected('ghbdtn', 'en') is True

    def test_protection_expires(self):
        ud = _make_user_dict_in_memory()
        ud.add_correction('ghbdtn', 'en')

        # Simulate time passing
        key = ud._key('ghbdtn', 'en')
        ud.data['words'][key]['protected_until'] = time.time() - 1.0

        assert ud.is_protected('ghbdtn', 'en') is False


class TestProtectedWordNotConverted:
    """AutoDetector returns False for protected words."""

    def test_protected_word_blocked(self):
        ud = _make_user_dict_in_memory()
        ud.add_correction('ghbdtn', 'en')  # sets protection

        dict_svc = MagicMock()
        dict_svc.should_convert.return_value = (True, "converted found in target dict")
        ngrams = MagicMock()

        detector = AutoDetector(dictionary=dict_svc, ngrams=ngrams, user_dict=ud)
        should, reason = detector.should_convert('ghbdtn', 'en')

        assert should is False
        assert 'protected' in reason

    def test_unprotected_word_passes_through(self):
        ud = _make_user_dict_in_memory()
        # No correction — not protected

        dict_svc = MagicMock()
        dict_svc.should_convert.return_value = (True, "converted found in target dict")
        ngrams = MagicMock()

        detector = AutoDetector(dictionary=dict_svc, ngrams=ngrams, user_dict=ud)
        should, reason = detector.should_convert('ghbdtn', 'en')

        assert should is True


class TestNegativeWeightBlocksConversion:
    """When weight <= -min_weight, AutoDetector blocks conversion."""

    def test_weight_below_threshold_blocks(self):
        ud = _make_user_dict_in_memory()
        # Apply 2 corrections (min_weight default = 2)
        ud.add_correction('ghbdtn', 'en')
        ud.add_correction('ghbdtn', 'en')
        # Expire protection to test weight-only logic
        key = ud._key('ghbdtn', 'en')
        ud.data['words'][key]['protected_until'] = 0

        dict_svc = MagicMock()
        dict_svc.should_convert.return_value = (True, "converted found in target dict")
        ngrams = MagicMock()

        detector = AutoDetector(dictionary=dict_svc, ngrams=ngrams, user_dict=ud)
        should, reason = detector.should_convert('ghbdtn', 'en')

        assert should is False
        assert 'weight' in reason

    def test_weight_above_threshold_allows(self):
        ud = _make_user_dict_in_memory()
        # Only 1 correction (weight = -1, threshold = 2) → still allows
        ud.add_correction('ghbdtn', 'en')
        key = ud._key('ghbdtn', 'en')
        ud.data['words'][key]['protected_until'] = 0  # expire protection

        dict_svc = MagicMock()
        dict_svc.should_convert.return_value = (True, "converted found in target dict")
        ngrams = MagicMock()

        detector = AutoDetector(dictionary=dict_svc, ngrams=ngrams, user_dict=ud)
        should, reason = detector.should_convert('ghbdtn', 'en')

        assert should is True


class TestContinuedTypingConfirmsPrevious:
    """Typing another word (space) without double-Shift confirms previous conversion."""

    def test_confirmation_called_on_next_space(self):
        app = _make_app(auto_switch=True)
        ud = _make_user_dict_in_memory()
        app.user_dict = ud
        app.auto_detector = _MockAutoDetector(should=True)
        app._wire_event_bus()

        # First word: triggers auto-conversion, sets marker
        _fill_buffer(app, WORD_GHBDTN)
        app._on_key_press(_event(KEY_SPACE))
        assert app._last_auto_marker is not None
        old_marker = app._last_auto_marker.copy()

        # Second word: another auto-conversion → previous should be confirmed
        _fill_buffer(app, [KEY_A, KEY_B, KEY_D])
        app._on_key_press(_event(KEY_SPACE))

        # Old word was confirmed (+1)
        assert ud.get_weight(old_marker['word'], old_marker['lang']) == 1

    def test_no_confirmation_without_user_dict(self):
        """user_dict=None → no crash, no confirmation."""
        app = _make_app(auto_switch=True)
        app.user_dict = None
        app.auto_detector = _MockAutoDetector(should=True)
        app._wire_event_bus()

        _fill_buffer(app, WORD_GHBDTN)
        app._on_key_press(_event(KEY_SPACE))

        _fill_buffer(app, [KEY_A, KEY_B, KEY_D])
        app._on_key_press(_event(KEY_SPACE))
        # No exception raised — test passes


class TestUserDictDisabledNoEffect:
    """When user_dict_enabled=False, no UserDictionary logic is involved."""

    def test_app_user_dict_none_by_default(self):
        app = _make_app(auto_switch=True, user_dict_enabled=False)
        assert app.user_dict is None

    def test_auto_detector_works_without_user_dict(self):
        dict_svc = MagicMock()
        dict_svc.should_convert.return_value = (True, "converted found in target dict")
        ngrams = MagicMock()

        detector = AutoDetector(dictionary=dict_svc, ngrams=ngrams, user_dict=None)
        should, reason = detector.should_convert('ghbdtn', 'en')
        assert should is True

    def test_marker_still_saved_even_without_user_dict(self):
        """Marker is saved regardless — it's just not used for correction."""
        app = _make_app(auto_switch=True, user_dict_enabled=False)
        app.user_dict = None
        app.auto_detector = _MockAutoDetector(should=True)
        app._wire_event_bus()

        _fill_buffer(app, WORD_GHBDTN)
        app._on_key_press(_event(KEY_SPACE))

        assert app._last_auto_marker is not None

    def test_double_shift_clears_marker_without_crash(self):
        """Double-shift with no user_dict → marker cleared, no error."""
        app = _make_app(auto_switch=True, user_dict_enabled=False)
        app.user_dict = None
        app.auto_detector = _MockAutoDetector(should=True)
        app._wire_event_bus()

        _fill_buffer(app, WORD_GHBDTN)
        app._on_key_press(_event(KEY_SPACE))

        app.state_manager.context.state = State.CONVERTING
        app.state_manager._state = State.CONVERTING
        app._do_conversion()

        assert app._last_auto_marker is None
