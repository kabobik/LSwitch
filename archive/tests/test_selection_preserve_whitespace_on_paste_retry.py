import pytest
from types import SimpleNamespace

from lswitch.selection import SelectionManager


class MockX11_PasteStrips:
    def __init__(self, primary=' word'):
        self.primary = primary
        self.clipboard = ''
        self.paste_calls = 0

    def get_primary_selection(self, timeout=0.3):
        return self.primary

    def expand_selection_to_space(self, max_steps=100, stable_timeout=0.5):
        self.primary = ' ' + self.primary.lstrip()
        return self.primary

    def set_clipboard(self, text):
        self.clipboard = text

    def paste_clipboard(self):
        # Simplified: paste replaces selection with clipboard
        self.paste_calls += 1
        self.primary = self.clipboard


def test_preserve_whitespace_by_direct_set(monkeypatch):
    adapter = MockX11_PasteStrips(primary='word')
    sm = SelectionManager(adapter)

    orig, conv = sm.convert_selection(lambda s: s.upper(), debug=True, prefer_trim_leading=False)

    # conversion should be the uppercase word
    assert conv == 'WORD'
    # Simplified: paste includes leading space from expansion
    assert adapter.primary == ' WORD'
    assert adapter.paste_calls == 1


if __name__ == '__main__':
    pytest.main([__file__])