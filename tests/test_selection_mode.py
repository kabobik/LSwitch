"""Tests for SelectionMode."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from lswitch.core.modes import SelectionMode
from lswitch.core.states import StateContext
from lswitch.platform.selection_adapter import SelectionInfo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_selection_mode(sel_adapter=None, xkb=None, sys_adapter=None, debug=False):
    sel = sel_adapter or MagicMock()
    xkb_ = xkb or MagicMock()
    sys_ = sys_adapter or MagicMock()
    return SelectionMode(sel, xkb_, sys_, debug=debug), sel, xkb_, sys_


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSelectionModeConvert:
    def test_converts_selected_text(self):
        mode, sel, xkb, _ = _make_selection_mode()
        sel.get_selection.return_value = SelectionInfo(text="ghbdtn", owner_id=1, timestamp=time.time())
        ctx = StateContext()

        result = mode.execute(ctx)

        assert result is True
        sel.replace_selection.assert_called_once_with("привет")

    def test_switches_layout(self):
        mode, sel, xkb, _ = _make_selection_mode()
        sel.get_selection.return_value = SelectionInfo(text="ghbdtn", owner_id=1, timestamp=time.time())
        ctx = StateContext()

        mode.execute(ctx)

        xkb.switch_layout.assert_called_once()


class TestSelectionModeEmpty:
    def test_empty_selection_returns_false(self):
        mode, sel, xkb, _ = _make_selection_mode()
        sel.get_selection.return_value = SelectionInfo(text="", owner_id=0, timestamp=0.0)
        ctx = StateContext()

        result = mode.execute(ctx)

        assert result is False
        sel.replace_selection.assert_not_called()
        xkb.switch_layout.assert_not_called()


class TestSelectionModeRoundTrip:
    def test_double_conversion_returns_original(self):
        """Applying conversion twice should return the original text."""
        from lswitch.core.text_converter import convert_text

        original = "ghbdtn"
        first = convert_text(original)
        second = convert_text(first)

        assert second == original

    def test_double_shift_twice_roundtrip(self):
        """SelectionMode applied twice returns text back to original."""
        mode, sel, xkb, _ = _make_selection_mode()

        # First conversion: en→ru
        sel.get_selection.return_value = SelectionInfo(text="ghbdtn", owner_id=1, timestamp=time.time())
        ctx = StateContext()
        mode.execute(ctx)
        first_result = sel.replace_selection.call_args[0][0]
        assert first_result == "привет"

        # Second conversion: ru→en
        sel.get_selection.return_value = SelectionInfo(text=first_result, owner_id=2, timestamp=time.time())
        mode.execute(ctx)
        second_result = sel.replace_selection.call_args[0][0]
        assert second_result == "ghbdtn"
