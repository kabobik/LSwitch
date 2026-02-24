from types import SimpleNamespace
from lswitch.core import LSwitch
from evdev import ecodes


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
    # ensure small timeout for speed
    ls.double_click_timeout = 0.5
    return ls


def test_backspace_hold_detection(monkeypatch):
    ls = make_lswitch_no_threads(monkeypatch)

    # Simulate repeats of Backspace (value=2) several times
    ev = SimpleNamespace(type=ecodes.EV_KEY, code=ecodes.KEY_BACKSPACE, value=2)
    for _ in range(4):
        ls.handle_event(ev)

    assert ls.consecutive_backspace_repeats >= 3
    assert ls.backspace_hold_detected


def test_double_shift_after_hold_triggers_selection(monkeypatch):
    ls = make_lswitch_no_threads(monkeypatch)

    # Mark as if backspace hold detected
    ls.backspace_hold_detected = True

    called = {'selection': False, 'retype': False}

    def sel_cb():
        called['selection'] = True

    def r_cb():
        called['retype'] = True

    # Monkeypatch convert_selection and convert_and_retype to record calls
    monkeypatch.setattr(ls, 'convert_selection', sel_cb)
    monkeypatch.setattr(ls, 'convert_and_retype', r_cb)

    # Simulate two Shift releases within timeout
    ev_shift = SimpleNamespace(type=ecodes.EV_KEY, code=ecodes.KEY_LEFTSHIFT, value=0)
    ls.handle_event(ev_shift)  # first release -> sets last_shift_press
    ls.handle_event(ev_shift)  # second release -> should detect double click

    assert called['selection']
    # backspace hold flag should be cleared after handling
    assert not ls.backspace_hold_detected
