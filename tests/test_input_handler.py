import types
import time

from lswitch.input import InputHandler

# We'll use small DummyLS objects rather than importing LSwitch to avoid package/import shadowing issues in tests

class DummyFakeKb:
    def __init__(self):
        self.writes = []
    def write(self, ev_type, code, value):
        self.writes.append((ev_type, code, value))
    def syn(self):
        pass


def mk_event(code, value, ev_type=1):
    return types.SimpleNamespace(code=code, value=value, type=ev_type)


def test_replay_events_writes_to_fake_kb():
    dummy_ls = types.SimpleNamespace()
    dummy_ls.config = {'debug': False}
    dummy = DummyFakeKb()
    dummy_ls.fake_kb = dummy
    ih = InputHandler(dummy_ls)
    evs = [mk_event(30, 0), mk_event(31, 0)]
    ih.replay_events(evs)
    assert dummy.writes, 'No writes recorded'
    assert any(w[1] == 30 for w in dummy.writes)


def test_on_double_shift_calls_convert_and_retype(monkeypatch):
    dummy_ls = types.SimpleNamespace()
    dummy_ls.config = {'debug': False}
    called = {'retype': False}
    def fake_retype(is_auto=False):
        called['retype'] = True
    # attributes expected by InputHandler
    dummy_ls.convert_and_retype = fake_retype
    dummy_ls.conversion_manager = None
    dummy_ls.backspace_hold_detected = False
    dummy_ls.chars_in_buffer = 1
    dummy_ls.last_shift_press = 0
    dummy_ls.config = {'debug': False}
    ih = InputHandler(dummy_ls)
    ih.on_double_shift()
    assert called['retype'] is True


def test_handle_event_esc_does_not_exit():
    """ESC no longer terminates service - only signals SIGTERM/SIGINT do."""
    dummy_ls = types.SimpleNamespace()
    dummy_ls.config = {'debug': False}
    dummy_ls.user_dict = None
    dummy_ls.is_converting = False
    dummy_ls.navigation_keys = set()
    dummy_ls.event_buffer = []
    dummy_ls.last_shift_press = 0
    dummy_ls.double_click_timeout = 0.3
    dummy_ls.had_backspace = False
    dummy_ls.consecutive_backspace_repeats = 0
    dummy_ls.backspace_hold_detected = False
    dummy_ls.chars_in_buffer = 0
    dummy_ls.text_buffer = []
    dummy_ls.last_manual_convert = None
    dummy_ls.last_auto_convert = None
    # minimal methods
    dummy_ls.clear_buffer = lambda: None
    dummy_ls.update_selection_snapshot = lambda: None
    dummy_ls.check_and_auto_convert = lambda: None
    # create event
    ev = mk_event(getattr(types.SimpleNamespace(KEY_ESC=1, EV_KEY=1), 'KEY_ESC'), 0, getattr(types.SimpleNamespace(KEY_ESC=1, EV_KEY=1), 'EV_KEY'))
    ih = InputHandler(dummy_ls)
    res = ih.handle_event(ev)
    # ESC should NOT terminate - returns True to continue
    assert res is True
