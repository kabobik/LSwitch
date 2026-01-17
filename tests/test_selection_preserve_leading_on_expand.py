import pytest
from types import SimpleNamespace

from selection import SelectionManager


class MockX11_Expand:
    def __init__(self, primary='поведения'):
        # initial selection (no leading space)
        self.primary = primary
        self.clipboard = ''
        self.cut_called = False
        self.paste_called = False

    def get_primary_selection(self, timeout=0.3):
        return self.primary

    def expand_selection_to_space(self, max_steps=100, stable_timeout=0.5):
        # simulate expansion that *adds* a leading space
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


def test_preserve_leading_space_added_by_expansion(monkeypatch):
    adapter = MockX11_Expand(primary='поведения')
    sm = SelectionManager(adapter)

    orig, conv = sm.convert_selection(lambda s: s.upper(), debug=True, prefer_trim_leading=False)

    # ensure conversion happened
    assert conv == 'ПОВЕДЕНИЯ'

    # since expansion added a leading space and caller did NOT request trimming,
    # the pasted primary should preserve that leading space
    assert adapter.primary.startswith(' ' + conv)


if __name__ == '__main__':
    pytest.main([__file__])
