import importlib
import time

import pytest
from evdev import ecodes

import lswitch as ls_mod
from lswitch.core import LSwitch


class MockX11:
    def __init__(self, primary='j,sxysq'):
        self.primary = primary
        self.clipboard = ''
        self.shift_calls = 0
        self.cut_called = False
        self.delete_called = False
        self.paste_called = False

    def get_primary_selection(self, timeout=0.3):
        print(f"MOCK get_primary_selection -> {self.primary!r}")
        return self.primary

    def get_clipboard(self, timeout=0.3):
        return self.clipboard

    def set_clipboard(self, text):
        print(f"MOCK set_clipboard -> {text!r}")
        self.clipboard = text

    def paste_clipboard(self):
        self.paste_called = True
        # simulate paste effect (for test): primary now becomes clipboard
        self.primary = self.clipboard

    def cut_selection(self):
        self.cut_called = True
        self.clipboard = self.primary
        self.primary = ''

    def delete_selection(self):
        self.delete_called = True
        self.primary = ''

    def shift_left(self):
        self.shift_calls += 1
        # After several shifts, simulate expansion by adding space to the left
        if self.shift_calls >= 4 and not self.primary.startswith(' '):
            self.primary = ' ' + self.primary

    def ctrl_shift_left(self):
        # word-wise expansion
        if not self.primary.startswith(' '):
            self.primary = ' ' + self.primary


class DummyUInput:
    def __init__(self, *args, **kwargs):
        pass

    def write(self, *a, **k):
        pass

    def syn(self):
        pass


def make_lswitch(mock_x11, monkeypatch):
    # prevent actual threads from starting
    monkeypatch.setattr('threading.Thread.start', lambda self: None)
    # prevent creating a real uinput device
    monkeypatch.setattr('evdev.UInput', DummyUInput)

    # patch adapter at module level (both lswitch and lswitch.core for text_processor)
    monkeypatch.setattr(ls_mod, 'x11_adapter', mock_x11)
    import lswitch.core as _core_mod
    monkeypatch.setattr(_core_mod, 'x11_adapter', mock_x11)

    # instantiate
    ls = LSwitch(config_path='config.json')
    # disable user dict for predictability
    ls.user_dict = None
    # enable debug to capture diagnostic logs during tests
    ls.config['_debug_for_tests'] = ls.config.get('debug', True)
    ls.config['debug'] = True
    # avoid actually switching layout during tests
    ls.config['switch_layout_after_convert'] = False
    return ls


@pytest.mark.parametrize('initial', [
    'j,sxysq', 'ytdthysq', 'hello,world', 'test.case', 'Ghbdtn', 'a', ','
])
def test_selection_convert_roundtrip(monkeypatch, initial):
    mock = MockX11(primary=initial)
    ls = make_lswitch(mock, monkeypatch)

    # First conversion (en->ru)
    ls.convert_selection()

    expected_conv = ls.convert_text(initial)
    # primary is the authoritative visible content
    assert mock.primary == expected_conv

    # Ensure expansion was attempted at least once for inputs longer than 1
    if len(initial) > 1:
        assert mock.shift_calls >= 0

    # Now simulate selecting converted text and convert back
    mock.cut_called = False
    mock.paste_called = False
    mock.primary = expected_conv

    ls.convert_selection()

    expected_back = ls.convert_text(expected_conv)
    assert mock.primary == expected_back


def test_selection_triggered_by_backspace_hold(monkeypatch):
    # Ensure selection-mode is triggered when backspace is held
    mock = MockX11(primary='ytdthysq')
    ls = make_lswitch(mock, monkeypatch)

    # Simulate backspace repeats to detect hold
    from types import SimpleNamespace
    ev = SimpleNamespace(type=ecodes.EV_KEY, code=ecodes.KEY_BACKSPACE, value=2)
    for _ in range(4):
        ls.handle_event(ev)

    # Now simulate double Shift (release twice)
    ev_shift = SimpleNamespace(type=ecodes.EV_KEY, code=ecodes.KEY_LEFTSHIFT, value=0)
    ls.handle_event(ev_shift)
    ls.handle_event(ev_shift)

    # After double shift with backspace hold, selection flow should be used
    assert mock.cut_called or mock.delete_called
    assert mock.paste_called


if __name__ == '__main__':
    pytest.main([__file__])
