"""Tests for ConversionEngine.choose_mode() and convert()."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from lswitch.core.conversion_engine import ConversionEngine
from lswitch.core.states import State, StateContext
from lswitch.platform.selection_adapter import SelectionInfo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(code: int, value: int):
    ev = MagicMock()
    ev.code = code
    ev.value = value
    return ev


def _make_engine(
    xkb=None,
    selection=None,
    virtual_kb=None,
    dictionary=None,
    system=None,
    debug=False,
):
    xkb_ = xkb or MagicMock()
    sel_ = selection or MagicMock()
    vk_ = virtual_kb or MagicMock()
    dict_ = dictionary or MagicMock()
    sys_ = system or MagicMock()
    engine = ConversionEngine(xkb_, sel_, vk_, dict_, sys_, debug=debug)
    return engine, xkb_, sel_, vk_, dict_, sys_


# ---------------------------------------------------------------------------
# choose_mode tests
# ---------------------------------------------------------------------------

class TestChooseMode:
    def test_retype_when_chars_in_buffer(self):
        engine, _, sel, _, _, _ = _make_engine()
        sel.has_fresh_selection.return_value = False
        ctx = StateContext()
        ctx.chars_in_buffer = 5

        assert engine.choose_mode(ctx) == "retype"

    def test_selection_when_fresh_selection(self):
        engine, _, sel, _, _, _ = _make_engine()
        sel.has_fresh_selection.return_value = True
        ctx = StateContext()
        ctx.chars_in_buffer = 0

        assert engine.choose_mode(ctx) == "selection"

    def test_selection_when_backspace_hold(self):
        engine, _, sel, _, _, _ = _make_engine()
        sel.has_fresh_selection.return_value = False
        ctx = StateContext()
        ctx.state = State.BACKSPACE_HOLD
        ctx.backspace_hold_active = True
        ctx.chars_in_buffer = 5  # even with chars, backspace_hold_active → selection

        assert engine.choose_mode(ctx) == "selection"

    def test_choose_mode_backspace_hold_active(self):
        """backspace_hold_active=True forces selection even when state=CONVERTING."""
        engine, _, sel, _, _, _ = _make_engine()
        sel.has_fresh_selection.return_value = False
        ctx = StateContext()
        ctx.state = State.CONVERTING
        ctx.backspace_hold_active = True
        ctx.chars_in_buffer = 5

        assert engine.choose_mode(ctx) == "selection"

    def test_selection_when_empty_buffer_and_no_selection(self):
        engine, _, sel, _, _, _ = _make_engine()
        sel.has_fresh_selection.return_value = False
        ctx = StateContext()
        ctx.chars_in_buffer = 0

        assert engine.choose_mode(ctx) == "selection"

    def test_fresh_selection_takes_precedence_over_buffer(self):
        """If both chars_in_buffer > 0 and fresh selection, prefer selection."""
        engine, _, sel, _, _, _ = _make_engine()
        sel.has_fresh_selection.return_value = True
        ctx = StateContext()
        ctx.chars_in_buffer = 5

        assert engine.choose_mode(ctx) == "selection"


# ---------------------------------------------------------------------------
# convert() tests
# ---------------------------------------------------------------------------

class TestConvertRetype:
    def test_retype_mode_deletes_and_retypes(self):
        engine, xkb, sel, vk, _, sys_ = _make_engine()
        sel.has_fresh_selection.return_value = False
        ctx = StateContext()
        ctx.chars_in_buffer = 3
        ctx.event_buffer = [_make_event(16, 1), _make_event(17, 1), _make_event(18, 1)]

        result = engine.convert(ctx)

        assert result is True
        vk.tap_key.assert_called_once_with(14, 3)  # KEY_BACKSPACE, 3 times
        xkb.switch_layout.assert_called_once()
        vk.replay_events.assert_called()


class TestConvertSelection:
    def test_selection_mode_converts_text(self):
        engine, xkb, sel, vk, _, sys_ = _make_engine()
        sel.has_fresh_selection.return_value = True
        sel.get_selection.return_value = SelectionInfo(
            text="ghbdtn", owner_id=1, timestamp=time.time()
        )
        ctx = StateContext()
        ctx.chars_in_buffer = 0

        result = engine.convert(ctx)

        assert result is True
        sel.replace_selection.assert_called_once_with("привет")
        xkb.switch_layout.assert_called_once()


class TestConvertReturnsFalse:
    """convert() must propagate False from the underlying mode."""

    def test_retype_empty_buffer_returns_false(self):
        engine, xkb, sel, vk, _, sys_ = _make_engine()
        sel.has_fresh_selection.return_value = False
        ctx = StateContext()
        ctx.chars_in_buffer = 0  # fallback to selection
        sel.get_selection.return_value = SelectionInfo(text="", owner_id=0, timestamp=0.0)

        result = engine.convert(ctx)
        assert result is False

    def test_selection_empty_text_returns_false(self):
        engine, xkb, sel, vk, _, sys_ = _make_engine()
        sel.has_fresh_selection.return_value = True
        sel.get_selection.return_value = SelectionInfo(text="", owner_id=0, timestamp=0.0)
        ctx = StateContext()
        ctx.chars_in_buffer = 0

        result = engine.convert(ctx)
        assert result is False
