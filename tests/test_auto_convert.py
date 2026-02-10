"""Tests for auto-conversion (check_and_auto_convert).

Bug fix: auto-conversion now uses the same reliable mechanism as manual
conversion (backspace + switch layout + replay events) instead of the
unreliable xdotool ctrl+shift+Left + Delete approach.
"""
import time
import types
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest
from evdev import ecodes

from lswitch.core import LSwitch


class DummyUInput:
    """Captures all writes for inspection."""
    def __init__(self, *args, **kwargs):
        self.writes = []

    def write(self, ev_type, code, value):
        self.writes.append((ev_type, code, value))

    def syn(self):
        pass

    def close(self):
        pass


def make_ls(monkeypatch, auto_switch=True, debug=False):
    """Create an LSwitch instance configured for auto-conversion testing."""
    monkeypatch.setattr('threading.Thread.start', lambda self: None)
    monkeypatch.setattr('evdev.UInput', DummyUInput)

    ls = LSwitch(config_path='config.json')
    ls.config['auto_switch'] = auto_switch
    ls.config['debug'] = debug
    ls.config['switch_layout_after_convert'] = True
    ls.auto_switch_enabled = auto_switch
    ls.user_dict = None  # Simplify: no user dict
    return ls


CHAR_TO_KEY = {
    'a': ecodes.KEY_A, 'b': ecodes.KEY_B, 'c': ecodes.KEY_C, 'd': ecodes.KEY_D,
    'e': ecodes.KEY_E, 'f': ecodes.KEY_F, 'g': ecodes.KEY_G, 'h': ecodes.KEY_H,
    'i': ecodes.KEY_I, 'j': ecodes.KEY_J, 'k': ecodes.KEY_K, 'l': ecodes.KEY_L,
    'm': ecodes.KEY_M, 'n': ecodes.KEY_N, 'o': ecodes.KEY_O, 'p': ecodes.KEY_P,
    'q': ecodes.KEY_Q, 'r': ecodes.KEY_R, 's': ecodes.KEY_S, 't': ecodes.KEY_T,
    'u': ecodes.KEY_U, 'v': ecodes.KEY_V, 'w': ecodes.KEY_W, 'x': ecodes.KEY_X,
    'y': ecodes.KEY_Y, 'z': ecodes.KEY_Z,
}


def simulate_typing(ls, text):
    """Simulate typing a word into the buffer (key-down + key-up events)."""
    for ch in text:
        code = CHAR_TO_KEY.get(ch.lower())
        if code is None:
            continue
        ev_down = SimpleNamespace(type=ecodes.EV_KEY, code=code, value=1)
        ev_up = SimpleNamespace(type=ecodes.EV_KEY, code=code, value=0)
        ls.handle_event(ev_down)
        ls.handle_event(ev_up)


def simulate_space(ls):
    """Simulate pressing space — triggers check_and_auto_convert internally."""
    ev_down = SimpleNamespace(type=ecodes.EV_KEY, code=ecodes.KEY_SPACE, value=1)
    ev_up = SimpleNamespace(type=ecodes.EV_KEY, code=ecodes.KEY_SPACE, value=0)
    ls.handle_event(ev_down)
    ls.handle_event(ev_up)


# ── Test: auto-convert disabled does nothing ─────────────────
def test_auto_convert_disabled_does_nothing(monkeypatch):
    """When auto_switch is False, check_and_auto_convert must be a no-op."""
    ls = make_ls(monkeypatch, auto_switch=False)
    simulate_typing(ls, 'ghbdtn')
    original = list(ls.text_buffer)
    original_count = ls.chars_in_buffer

    ls.check_and_auto_convert()

    assert ls.text_buffer == original
    assert ls.chars_in_buffer == original_count


def test_auto_convert_empty_buffer(monkeypatch):
    """Auto-convert with empty buffer must not crash."""
    ls = make_ls(monkeypatch)
    assert ls.chars_in_buffer == 0
    ls.check_and_auto_convert()  # Must not raise


def test_auto_convert_sets_marker_when_converting(monkeypatch):
    """When ngrams says to convert, last_auto_convert marker must be set
    so the user can undo it with manual double-Shift."""
    ls = make_ls(monkeypatch)
    simulate_typing(ls, 'ghbdtn')

    # Explicitly set text_buffer to English chars (simulates English layout active)
    ls.text_buffer = list('ghbdtn')

    # Mock should_convert to force conversion
    with patch('lswitch.ngrams.should_convert', return_value=(True, 'привет', 'test')):
        # Mock convert_and_retype to avoid side effects
        with patch.object(ls, 'convert_and_retype') as mock_convert:
            ls.check_and_auto_convert()

            # Verify marker was set
            assert ls.last_auto_convert is not None
            assert 'word' in ls.last_auto_convert
            assert 'converted_to' in ls.last_auto_convert
            assert 'time' in ls.last_auto_convert
            assert ls.last_auto_convert['converted_to'] == 'привет'

            # Verify convert_and_retype was called with is_auto=True
            mock_convert.assert_called_once_with(is_auto=True)


def test_auto_convert_uses_convert_and_retype(monkeypatch):
    """Auto-convert must delegate to convert_and_retype(is_auto=True)
    instead of using unreliable xdotool selection."""
    ls = make_ls(monkeypatch)
    simulate_typing(ls, 'ghbdtn')
    ls.text_buffer = list('ghbdtn')  # Simulate English layout

    with patch('lswitch.ngrams.should_convert', return_value=(True, 'привет', 'test')):
        with patch.object(ls, 'convert_and_retype') as mock_convert:
            ls.check_and_auto_convert()
            mock_convert.assert_called_once_with(is_auto=True)


def test_auto_convert_no_xdotool_select(monkeypatch):
    """Auto-convert must NOT use xdotool ctrl+shift+Left to select text."""
    ls = make_ls(monkeypatch)
    simulate_typing(ls, 'ghbdtn')
    ls.text_buffer = list('ghbdtn')  # Simulate English layout

    # Track all system calls
    system_calls = []
    original_system = ls.system
    if original_system and hasattr(original_system, 'xdotool_key'):
        orig_xdotool = original_system.xdotool_key
        def tracking_xdotool(key, **kwargs):
            system_calls.append(('xdotool_key', key))
            return orig_xdotool(key, **kwargs)
        original_system.xdotool_key = tracking_xdotool

    with patch('lswitch.ngrams.should_convert', return_value=(True, 'привет', 'test')):
        with patch.object(ls, 'convert_and_retype'):
            ls.check_and_auto_convert()

    # Verify no ctrl+shift+Left calls
    for call_type, arg in system_calls:
        assert 'ctrl+shift+Left' not in str(arg), \
            "Auto-convert must not use ctrl+shift+Left (unreliable)"


def test_auto_convert_skips_valid_word(monkeypatch):
    """If the word is valid in current language, no conversion should happen."""
    ls = make_ls(monkeypatch)
    simulate_typing(ls, 'ghbdtn')

    with patch('lswitch.ngrams.should_convert', return_value=(False, 'ghbdtn', 'found_in_dict')):
        with patch.object(ls, 'convert_and_retype') as mock_convert:
            ls.check_and_auto_convert()
            # convert_and_retype must NOT be called
            mock_convert.assert_not_called()


def test_auto_convert_skips_same_text(monkeypatch):
    """If best_text equals the original, no conversion should happen."""
    ls = make_ls(monkeypatch)
    simulate_typing(ls, 'hello')
    word = ''.join(ls.text_buffer)

    with patch('lswitch.ngrams.should_convert', return_value=(True, word, 'same')):
        with patch.object(ls, 'convert_and_retype') as mock_convert:
            ls.check_and_auto_convert()
            mock_convert.assert_not_called()


def test_text_buffer_populated_correctly(monkeypatch):
    """text_buffer must be populated with characters after typing."""
    ls = make_ls(monkeypatch)
    simulate_typing(ls, 'ghbdtn')

    assert ls.chars_in_buffer == 6
    assert len(ls.text_buffer) == 6
    # The actual chars depend on current XKB layout, but buffer must not be empty
    text = ''.join(ls.text_buffer)
    assert len(text) == 6


def test_fallback_type_text_cyrillic(monkeypatch):
    """_fallback_type_text must correctly map Cyrillic characters via RU_TO_EN."""
    ls = make_ls(monkeypatch)
    fake_kb = ls.fake_kb
    initial_writes = len(fake_kb.writes)

    ls._fallback_type_text('привет')

    # Should have written KEY events for each character (down+up = 2 per char + syn)
    new_writes = fake_kb.writes[initial_writes:]
    # Filter for EV_KEY writes (type=1)
    key_writes = [w for w in new_writes if w[0] == ecodes.EV_KEY]
    # Each char produces 2 events (down=1, up=0), so 6 chars → 12 events
    assert len(key_writes) >= 12, \
        f"Expected at least 12 key events for 'привет', got {len(key_writes)}"
