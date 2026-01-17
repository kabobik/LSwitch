import pytest
from lswitch.selection import SelectionManager


class RetryAdapter:
    def __init__(self, primary):
        self.primary = primary
        self.clipboard = ''
        self.paste_calls = 0

    def get_primary_selection(self):
        return self.primary

    def delete_selection(self):
        # simulate deletion clearing primary
        self.primary = ''

    def set_clipboard(self, text):
        self.clipboard = text

    def paste_clipboard(self):
        # succeed only on 2nd paste call
        self.paste_calls += 1
        if self.paste_calls >= 2:
            self.primary = self.clipboard


def test_paste_succeeds_on_retry():
    adapter = RetryAdapter('word')
    sm = SelectionManager(adapter)

    def conv_fn(s):
        return s[::-1]  # reverse for visibility

    orig, conv = sm.convert_selection(conv_fn, debug=True)

    assert orig == 'word'
    assert conv == 'drow'
    assert adapter.get_primary_selection() == 'drow'


class CutThenPasteAdapter:
    def __init__(self, primary):
        self.primary = primary
        self.clipboard = ''
        self.paste_calls = 0
        self.cut_called = False

    def get_primary_selection(self):
        return self.primary

    def cut_selection(self):
        # simulate a cut that succeeds in moving text to clipboard
        self.cut_called = True
        self.clipboard = self.primary
        self.primary = ''

    def set_clipboard(self, text):
        self.clipboard = text

    def paste_clipboard(self):
        # succeed only after cut was called and second paste
        self.paste_calls += 1
        if self.paste_calls >= 2 and self.cut_called:
            self.primary = self.clipboard


def test_cut_then_paste_with_retry():
    adapter = CutThenPasteAdapter('hello')
    sm = SelectionManager(adapter)

    def conv_fn(s):
        return s.upper()

    orig, conv = sm.convert_selection(conv_fn, debug=True)

    assert orig == 'hello'
    assert conv == 'HELLO'
    assert adapter.get_primary_selection() == 'HELLO'
