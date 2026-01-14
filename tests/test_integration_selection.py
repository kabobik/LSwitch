import importlib
import time

import pytest

import lswitch as ls_mod
from lswitch import LSwitch


class MockX11:
    def __init__(self, primary='j,sxysq'):
        self.primary = primary
        self.clipboard = ''
        self.shift_calls = 0
        self.cut_called = False
        self.delete_called = False
        self.paste_called = False

    def get_primary_selection(self, timeout=0.3):
        return self.primary

    def get_clipboard(self, timeout=0.3):
        return self.clipboard

    def set_clipboard(self, text):
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

    # patch adapter at module level
    monkeypatch.setattr(ls_mod, 'x11_adapter', mock_x11)

    # instantiate
    ls = LSwitch(config_path='config.json')
    # disable user dict for predictability
    ls.user_dict = None
    return ls


def test_selection_convert_j_sxysq_roundtrip(monkeypatch):
    mock = MockX11(primary='j,sxysq')
    ls = make_lswitch(mock, monkeypatch)

    # First conversion (en->ru)
    ls.convert_selection()

    expected_conv = ls.convert_text('j,sxysq')
    assert mock.cut_called or mock.delete_called, "Expected cut or delete to be attempted"
    assert mock.paste_called, "Expected paste to be called"
    assert mock.clipboard == expected_conv
    assert mock.primary == expected_conv

    # Ensure expansion was attempted
    assert mock.shift_calls >= 1, "Expected selection expansion via shift_left"

    # Now simulate selecting converted text and convert back
    mock.cut_called = False
    mock.paste_called = False
    mock.primary = expected_conv

    ls.convert_selection()

    expected_back = ls.convert_text(expected_conv)
    assert mock.clipboard == expected_back
    assert mock.primary == expected_back


if __name__ == '__main__':
    pytest.main([__file__])
