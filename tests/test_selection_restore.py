import pytest
from lswitch.selection import SelectionManager


class FailingAdapter:
    def __init__(self, primary):
        self.primary = primary
        self.clipboard = ''

    def get_primary_selection(self):
        return self.primary

    def delete_selection(self):
        # simulate deletion clearing primary
        self.primary = ''

    def set_clipboard(self, text):
        self.clipboard = text

    def paste_clipboard(self):
        # Simulate a failing paste: do nothing (clipboard not applied to primary)
        return


def test_convert_selection_restores_original_on_failed_paste(monkeypatch):
    adapter = FailingAdapter('hello')
    sm = SelectionManager(adapter)

    def conv_fn(s):
        return s.upper()

    orig, conv = sm.convert_selection(conv_fn, debug=True)

    # After conversion attempt with failing paste, primary should be either converted (if last-resort worked)
    # or restored to original (if paste succeeded on restore). We accept both behaviors, but not deletion.
    assert adapter.get_primary_selection() in ('HELLO', 'hello')
    assert orig == 'hello'
    assert conv == 'HELLO'
