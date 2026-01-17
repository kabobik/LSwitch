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
    monkeypatch.setattr('threading.Thread.start', lambda self: None)
    monkeypatch.setattr('evdev.UInput', DummyUInput)
    ls = LSwitch(config_path='config.json')
    ls.user_dict = None
    ls.config['debug'] = True
    return ls


def mk_event(code, value):
    return SimpleNamespace(type=ecodes.EV_KEY, code=code, value=value)


def test_stray_shift_release_ignored(monkeypatch):
    ls = make_lswitch(monkeypatch)

    called = {'count': 0}
    orig = ls.input_handler.on_double_shift

    def wrapped():
        called['count'] += 1
        return orig()

    ls.input_handler.on_double_shift = wrapped

    ev_rel = mk_event(ecodes.KEY_LEFTSHIFT, 0)

    # send a single release (no preceding press) — should not trigger
    ls.handle_event(ev_rel)

    assert called['count'] == 0


def test_normal_double_shift_triggers(monkeypatch):
    ls = make_lswitch(monkeypatch)

    called = {'count': 0}
    orig = ls.input_handler.on_double_shift

    def wrapped():
        called['count'] += 1
        return orig()

    ls.input_handler.on_double_shift = wrapped

    ev_press = mk_event(ecodes.KEY_LEFTSHIFT, 1)
    ev_rel = mk_event(ecodes.KEY_LEFTSHIFT, 0)

    # Press+release, then press+release quickly -> should trigger once
    ls.handle_event(ev_press)
    ls.handle_event(ev_rel)
    time.sleep(0.05)
    ls.handle_event(ev_press)
    ls.handle_event(ev_rel)

    assert called['count'] == 1, f"on_double_shift called {called['count']} times"