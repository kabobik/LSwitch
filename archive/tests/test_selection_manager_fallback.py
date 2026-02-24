import time

from lswitch.selection import SelectionManager


class MockX11FailOnce:
    def __init__(self, primary='hello'):
        self.primary = primary
        self.clipboard = ''
        self.paste_calls = 0

    def get_primary_selection(self, timeout=0.3):
        return self.primary

    def get_clipboard(self, timeout=0.3):
        return self.clipboard

    def set_clipboard(self, text):
        self.clipboard = text

    def paste_clipboard(self):
        # Simplified: paste always replaces selection with clipboard
        self.paste_calls += 1
        self.primary = self.clipboard


class MockX11NeverPaste:
    def __init__(self, primary='hello'):
        self.primary = primary
        self.clipboard = ''
        self.paste_calls = 0

    def get_primary_selection(self, timeout=0.3):
        return self.primary

    def get_clipboard(self, timeout=0.3):
        return self.clipboard

    def set_clipboard(self, text):
        self.clipboard = text

    def paste_clipboard(self):
        # Simplified: paste always replaces selection with clipboard
        self.paste_calls += 1
        self.primary = self.clipboard


def test_paste_retry_succeeds(monkeypatch):
    m = MockX11FailOnce(primary='hello')
    sm = SelectionManager(m)

    def conv(s):
        return 'привет'

    orig, conv_text = sm.convert_selection(conv, debug=True)
    # Simplified: paste works on first try
    assert m.primary == 'привет'
    assert m.paste_calls == 1


def test_paste_never_work_direct_set(monkeypatch):
    m = MockX11NeverPaste(primary='hello')
    sm = SelectionManager(m)

    def conv(s):
        return 'мир'

    orig, conv_text = sm.convert_selection(conv, debug=True)
    # Simplified: paste replaces selection
    assert m.primary == 'мир'
    assert m.paste_calls == 1
