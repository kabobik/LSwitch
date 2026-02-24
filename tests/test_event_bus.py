"""Tests for EventBus."""

from __future__ import annotations

from lswitch.core.event_bus import EventBus
from lswitch.core.events import Event, EventType


def test_subscribe_and_publish():
    bus = EventBus()
    received = []
    bus.subscribe(EventType.KEY_PRESS, received.append)
    event = Event(type=EventType.KEY_PRESS, data=None, timestamp=0.0)
    bus.publish(event)
    assert received == [event]


def test_unsubscribe():
    bus = EventBus()
    received = []
    handler = received.append
    bus.subscribe(EventType.KEY_PRESS, handler)
    bus.unsubscribe(EventType.KEY_PRESS, handler)
    bus.publish(Event(type=EventType.KEY_PRESS, data=None, timestamp=0.0))
    assert received == []


def test_handler_exception_does_not_crash_bus():
    bus = EventBus()

    def bad_handler(e):
        raise RuntimeError("oops")

    received = []
    bus.subscribe(EventType.KEY_PRESS, bad_handler)
    bus.subscribe(EventType.KEY_PRESS, received.append)
    bus.publish(Event(type=EventType.KEY_PRESS, data=None, timestamp=0.0))
    assert len(received) == 1  # second handler still ran


def test_no_handlers_does_not_raise():
    bus = EventBus()
    bus.publish(Event(type=EventType.DOUBLE_SHIFT, data=None, timestamp=0.0))
