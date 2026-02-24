import pytest
from types import SimpleNamespace

from lswitch.selection import SelectionManager


class MockX11_Delete:
    def __init__(self, primary=' word'):
        self.primary = primary
        self.clipboard = ''
        self.cut_called = False
        self.delete_called = False
        self.paste_called = False

    def get_primary_selection(self, timeout=0.3):
        return self.primary

    def expand_selection_to_space(self, max_steps=100, stable_timeout=0.5):
        self.primary = ' ' + self.primary.lstrip()
        return self.primary

    def delete_selection(self):
        self.delete_called = True
        # remove selection without copying
        self.primary = ''

    def set_clipboard(self, text):
        self.clipboard = text

    def paste_clipboard(self):
        self.paste_called = True
        self.primary = self.clipboard


def test_delete_selection_prevents_leading_space_capture(monkeypatch):
    adapter = MockX11_Delete(primary='word')
    sm = SelectionManager(adapter)

    orig, conv = sm.convert_selection(lambda s: s.upper(), debug=True, prefer_trim_leading=True)

    # Simplified algorithm: no delete_selection anymore, paste replaces selection
    assert adapter.paste_called is True
    assert conv == 'WORD'
    # Clipboard should include leading space for proper replacement
    assert adapter.primary == ' WORD'


if __name__ == '__main__':
    pytest.main([__file__])