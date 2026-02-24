import types
from lswitch.utils.keyboard import KeyboardController


class DummyUInput:
    def __init__(self):
        self.writes = []
    def write(self, typ, code, val):
        self.writes.append((typ, code, val))
    def syn(self):
        pass


def test_tap_key_calls_write_correctly():
    u = DummyUInput()
    kc = KeyboardController(u)
    kc.tap_key(42, n_times=2)
    # Each tap produces press and release => 2 writes per tap
    expected = [(1, 42, 1), (1, 42, 0)] * 2
    assert u.writes == expected


def test_replay_events_replays_values():
    u = DummyUInput()
    kc = KeyboardController(u)
    EV = types.SimpleNamespace
    events = [EV(code=10, value=1), EV(code=10, value=0), EV(code=11, value=0)]
    kc.replay_events(events)
    assert u.writes == [(1, 10, 1), (1, 10, 0), (1, 11, 0)]
