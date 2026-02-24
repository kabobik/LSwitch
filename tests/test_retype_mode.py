"""Tests for RetypeMode."""

from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest

from lswitch.core.modes import RetypeMode, KEY_BACKSPACE, _SyntheticEvent
from lswitch.core.states import StateContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(code: int, value: int):
    """Create an event-like object with .code and .value."""
    ev = MagicMock()
    ev.code = code
    ev.value = value
    return ev


def _make_retype(mock_vk=None, mock_xkb=None, mock_sys=None, debug=False):
    vk = mock_vk or MagicMock()
    xkb = mock_xkb or MagicMock()
    sys = mock_sys or MagicMock()
    return RetypeMode(vk, xkb, sys, debug=debug), vk, xkb, sys


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRetypeModeDeletesCorrectly:
    def test_deletes_correct_number_of_chars(self):
        retype, vk, xkb, _ = _make_retype()
        ctx = StateContext()
        ctx.chars_in_buffer = 5
        ctx.event_buffer = [_make_event(16, 1)]  # 'q' press

        retype.execute(ctx)

        vk.tap_key.assert_called_once_with(KEY_BACKSPACE, 5)

    def test_switches_layout(self):
        retype, vk, xkb, _ = _make_retype()
        ctx = StateContext()
        ctx.chars_in_buffer = 3
        ctx.event_buffer = [_make_event(16, 1)]

        retype.execute(ctx)

        xkb.switch_layout.assert_called_once()

    def test_replays_events(self):
        retype, vk, xkb, _ = _make_retype()
        events = [_make_event(16, 1), _make_event(16, 0), _make_event(17, 1), _make_event(17, 0)]
        ctx = StateContext()
        ctx.chars_in_buffer = 2
        ctx.event_buffer = events

        retype.execute(ctx)

        # replay_events should be called with a copy of the saved events
        vk.replay_events.assert_called()
        replayed = vk.replay_events.call_args_list[0][0][0]
        assert len(replayed) == 4


class TestRetypeModeShiftRelease:
    def test_no_shift_release_when_no_shift_in_buffer(self):
        """Key v2 fix: Shift release must NOT be sent if buffer had no Shift press."""
        retype, vk, xkb, _ = _make_retype()
        events = [_make_event(16, 1), _make_event(16, 0)]  # just 'q' press/release
        ctx = StateContext()
        ctx.chars_in_buffer = 1
        ctx.event_buffer = events

        retype.execute(ctx)

        # replay_events should be called exactly once (for the actual events)
        assert vk.replay_events.call_count == 1

    def test_shift_release_sent_when_shift_in_buffer(self):
        """Shift release IS sent only for UNPAIRED Shift press events.

        When the buffer contains both Shift press AND release, the replay
        already handles the release — no synthetic duplicate is needed.
        """
        retype, vk, xkb, _ = _make_retype()
        events = [
            _make_event(42, 1),   # LShift press
            _make_event(16, 1),   # 'q' press
            _make_event(16, 0),   # 'q' release
            _make_event(42, 0),   # LShift release (paired)
        ]
        ctx = StateContext()
        ctx.chars_in_buffer = 1
        ctx.event_buffer = events

        retype.execute(ctx)

        # Shift press is paired with release → no extra synthetic release
        assert vk.replay_events.call_count == 1

    def test_no_shift_state_leak(self):
        """After execute, no lingering shift state should remain.

        Verify that if a Shift press is in the buffer without a paired release,
        it is still passed to replay_events.  VirtualKeyboard.replay_events()
        is responsible for appending the synthetic release (auto-release logic
        was moved there to avoid the double-release / XKB toggle bug).
        """
        retype, vk, xkb, _ = _make_retype()
        events = [
            _make_event(42, 1),   # LShift press
            _make_event(16, 1),   # 'Q' press
            _make_event(16, 0),   # 'Q' release
            # Note: NO LShift release in the buffer
        ]
        ctx = StateContext()
        ctx.chars_in_buffer = 1
        ctx.event_buffer = events

        retype.execute(ctx)

        # replay_events is called exactly once; auto-release of unpaired keys
        # is now handled inside VirtualKeyboard.replay_events() itself.
        assert vk.replay_events.call_count == 1
        replayed = vk.replay_events.call_args_list[0][0][0]
        # The shift press must be present so VirtualKeyboard can add release
        assert any(e.code == 42 and e.value == 1 for e in replayed)


class TestRetypeModeEmptyBuffer:
    def test_empty_buffer_returns_false(self):
        retype, vk, xkb, _ = _make_retype()
        ctx = StateContext()
        ctx.chars_in_buffer = 0

        result = retype.execute(ctx)

        assert result is False
        vk.tap_key.assert_not_called()
        xkb.switch_layout.assert_not_called()

    def test_negative_buffer_returns_false(self):
        retype, vk, xkb, _ = _make_retype()
        ctx = StateContext()
        ctx.chars_in_buffer = -1

        result = retype.execute(ctx)

        assert result is False


class TestRetypeModeReturnValue:
    def test_returns_true_on_success(self):
        retype, vk, xkb, _ = _make_retype()
        ctx = StateContext()
        ctx.chars_in_buffer = 3
        ctx.event_buffer = [_make_event(16, 1)]

        result = retype.execute(ctx)

        assert result is True


class TestRetypeModeRightShift:
    """Conditional Shift release works for KEY_RIGHTSHIFT (54) too."""

    def test_rshift_unpaired_sends_release(self):
        """Unpaired RShift is passed to replay_events; VK handles auto-release."""
        retype, vk, xkb, _ = _make_retype()
        events = [
            _make_event(54, 1),   # RShift press (unpaired)
            _make_event(16, 1),   # 'q' press
            _make_event(16, 0),   # 'q' release
        ]
        ctx = StateContext()
        ctx.chars_in_buffer = 1
        ctx.event_buffer = events

        retype.execute(ctx)

        # One call to replay_events; auto-release is VK's responsibility
        assert vk.replay_events.call_count == 1
        replayed = vk.replay_events.call_args_list[0][0][0]
        # RShift press must be in the replayed list
        assert any(e.code == 54 and e.value == 1 for e in replayed)

    def test_rshift_paired_no_extra_release(self):
        retype, vk, xkb, _ = _make_retype()
        events = [
            _make_event(54, 1),   # RShift press
            _make_event(16, 1),   # 'q' press
            _make_event(16, 0),   # 'q' release
            _make_event(54, 0),   # RShift release (paired)
        ]
        ctx = StateContext()
        ctx.chars_in_buffer = 1
        ctx.event_buffer = events

        retype.execute(ctx)

        # Paired → no synthetic release
        assert vk.replay_events.call_count == 1
