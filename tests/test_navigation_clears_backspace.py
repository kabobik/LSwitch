from types import SimpleNamespace
from lswitch.core import LSwitch
from evdev import ecodes
import time


def make_lswitch_no_threads(monkeypatch):
    monkeypatch.setattr('threading.Thread.start', lambda self: None)
    # Prevent real uinput creation
    class DummyUInput:
        def __init__(self, *a, **k):
            pass
        def write(self, *a, **k):
            pass
        def syn(self):
            pass
    monkeypatch.setattr('evdev.UInput', DummyUInput)
    ls = LSwitch(config_path='config.json')
    # small timeout for speed
    ls.double_click_timeout = 0.5
    return ls


def test_navigation_resets_backspace_and_allows_retype(monkeypatch):
    ls = make_lswitch_no_threads(monkeypatch)

    # Simulate that user pressed backspace once (not a hold)
    ev_back = SimpleNamespace(type=ecodes.EV_KEY, code=ecodes.KEY_BACKSPACE, value=0)
    ls.handle_event(ev_back)

    assert ls.had_backspace is True

    # Now simulate navigation (left arrow). Previously this would not clear when buffer empty.
    ev_nav = SimpleNamespace(type=ecodes.EV_KEY, code=ecodes.KEY_LEFT, value=0)
    ls.handle_event(ev_nav)

    # Buffer should be cleared and had_backspace reset
    assert ls.had_backspace is False

    # Type a character and ensure convert chooses retype (no selection path)
    ev_a_press = SimpleNamespace(type=ecodes.EV_KEY, code=30, value=1)  # KEY_ a press
    ev_a_rel = SimpleNamespace(type=ecodes.EV_KEY, code=30, value=0)    # release
    ls.handle_event(ev_a_press)
    ls.handle_event(ev_a_rel)

    # Mark convert calls
    called = {'retype': False, 'selection': False}
    monkeypatch.setattr(ls, 'convert_and_retype', lambda *a, **k: called.__setitem__('retype', True))
    monkeypatch.setattr(ls, 'convert_selection', lambda *a, **k: called.__setitem__('selection', True))

    # Simulate double shift
    ev_shift_rel = SimpleNamespace(type=ecodes.EV_KEY, code=ecodes.KEY_LEFTSHIFT, value=0)
    # first release
    ls.handle_event(SimpleNamespace(type=ecodes.EV_KEY, code=ecodes.KEY_LEFTSHIFT, value=1))
    ls.handle_event(ev_shift_rel)
    # second within timeout
    ls.handle_event(SimpleNamespace(type=ecodes.EV_KEY, code=ecodes.KEY_LEFTSHIFT, value=1))
    ls.handle_event(ev_shift_rel)

    assert called['retype'] is True
    assert called['selection'] is False
