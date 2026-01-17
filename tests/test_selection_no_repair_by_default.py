import pytest
from types import SimpleNamespace

from selection import SelectionManager


class MockX11_SafeReplaceMismatch:
    def __init__(self, primary='word'):
        self.primary = primary
        self.clipboard = ''
        self.deleted = False
        self.paste_calls = 0
        self.set_clipboard_calls = 0

    def get_primary_selection(self, timeout=0.3):
        return self.primary

    def safe_replace_selection(self, converted, selected_text=None, debug=False):
        # Adapter returns an unexpected value but does not modify primary
        return ' ' + converted.strip()

    def delete_selection(self):
        self.deleted = True
        self.primary = ''

    def set_clipboard(self, text):
        self.set_clipboard_calls += 1
        self.clipboard = text

    def paste_clipboard(self):
        self.paste_calls += 1
        self.primary = self.clipboard


def test_no_repair_by_default(monkeypatch):
    adapter = MockX11_SafeReplaceMismatch(primary='word')
    sm = SelectionManager(adapter)  # repair disabled by default

    orig, conv = sm.convert_selection(lambda s: s.upper(), debug=True, prefer_trim_leading=False)

    assert conv == 'WORD'
    # Since repair is disabled, delete/paste should not have been invoked
    assert adapter.deleted is False
    assert adapter.paste_calls == 0
    assert adapter.set_clipboard_calls == 0
    # Primary should remain unchanged (adapter didn't commit safe_replace to primary)
    assert adapter.primary == 'word'
