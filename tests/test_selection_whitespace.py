import pytest
import time
from types import SimpleNamespace
from evdev import ecodes

import lswitch as ls_mod
from lswitch import LSwitch


class MockX11_Space:
    def __init__(self, primary=' hello'):
        self.primary = primary
        self.clipboard = ''
        self.cut_called = False
        self.paste_called = False
    def get_primary_selection(self, timeout=0.3):
        return self.primary
    def cut_selection(self):
        self.cut_called = True
        self.clipboard = self.primary
        self.primary = ''
    def set_clipboard(self, text):
        self.clipboard = text
    def paste_clipboard(self):
        self.paste_called = True
        # simulate paste effect
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


def test_preserve_leading_space(monkeypatch):
    mock = MockX11_Space(primary=' hello')
    ls = make_lswitch(mock, monkeypatch)

    ls.convert_selection()

    # Expect leading space preserved
    assert mock.primary.startswith(' ')
    assert mock.primary.strip() == ls.convert_text('hello')


if __name__ == '__main__':
    pytest.main([__file__])