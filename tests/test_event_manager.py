"""Tests for EventManager — raw event classification and publishing."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from lswitch.core.event_bus import EventBus
from lswitch.core.event_manager import EventManager, NAVIGATION_KEYS, MOUSE_BUTTONS
from lswitch.core.events import EventType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ev(type_: int, code: int, value: int):
    """Create a minimal event-like object."""
    return SimpleNamespace(type=type_, code=code, value=value)


EV_KEY = 1


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestKeyPress:
    def test_regular_key_press_publishes_key_press(self):
        bus = EventBus()
        mgr = EventManager(bus)
        received = []
        bus.subscribe(EventType.KEY_PRESS, lambda e: received.append(e))

        mgr.handle_raw_event(_ev(EV_KEY, 16, 1))  # 'q' press

        assert len(received) == 1
        assert received[0].type == EventType.KEY_PRESS
        assert received[0].data.code == 16
        assert received[0].data.value == 1


class TestKeyRelease:
    def test_shift_release_publishes_key_release(self):
        bus = EventBus()
        mgr = EventManager(bus)
        received = []
        bus.subscribe(EventType.KEY_RELEASE, lambda e: received.append(e))

        mgr.handle_raw_event(_ev(EV_KEY, 42, 0))  # LShift release

        assert len(received) == 1
        assert received[0].type == EventType.KEY_RELEASE
        assert received[0].data.code == 42

    def test_regular_release_publishes_key_release(self):
        bus = EventBus()
        mgr = EventManager(bus)
        received = []
        bus.subscribe(EventType.KEY_RELEASE, lambda e: received.append(e))

        mgr.handle_raw_event(_ev(EV_KEY, 16, 0))  # 'q' release

        assert len(received) == 1
        assert received[0].data.code == 16


class TestKeyRepeat:
    def test_repeat_publishes_key_repeat(self):
        bus = EventBus()
        mgr = EventManager(bus)
        received = []
        bus.subscribe(EventType.KEY_REPEAT, lambda e: received.append(e))

        mgr.handle_raw_event(_ev(EV_KEY, 14, 2))  # backspace repeat

        assert len(received) == 1
        assert received[0].type == EventType.KEY_REPEAT
        assert received[0].data.code == 14


class TestIgnoreNonEVKEY:
    def test_non_ev_key_ignored(self):
        bus = EventBus()
        mgr = EventManager(bus)
        received = []
        bus.subscribe(EventType.KEY_PRESS, lambda e: received.append(e))
        bus.subscribe(EventType.KEY_RELEASE, lambda e: received.append(e))
        bus.subscribe(EventType.KEY_REPEAT, lambda e: received.append(e))

        mgr.handle_raw_event(_ev(2, 16, 1))  # EV_REL (not EV_KEY)

        assert len(received) == 0

    def test_event_without_type_ignored(self):
        bus = EventBus()
        mgr = EventManager(bus)
        received = []
        bus.subscribe(EventType.KEY_PRESS, lambda e: received.append(e))

        class NoType:
            code = 16
            value = 1

        mgr.handle_raw_event(NoType())
        assert len(received) == 0


class TestNavigationKey:
    def test_navigation_key_press_publishes_key_press(self):
        bus = EventBus()
        mgr = EventManager(bus)
        received = []
        bus.subscribe(EventType.KEY_PRESS, lambda e: received.append(e))

        # Arrow up = 103
        mgr.handle_raw_event(_ev(EV_KEY, 103, 1))

        assert len(received) == 1
        assert received[0].data.code == 103

    def test_navigation_key_release_publishes_key_release(self):
        bus = EventBus()
        mgr = EventManager(bus)
        received = []
        bus.subscribe(EventType.KEY_RELEASE, lambda e: received.append(e))

        mgr.handle_raw_event(_ev(EV_KEY, 105, 0))  # Arrow left release

        assert len(received) == 1
        assert received[0].data.code == 105


class TestMouseButton:
    def test_mouse_press_publishes_mouse_click(self):
        bus = EventBus()
        mgr = EventManager(bus)
        received = []
        bus.subscribe(EventType.MOUSE_CLICK, lambda e: received.append(e))

        mgr.handle_raw_event(_ev(EV_KEY, 272, 1))  # BTN_LEFT press

        assert len(received) == 1
        assert received[0].type == EventType.MOUSE_CLICK

    def test_mouse_release_publishes_mouse_release(self):
        """Mouse button release triggers MOUSE_RELEASE event."""
        bus = EventBus()
        mgr = EventManager(bus)
        received = []
        bus.subscribe(EventType.MOUSE_RELEASE, lambda e: received.append(e))

        mgr.handle_raw_event(_ev(EV_KEY, 272, 0))  # BTN_LEFT release

        assert len(received) == 1
        assert received[0].type == EventType.MOUSE_RELEASE

    def test_mouse_release_not_published_as_click(self):
        """Mouse release must NOT trigger MOUSE_CLICK."""
        bus = EventBus()
        mgr = EventManager(bus)
        received = []
        bus.subscribe(EventType.MOUSE_CLICK, lambda e: received.append(e))

        mgr.handle_raw_event(_ev(EV_KEY, 272, 0))  # BTN_LEFT release

        assert len(received) == 0

    def test_mouse_does_not_leak_to_key_press(self):
        bus = EventBus()
        mgr = EventManager(bus)
        key_events = []
        bus.subscribe(EventType.KEY_PRESS, lambda e: key_events.append(e))

        mgr.handle_raw_event(_ev(EV_KEY, 272, 1))

        assert len(key_events) == 0
