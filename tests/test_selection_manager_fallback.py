import time

from selection import SelectionManager


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
        # Fail first time (no effect), succeed second time
        self.paste_calls += 1
        if self.paste_calls >= 2:
            self.primary = self.clipboard

    def cut_selection(self):
        self.clipboard = self.primary
        self.primary = ''


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
        # Never changes primary
        self.paste_calls += 1

    def cut_selection(self):
        self.clipboard = self.primary
        self.primary = ''


def test_paste_retry_succeeds(monkeypatch):
    m = MockX11FailOnce(primary='hello')
    sm = SelectionManager(m)

    def conv(s):
        return 'привет'

    orig, conv_text = sm.convert_selection(conv, debug=True)
    assert m.primary == 'привет'
    assert m.paste_calls >= 2


def test_paste_never_work_direct_set(monkeypatch):
    m = MockX11NeverPaste(primary='hello')
    sm = SelectionManager(m)

    def conv(s):
        return 'мир'

    orig, conv_text = sm.convert_selection(conv, debug=True)
    # fallback should set primary directly
    assert m.primary == 'мир'
    assert m.paste_calls >= 1
