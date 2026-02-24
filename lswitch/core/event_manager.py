"""EventManager — receives raw evdev events, classifies, publishes to EventBus."""

from __future__ import annotations

import logging
import time

from lswitch.core.event_bus import EventBus
from lswitch.core.events import Event, EventType, KeyEventData

logger = logging.getLogger(__name__)

# evdev keycodes (avoid hard dependency on evdev at import time)
KEY_LEFTSHIFT = 42
KEY_RIGHTSHIFT = 54
KEY_BACKSPACE = 14
KEY_SPACE = 57
KEY_ENTER = 28

NAVIGATION_KEYS = {103, 108, 105, 106, 102, 107, 104, 109, 15}  # arrows, home, end, pgup, pgdn, tab


class EventManager:
    """Receives raw evdev events and dispatches typed events to EventBus."""

    def __init__(self, event_bus: EventBus, debug: bool = False):
        self.bus = event_bus
        self.debug = debug

    def handle_raw_event(self, event, device_name: str = "") -> None:
        """Process a single evdev EV_KEY event."""
        try:
            from evdev import ecodes
            if event.type != ecodes.EV_KEY:
                return
        except Exception:
            if getattr(event, "type", None) != 1:  # EV_KEY = 1
                return

        code = event.code
        value = event.value  # 0=release, 1=press, 2=repeat

        data = KeyEventData(code=code, value=value, device_name=device_name)
        ts = time.time()

        if value == 1:
            self.bus.publish(Event(EventType.KEY_PRESS, data, ts))
        elif value == 0:
            self.bus.publish(Event(EventType.KEY_RELEASE, data, ts))
        elif value == 2:
            self.bus.publish(Event(EventType.KEY_REPEAT, data, ts))
