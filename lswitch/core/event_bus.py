"""EventBus — pub/sub for internal component communication."""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Callable

from lswitch.core.events import Event, EventType

logger = logging.getLogger(__name__)


class EventBus:
    """Lightweight synchronous pub/sub bus."""

    def __init__(self):
        self._handlers: dict[EventType, list[Callable[[Event], None]]] = defaultdict(list)

    def subscribe(self, event_type: EventType, handler: Callable[[Event], None]) -> None:
        """Register a handler for an event type."""
        self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: EventType, handler: Callable[[Event], None]) -> None:
        """Remove a previously registered handler."""
        try:
            self._handlers[event_type].remove(handler)
        except ValueError:
            pass

    def publish(self, event: Event) -> None:
        """Dispatch event to all registered handlers synchronously."""
        for handler in list(self._handlers.get(event.type, [])):
            try:
                handler(event)
            except Exception:
                logger.exception("EventBus handler error for %s", event.type)
