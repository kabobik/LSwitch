import types
import time
from types import SimpleNamespace

import pytest
from evdev import ecodes

import lswitch as ls_mod
from lswitch import LSwitch


class DummyUInput:
    def __init__(self, *args, **kwargs):
        self.writes = []
    def write(self, *a, **k):
        self.writes.append(a)
    def syn(self):
        pass


def make_lswitch(monkeypatch):
    # prevent actual threads from starting
    monkeypatch.setattr('threading.Thread.start', lambda self: None)
    # prevent creating a real uinput device
    monkeypatch.setattr('evdev.UInput', DummyUInput)

    ls = LSwitch(config_path='config.json')
    ls.user_dict = None
    ls.config['debug'] = True
    ls.config['switch_layout_after_convert'] = False
    return ls


def mk_event(code, value):
    return SimpleNamespace(type=ecodes.EV_KEY, code=code, value=value)


def test_suppresses_shift_detection_during_replay(monkeypatch):
    ls = make_lswitch(monkeypatch)

    # Prepare buffer events that include several Shift releases (simulate
    # the kind of events that could retrigger double-shift detection when replayed)
    ev_shift_rel = mk_event(ecodes.KEY_LEFTSHIFT, 0)
    ev_a = mk_event(ecodes.KEY_A, 0)

    # Set these as the events to be replayed
    ls.buffer.set_events([ev_shift_rel, ev_shift_rel, ev_a])
    ls.buffer.chars_in_buffer = 1

    # Force the conversion mode to be "retype" so convert_and_retype() path is taken
    ls.conversion_manager = SimpleNamespace(choose_mode=lambda buffer, has_sel_fn, backspace_hold=False: 'retype')

    # Wrap on_double_shift to count invocations while delegating to original
    orig = ls.input_handler.on_double_shift
    calls = {'count': 0}

    def wrapped_on_double_shift():
        calls['count'] += 1
        return orig()

    ls.input_handler.on_double_shift = wrapped_on_double_shift

    # Patch replay_events so that replayed events are delivered back into
    # the same handler (simulating virtual keyboard loopback) so we can
    # observe whether suppression prevents retriggering.
    def replay_and_inject(events):
        for ev in events:
            # deliver events as if they were coming from the input subsystem
            ls.handle_event(ev)

    monkeypatch.setattr(ls.input_handler, 'replay_events', replay_and_inject)

    # Simulate user performing a double Shift (two releases)
    ls.handle_event(ev_shift_rel)
    ls.handle_event(ev_shift_rel)

    # Ensure on_double_shift was called exactly once (the original trigger),
    # not retriggered by replayed shift events
    assert calls['count'] == 1, f"on_double_shift called {calls['count']} times, expected 1"