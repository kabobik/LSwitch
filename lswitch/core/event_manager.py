"""EventManager — receives raw evdev events, classifies, publishes to EventBus."""

from __future__ import annotations

import logging
import time

import lswitch.log  # registers TRACE level and logger.trace()
from lswitch.core.event_bus import EventBus
from lswitch.core.events import Event, EventType, KeyEventData

logger = logging.getLogger(__name__)

# evdev keycodes (avoid hard dependency on evdev at import time)
KEY_LEFTSHIFT = 42
KEY_RIGHTSHIFT = 54
SHIFT_KEYS = {KEY_LEFTSHIFT, KEY_RIGHTSHIFT}
KEY_BACKSPACE = 14
KEY_SPACE = 57
KEY_ENTER = 28

NAVIGATION_KEYS = {103, 108, 105, 106, 102, 107, 104, 109, 15}  # arrows, home, end, pgup, pgdn, tab
MOUSE_BUTTONS = {272, 273, 274}  # BTN_LEFT, BTN_RIGHT, BTN_MIDDLE

# EV_KEY type constant (used when evdev is not importable)
EV_KEY = 1


class EventManager:
    """Receives raw evdev events and dispatches typed events to EventBus."""

    def __init__(self, event_bus: EventBus, debug: bool = False):
        self.bus = event_bus
        self.debug = debug
        try:
            from evdev import ecodes
            self._ev_key = ecodes.EV_KEY
        except Exception:
            self._ev_key = EV_KEY

    def handle_raw_event(self, event, device_name: str = "") -> None:
        """Process a single evdev input event.

        Publishes KEY_PRESS / KEY_RELEASE / KEY_REPEAT for EV_KEY events and
        MOUSE_CLICK for mouse button presses.
        """
        event_type = getattr(event, "type", None)
        if event_type != self._ev_key:
            return

        code = event.code
        value = event.value  # 0=release, 1=press, 2=repeat

        if self.debug:
            val_name = {0: 'release', 1: 'press', 2: 'repeat'}.get(value, str(value))
            logger.trace("RawEvent: dev=%s code=%d (%s)", device_name, code, val_name)  # type: ignore[attr-defined]

        # Mouse button → MOUSE_CLICK on press
        if code in MOUSE_BUTTONS:
            if value == 1:
                self.bus.publish(Event(EventType.MOUSE_CLICK, KeyEventData(code=code, value=value, device_name=device_name), time.time()))
            return

        data = KeyEventData(code=code, value=value, device_name=device_name)
        ts = time.time()

        if value == 1:
            self.bus.publish(Event(EventType.KEY_PRESS, data, ts))
        elif value == 0:
            self.bus.publish(Event(EventType.KEY_RELEASE, data, ts))
        elif value == 2:
            self.bus.publish(Event(EventType.KEY_REPEAT, data, ts))
