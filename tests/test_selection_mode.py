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


class _DirectSelectionAdapter:
    def __init__(self, text: str):
        self.info = SelectionInfo(text=text, owner_id=0, timestamp=time.time())
        self.replace_calls: list[str] = []
        self.typed_calls: list[tuple[str, str]] = []

    def get_selection(self) -> SelectionInfo:
        return self.info

    def expand_selection_to_word(self) -> SelectionInfo:
        return self.info

    def replace_selection(self, new_text: str) -> bool:
        self.replace_calls.append(new_text)
        return True

    def prefers_direct_replacement(self) -> bool:
        return True

    def replace_selection_by_typing(
        self,
        new_text: str,
        layout_name: str = "en",
    ) -> bool:
        self.typed_calls.append((new_text, layout_name))
        return True


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

    def test_direct_replacement_switches_layout_before_typing(self):
        from lswitch.platform.xkb_adapter import LayoutInfo

        sel = _DirectSelectionAdapter("ghbdtn")
        xkb = MagicMock()
        xkb.get_layouts.return_value = [
            LayoutInfo(name="en", index=0, xkb_name="us"),
            LayoutInfo(name="ru", index=1, xkb_name="ru"),
        ]
        mode, _, _, _ = _make_selection_mode(sel_adapter=sel, xkb=xkb)
        ctx = StateContext()

        result = mode.execute(ctx)

        assert result is True
        assert sel.replace_calls == []
        assert sel.typed_calls == [("привет", "ru")]
        xkb.switch_layout.assert_called_once_with(target=xkb.get_layouts.return_value[1])


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
