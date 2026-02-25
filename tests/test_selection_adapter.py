"""Tests for SelectionAdapter — mock-based."""

from __future__ import annotations

import time
import pytest

from lswitch.platform.selection_adapter import (
    ISelectionAdapter,
    SelectionInfo,
    X11SelectionAdapter,
)
from lswitch.platform.system_adapter import CommandResult

# Re-use mock adapters from conftest
from tests.conftest import MockSelectionAdapter, MockSystemAdapter


# ---------------------------------------------------------------------------
# MockSelectionAdapter tests
# ---------------------------------------------------------------------------

class TestMockSelectionAdapter:
    """ISelectionAdapter contract verified via MockSelectionAdapter."""

    def test_implements_interface(self, mock_selection: MockSelectionAdapter):
        assert isinstance(mock_selection, ISelectionAdapter)

    def test_get_selection_empty(self, mock_selection: MockSelectionAdapter):
        info = mock_selection.get_selection()
        assert isinstance(info, SelectionInfo)
        assert info.text == ""

    def test_set_and_get_selection(self, mock_selection: MockSelectionAdapter):
        mock_selection.set_selection("hello")
        info = mock_selection.get_selection()
        assert info.text == "hello"
        assert info.owner_id > 0

    def test_has_fresh_selection_empty_is_false(self, mock_selection: MockSelectionAdapter):
        assert mock_selection.has_fresh_selection() is False

    def test_has_fresh_selection_after_set(self, mock_selection: MockSelectionAdapter):
        mock_selection.set_selection("word")
        assert mock_selection.has_fresh_selection() is True

    def test_has_fresh_selection_on_same_text(self, mock_selection: MockSelectionAdapter):
        """CRITICAL: re-selecting the same text should still count as fresh.

        This is the v1 bug fix — owner_id changes so the selection is fresh
        even when the text content is identical.
        """
        mock_selection.set_selection("same")
        assert mock_selection.has_fresh_selection() is True
        # "Re-select" the same text — owner_id increments
        mock_selection.set_selection("same")
        assert mock_selection.has_fresh_selection() is True

    def test_replace_selection(self, mock_selection: MockSelectionAdapter):
        mock_selection.set_selection("old")
        result = mock_selection.replace_selection("new")
        assert result is True
        assert mock_selection.get_selection().text == "new"

    def test_expand_selection_to_word(self, mock_selection: MockSelectionAdapter):
        mock_selection.set_selection("partial")
        info = mock_selection.expand_selection_to_word()
        assert isinstance(info, SelectionInfo)
        # Mock doesn't really expand, just returns current
        assert info.text == "partial"


# ---------------------------------------------------------------------------
# X11SelectionAdapter unit tests (with mock system adapter)
# ---------------------------------------------------------------------------

class _RecordingSystemAdapter(MockSystemAdapter):
    """Extends MockSystemAdapter to record calls and control clipboard state."""

    def __init__(self):
        self._clipboard: dict[str, str] = {"primary": "", "clipboard": ""}
        self.keys_sent: list[str] = []

    def get_clipboard(self, selection: str = "primary") -> str:
        return self._clipboard.get(selection, "")

    def set_clipboard(self, text: str, selection: str = "clipboard") -> None:
        self._clipboard[selection] = text

    def xdotool_key(self, sequence: str, timeout: float = 0.3) -> None:
        self.keys_sent.append(sequence)


class TestX11SelectionAdapterUnit:
    """Test X11SelectionAdapter with mocked system adapter (no real X11)."""

    def _make_adapter(self, system=None) -> X11SelectionAdapter:
        return X11SelectionAdapter(system=system or _RecordingSystemAdapter())

    def test_get_selection_returns_info(self):
        sys = _RecordingSystemAdapter()
        sys._clipboard["primary"] = "hello"
        adapter = self._make_adapter(sys)
        info = adapter.get_selection()
        assert isinstance(info, SelectionInfo)
        assert info.text == "hello"

    def test_get_selection_empty(self):
        adapter = self._make_adapter()
        info = adapter.get_selection()
        assert info.text == ""

    def test_has_fresh_selection_detects_text_change(self):
        sys = _RecordingSystemAdapter()
        adapter = self._make_adapter(sys)

        sys._clipboard["primary"] = "alpha"
        assert adapter.has_fresh_selection() is True

        # Same text, same owner (owner_id=0 from mock) → not fresh
        assert adapter.has_fresh_selection() is False

        # Text changes
        sys._clipboard["primary"] = "beta"
        assert adapter.has_fresh_selection() is True

    def test_has_fresh_selection_same_text_same_owner_not_fresh(self):
        sys = _RecordingSystemAdapter()
        sys._clipboard["primary"] = "text"
        adapter = self._make_adapter(sys)

        # First call: fresh because text changed from ""
        assert adapter.has_fresh_selection() is True
        # Second call: same text, same owner → not fresh
        assert adapter.has_fresh_selection() is False

    def test_replace_selection(self):
        sys = _RecordingSystemAdapter()
        adapter = self._make_adapter(sys)
        result = adapter.replace_selection("converted")
        assert result is True
        assert "ctrl+v" in sys.keys_sent

    def test_replace_selection_restores_clipboard(self):
        """replace_selection должен восстановить оригинальный clipboard."""
        sys = _RecordingSystemAdapter()
        sys._clipboard["clipboard"] = "original"
        adapter = self._make_adapter(sys)
        result = adapter.replace_selection("new text")
        assert result is True
        # After replace_selection, the clipboard must be restored to "original"
        assert sys._clipboard["clipboard"] == "original"

    def test_replace_selection_restores_empty_clipboard(self):
        """replace_selection с пустым clipboard не должен крашиться."""
        sys = _RecordingSystemAdapter()
        sys._clipboard["clipboard"] = ""
        adapter = self._make_adapter(sys)
        result = adapter.replace_selection("new text")
        assert result is True
        # Empty string clipboard must also be restored (not skipped)
        assert sys._clipboard["clipboard"] == ""

    def test_expand_selection_to_word(self):
        sys = _RecordingSystemAdapter()
        sys._clipboard["primary"] = "word"
        adapter = self._make_adapter(sys)
        info = adapter.expand_selection_to_word()
        assert isinstance(info, SelectionInfo)
        assert "ctrl+shift+Left" in sys.keys_sent
