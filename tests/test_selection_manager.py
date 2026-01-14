import pytest
from types import SimpleNamespace
from selection import SelectionManager


class MockX11:
    def __init__(self, primary='j,sxysq'):
        self.primary = primary
        self.clip = ''
        self.expanded = False

    def get_primary_selection(self, timeout=0.3):
        return self.primary

    def expand_selection_to_space(self, max_steps=100, stable_timeout=0.5):
        self.expanded = True
        # emulate leading space after expansion
        if not self.primary.startswith(' '):
            self.primary = ' ' + self.primary
        return self.primary

    def safe_replace_selection(self, converted, selected_text=None, debug=False):
        # emulate replacing primary with converted text
        self.clip = converted
        self.primary = converted
        return self.primary


def convert_fn(s):
    return s.upper()


def test_convert_selection_roundtrip(monkeypatch):
    adapter = MockX11(primary='hello,world')
    sm = SelectionManager(adapter)

    orig, conv = sm.convert_selection(convert_fn, debug=True)
    assert orig.strip() == 'hello,world'
    assert conv == 'HELLO,WORLD'
    assert adapter.expanded
    assert adapter.primary == conv


def test_no_adapter():
    sm = SelectionManager(None)
    orig, conv = sm.convert_selection(convert_fn)
    assert orig == '' and conv == ''
