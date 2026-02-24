import pytest
from types import SimpleNamespace

import lswitch as ls_mod
from lswitch.core import LSwitch


class MockX11_Leading:
    def __init__(self, primary='j', after_expanded=' j'):
        # initial primary is unexpanded; after shift_left it becomes ' j'
        self.primary = primary
        self.after = after_expanded
        self.clipboard = ''
        self.cut_called = False
        self.paste_called = False

    def get_primary_selection(self, timeout=0.3):
        return self.primary

    def shift_left(self):
        # simulate expansion adding leading space
        self.primary = self.after

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
    import lswitch.core as _core_mod
    monkeypatch.setattr(_core_mod, 'x11_adapter', mock_x11)
    ls = LSwitch(config_path='config.json')
    ls.user_dict = None
    ls.config['debug'] = True
    ls.config['switch_layout_after_convert'] = False
    return ls


def test_expand_strips_leading_space(monkeypatch):
    mock = MockX11_Leading(primary='j', after_expanded=' j')
    ls = make_lswitch(mock, monkeypatch)

    # Simulate user selecting + converting
    ls.convert_selection()

    # Since expansion added a leading space that was not present originally,
    # we expect the conversion to operate on 'j' and the clipboard to contain
    # the converted text without an extra leading space.
    expected = ls.convert_text('j')
    assert mock.clipboard == expected
    assert mock.primary == expected


if __name__ == '__main__':
    pytest.main([__file__])