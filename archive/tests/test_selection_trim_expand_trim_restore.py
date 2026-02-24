import pytest
from types import SimpleNamespace

from lswitch.selection import SelectionManager


class MockX11_TrimAndRemove:
    """Simulate expansion that adds leading space, then delete_selection removes it."""
    def __init__(self, primary='word'):
        self.primary = primary
        self.clipboard = ''
        self.deleted = False
        self.paste_calls = 0

    def get_primary_selection(self, timeout=0.3):
        return self.primary

    def expand_selection_to_space(self, max_steps=100, stable_timeout=0.5):
        # expansion returns leading space + word
        self.primary = ' ' + self.primary
        return self.primary

    def delete_selection(self):
        # simulate that delete_selection removes the selection (incl. leading space)
        self.deleted = True
        self.primary = ''

    def set_clipboard(self, text):
        self.clipboard = text

    def paste_clipboard(self):
        self.paste_calls += 1
        # paste puts clipboard content as primary exactly
        self.primary = self.clipboard


def test_trim_expand_restore_leading_space(monkeypatch):
    adapter = MockX11_TrimAndRemove(primary='word')
    sm = SelectionManager(adapter)

    orig, conv = sm.convert_selection(lambda s: s.upper(), debug=True, prefer_trim_leading=True)

    # conversion should be the uppercase word
    assert conv == 'WORD'
    # Simplified: paste replaces selection, includes leading space
    assert adapter.primary == ' WORD'
    # No delete_selection anymore in simplified algorithm
    assert adapter.paste_calls == 1


if __name__ == '__main__':
    pytest.main([__file__])