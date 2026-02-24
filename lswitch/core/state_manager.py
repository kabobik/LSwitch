"""StateManager — processes events and drives state machine."""

from __future__ import annotations

import logging
import time

from lswitch.core.states import State, StateContext
from lswitch.core.transitions import can_transition, next_state

logger = logging.getLogger(__name__)


class StateManager:
    """Maintains application state and coordinates transitions."""

    def __init__(self, double_click_timeout: float = 0.3, debug: bool = False):
        self.context = StateContext()
        self.double_click_timeout = double_click_timeout
        self.debug = debug

    @property
    def state(self) -> State:
        return self.context.state

    def _transition(self, event_name: str) -> bool:
        if not can_transition(self.context.state, event_name):
            if self.debug:
                logger.debug("Ignored transition %r from %s", event_name, self.context.state)
            return False
        new_state = next_state(self.context.state, event_name)
        if self.debug:
            logger.debug("State: %s → %s (on %r)", self.context.state, new_state, event_name)
        self.context.state = new_state
        return True

    def on_key_press(self, keycode: int) -> None:
        self._transition("key_press")

    def on_shift_down(self) -> None:
        self.context.shift_pressed = True
        self.context.last_shift_time = time.time()
        self._transition("shift_down")

    def on_shift_up(self) -> bool:
        """Returns True if double-shift was detected."""
        self.context.shift_pressed = False
        now = time.time()
        delta = now - self.context.last_shift_time
        if delta < self.double_click_timeout:
            self._transition("shift_up_double")
            return True
        else:
            self.context.last_shift_time = now
            self._transition("shift_up_single")
            return False

    def on_backspace_hold(self) -> None:
        self.context.backspace_hold_at = time.time()
        self.context.backspace_hold_active = True
        self._transition("backspace_hold")

    def on_navigation(self) -> None:
        self.context.backspace_hold_active = False
        self.context.reset()
        self._transition("navigation")

    def on_mouse_click(self) -> None:
        self.context.backspace_hold_active = False
        self.context.reset()
        self._transition("mouse_click")

    def on_conversion_complete(self) -> None:
        self.context.backspace_hold_active = False
        self._transition("complete")

    def on_conversion_cancelled(self) -> None:
        self.context.backspace_hold_active = False
        self._transition("cancelled")
