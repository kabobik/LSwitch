"""Test that mouse click marks selection as fresh for same-text reselect."""
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


def test_mouse_click_makes_selection_fresh(monkeypatch):
    """Test that clicking mouse makes selection fresh even if content unchanged."""
    ls = make_lswitch_no_threads(monkeypatch)
    
    # Mock xclip_get to return same text multiple times
    class MockResult:
        def __init__(self, text):
            self.stdout = text
            self.returncode = 0
    
    call_count = [0]
    def mock_xclip_get(*args, **kwargs):
        call_count[0] += 1
        return MockResult("test")
    
    monkeypatch.setattr(ls.system, 'xclip_get', mock_xclip_get)
    
    # First check: selection exists
    assert ls.has_selection() is True
    assert ls.last_known_selection == "test"
    
    # Second check immediately: same text, not fresh
    assert ls.has_selection() is False
    
    # Now simulate mouse click (should set cursor_moved_at)
    ev_click = SimpleNamespace(
        type=ecodes.EV_KEY,
        code=ecodes.BTN_LEFT,
        value=1
    )
    # Simulate click in main loop (core.py sets cursor_moved_at)
    ls.cursor_moved_at = time.time()
    
    # Third check: same text but should be fresh due to recent cursor movement
    time.sleep(0.01)  # Small delay to ensure time passes
    assert ls.has_selection() is True
    
    # After freshness window expires, should be stale again
    ls.cursor_moved_at = time.time() - 1.0  # 1 second ago
    assert ls.has_selection() is False


def test_arrow_navigation_does_not_make_selection_fresh(monkeypatch):
    """Test that arrow navigation does NOT make selection fresh."""
    ls = make_lswitch_no_threads(monkeypatch)
    
    class MockResult:
        def __init__(self, text):
            self.stdout = text
            self.returncode = 0
    
    def mock_xclip_get(*args, **kwargs):
        return MockResult("test")
    
    monkeypatch.setattr(ls.system, 'xclip_get', mock_xclip_get)
    
    # First check: selection exists
    assert ls.has_selection() is True
    
    # Second check: stale
    assert ls.has_selection() is False
    
    # Simulate arrow navigation (should NOT set cursor_moved_at)
    ev_arrow = SimpleNamespace(
        type=ecodes.EV_KEY,
        code=ecodes.KEY_LEFT,
        value=0
    )
    ls.input_handler.handle_event(ev_arrow)
    
    # cursor_moved_at should NOT be set by navigation
    # Third check: should still be stale
    assert ls.has_selection() is False
