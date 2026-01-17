import pytest
import time
from types import SimpleNamespace

import lswitch as ls_mod
from lswitch import LSwitch
from selection import SelectionManager


class MockX11_Trim:
    def __init__(self, primary=' word'):
        self.primary = primary
        self.clipboard = ''
        self.cut_called = False
        self.paste_called = False

    def get_primary_selection(self, timeout=0.3):
        return self.primary

    def expand_selection_to_space(self, max_steps=100, stable_timeout=0.5):
        # simulate expansion producing leading space
        self.primary = ' ' + self.primary.lstrip()
        return self.primary

    def cut_selection(self):
        self.cut_called = True
        self.clipboard = self.primary
        self.primary = ''

    def set_clipboard(self, text):
        self.clipboard = text

    def paste_clipboard(self):
        self.paste_called = True
        self.primary = self.clipboard


class DummyUInput:
    def __init__(self, *args, **kwargs):
        pass
    def write(self, *a, **k):
        pass
    def syn(self):
        pass


def make_lswitch(mock_x11, monkeypatch):
    monkeypatch.setattr('threading.Thread.start', lambda self: None)
    monkeypatch.setattr('evdev.UInput', DummyUInput)
    monkeypatch.setattr(ls_mod, 'x11_adapter', mock_x11)
    ls = LSwitch(config_path='config.json')
    ls.user_dict = None
    ls.config['debug'] = True
    ls.config['switch_layout_after_convert'] = False
    return ls


def test_trim_clipboard_on_expand(monkeypatch):
    mock = MockX11_Trim(primary='word')
    ls = make_lswitch(mock, monkeypatch)

    # Simulate convert triggered via expansion (no prior selection)
    # prefer_trim_leading should be True in that scenario
    sm = SelectionManager(mock)
    orig, conv = sm.convert_selection(lambda s: s.upper(), debug=True, prefer_trim_leading=True)

    # Ensure conversion used trimmed clipboard (conversion of 'word')
    assert conv == 'WORD'
    # And final clipboard/paste contains converted word (may re-add leading space visually)
    assert mock.clipboard.strip() == 'WORD'


if __name__ == '__main__':
    pytest.main([__file__])