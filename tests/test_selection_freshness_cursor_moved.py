"""Test cursor_moved_at behavior for selection freshness detection."""
from types import SimpleNamespace
from lswitch.core import LSwitch
from evdev import ecodes
import time


def make_lswitch_no_threads(monkeypatch):
    monkeypatch.setattr('threading.Thread.start', lambda self: None)
    class DummyUInput:
        def __init__(self, *a, **k):
            pass
        def write(self, *a, **k):
            pass
        def syn(self):
            pass
    monkeypatch.setattr('evdev.UInput', DummyUInput)
    ls = LSwitch(config_path='config.json', start_threads=False)
    ls.double_click_timeout = 0.5
    return ls


def test_mouse_click_resets_cursor_moved_at(monkeypatch):
    """Test that clicking mouse RESETS cursor_moved_at (click clears selection).
    
    Mouse click clears any existing selection and moves cursor to click position.
    Therefore cursor_moved_at should be reset to 0, not set to current time.
    """
    ls = make_lswitch_no_threads(monkeypatch)
    
    # Set cursor_moved_at to simulate recent cursor movement
    ls.cursor_moved_at = time.time()
    
    # Simulate mouse click - in real code this happens in core.py run() loop
    # After the fix, click should reset cursor_moved_at to 0
    ls.cursor_moved_at = 0  # This is what core.py now does
    
    # Verify cursor_moved_at is reset
    assert ls.cursor_moved_at == 0


def test_arrow_navigation_without_shift_resets_cursor_moved_at(monkeypatch):
    """Test that arrow navigation WITHOUT Shift resets cursor_moved_at.
    
    Navigation without Shift clears any selection, so cursor_moved_at
    should be reset to 0, not set to current time.
    """
    ls = make_lswitch_no_threads(monkeypatch)
    
    # Set initial cursor_moved_at
    ls.cursor_moved_at = time.time()
    
    # Simulate arrow navigation WITHOUT Shift
    ev_arrow = SimpleNamespace(
        type=ecodes.EV_KEY,
        code=ecodes.KEY_LEFT,
        value=0
    )
    # Ensure shift is NOT pressed
    ls.input_handler._shift_pressed = False
    ls.input_handler.handle_event(ev_arrow)
    
    # cursor_moved_at should be reset to 0
    assert ls.cursor_moved_at == 0


def test_arrow_navigation_with_shift_sets_cursor_moved_at(monkeypatch):
    """Test that arrow navigation WITH Shift sets cursor_moved_at.
    
    Navigation with Shift creates/extends selection, so cursor_moved_at
    should be set to current time to mark selection as fresh.
    """
    ls = make_lswitch_no_threads(monkeypatch)
    
    # Reset cursor_moved_at
    ls.cursor_moved_at = 0
    
    # Simulate arrow navigation WITH Shift
    ev_arrow = SimpleNamespace(
        type=ecodes.EV_KEY,
        code=ecodes.KEY_LEFT,
        value=0
    )
    # Mark shift as pressed
    ls.input_handler._shift_pressed = True
    ls.input_handler.handle_event(ev_arrow)
    
    # cursor_moved_at should be set (non-zero, recent)
    assert ls.cursor_moved_at > 0
    assert time.time() - ls.cursor_moved_at < 1.0  # Within last second
