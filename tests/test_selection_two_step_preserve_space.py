import pytest
from types import SimpleNamespace

from selection import SelectionManager


class MockX11_TwoStep:
    def __init__(self, primary='раз проверка'):
        self.primary = primary
        self.clipboard = ''
        self.cut_calls = 0
        self.paste_calls = 0
        self.deleted = False

    def get_primary_selection(self, timeout=0.3):
        return self.primary

    def cut_selection(self):
        self.cut_calls += 1
        self.clipboard = self.primary
        self.primary = ''

    def set_clipboard(self, text):
        self.clipboard = text

    def paste_clipboard(self):
        self.paste_calls += 1
        self.primary = self.clipboard

    # simulate expand: right-convert second step, expand selects ' проверка' (leading space + word)
    def ctrl_shift_left(self):
        self.primary = ' ' + self.primary.split()[-1]
        return self.primary


def test_two_step_conversion_preserves_internal_space(monkeypatch):
    adapter = MockX11_TwoStep(primary='раз проверка')
    sm = SelectionManager(adapter)

    # First conversion: user selects 'раз проверка' directly
    orig1, conv1 = sm.convert_selection(lambda s: s.upper(), debug=True, prefer_trim_leading=False)
    assert conv1 == 'РАЗ ПРОВЕРКА'
    # After first step, primary should be replaced with converted text
    assert adapter.primary == conv1

    # Simulate user moves to the second word and triggers convert without explicit selection
    # Adapter.expand (ctrl_shift_left) will set primary to ' проверка'
    # Now, conversion should convert only 'проверка' but keep the space between words
    adapter.primary = ' ' + 'проверка'

    orig2, conv2 = sm.convert_selection(lambda s: s.upper(), debug=True, prefer_trim_leading=True)
    # converted second word must be 'ПРОВЕРКА'
    assert conv2 == 'ПРОВЕРКА'
    # And final primary should include the leading space preserved
    assert adapter.primary == (' ' + conv2)


if __name__ == '__main__':
    pytest.main([__file__])