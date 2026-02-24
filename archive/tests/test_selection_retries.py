import pytest
from lswitch.selection import SelectionManager


class RetryAdapter:
    def __init__(self, primary):
        self.primary = primary
        self.clipboard = ''
        self.paste_calls = 0

    def get_primary_selection(self):
        return self.primary

    def set_clipboard(self, text):
        self.clipboard = text

    def paste_clipboard(self):
        # Simplified: paste always replaces selection
        self.paste_calls += 1
        self.primary = self.clipboard


def test_paste_succeeds_on_retry():
    adapter = RetryAdapter('word')
    sm = SelectionManager(adapter)

    def conv_fn(s):
        return s[::-1]  # reverse for visibility

    orig, conv = sm.convert_selection(conv_fn, debug=True)

    assert orig == 'word'
    assert conv == 'drow'
    # Simplified: paste works on first try
    assert adapter.get_primary_selection() == 'drow'
    assert adapter.paste_calls == 1


class CutThenPasteAdapter:
    def __init__(self, primary):
        self.primary = primary
        self.clipboard = ''
        self.paste_calls = 0

    def get_primary_selection(self):
        return self.primary

    def set_clipboard(self, text):
        self.clipboard = text

    def paste_clipboard(self):
        # Simplified: paste replaces selection with clipboard
        self.paste_calls += 1
        self.primary = self.clipboard


def test_cut_then_paste_with_retry():
    adapter = CutThenPasteAdapter('hello')
    sm = SelectionManager(adapter)

    def conv_fn(s):
        return s.upper()

    orig, conv = sm.convert_selection(conv_fn, debug=True)

    assert orig == 'hello'
    assert conv == 'HELLO'
    # Simplified: paste works on first try
    assert adapter.get_primary_selection() == 'HELLO'
    assert adapter.paste_calls == 1
