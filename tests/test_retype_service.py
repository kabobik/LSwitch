"""Tests for the shared typed-event retype primitive."""

from __future__ import annotations

from unittest.mock import MagicMock

from lswitch.core.retype_service import KEY_BACKSPACE, RetypeService
from lswitch.platform.xkb_adapter import LayoutInfo


def _event(code: int):
    event = MagicMock()
    event.code = code
    event.value = 1
    return event


def test_retype_events_switches_to_next_layout_with_positional_backspace_count():
    virtual_kb = MagicMock()
    xkb = MagicMock()
    events = [_event(16), _event(17)]
    service = RetypeService(virtual_kb, xkb, debug=True)

    ok = service.retype_events(
        events,
        delete_count=2,
        switch_to_next=True,
        before_replay_delay=0,
    )

    assert ok is True
    virtual_kb.tap_key.assert_called_once_with(KEY_BACKSPACE, 2)
    xkb.switch_layout.assert_called_once_with()
    virtual_kb.replay_events.assert_called_once()
    assert virtual_kb.replay_events.call_args[0][0] == events
    assert virtual_kb.replay_events.call_args[0][0] is not events


def test_retype_events_switches_to_explicit_target_with_keyword_backspace_count():
    virtual_kb = MagicMock()
    xkb = MagicMock()
    target = LayoutInfo(name="ru", index=1, xkb_name="ru")
    service = RetypeService(virtual_kb, xkb)

    ok = service.retype_events(
        [_event(16)],
        delete_count=3,
        target_layout=target,
        before_replay_delay=0,
        backspace_n_times_keyword=True,
    )

    assert ok is True
    virtual_kb.tap_key.assert_called_once_with(KEY_BACKSPACE, n_times=3)
    xkb.switch_layout.assert_called_once_with(target=target)
    virtual_kb.replay_events.assert_called_once()


def test_retype_events_returns_false_for_empty_delete_count():
    virtual_kb = MagicMock()
    xkb = MagicMock()
    service = RetypeService(virtual_kb, xkb)

    ok = service.retype_events([], delete_count=0, before_replay_delay=0)

    assert ok is False
    virtual_kb.tap_key.assert_not_called()
    xkb.switch_layout.assert_not_called()


def test_retype_events_returns_false_when_layout_switch_fails():
    virtual_kb = MagicMock()
    xkb = MagicMock()
    xkb.switch_layout.side_effect = RuntimeError("no layout")
    service = RetypeService(virtual_kb, xkb)

    ok = service.retype_events(
        [_event(16)],
        delete_count=1,
        switch_to_next=True,
        before_replay_delay=0,
    )

    assert ok is False
    virtual_kb.tap_key.assert_called_once_with(KEY_BACKSPACE, 1)
    virtual_kb.replay_events.assert_not_called()
