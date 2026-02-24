"""State transition rules and guard conditions."""

from __future__ import annotations

from lswitch.core.states import State


# Allowed transitions: {from_state: {event_name: to_state}}
TRANSITIONS: dict[State, dict[str, State]] = {
    State.IDLE: {
        "key_press": State.TYPING,
    },
    State.TYPING: {
        "shift_down": State.SHIFT_PRESSED,
        "backspace_hold": State.BACKSPACE_HOLD,
        "navigation": State.IDLE,
        "mouse_click": State.IDLE,
        "enter": State.IDLE,
    },
    State.SHIFT_PRESSED: {
        "shift_up_single": State.TYPING,
        "shift_up_double": State.CONVERTING,
        "key_press": State.TYPING,
    },
    State.BACKSPACE_HOLD: {
        "key_press": State.TYPING,
        "shift_up_double": State.CONVERTING,
        "navigation": State.IDLE,
        "mouse_click": State.IDLE,
    },
    State.CONVERTING: {
        "complete": State.IDLE,
        "cancelled": State.IDLE,
    },
}


def can_transition(from_state: State, event_name: str) -> bool:
    return event_name in TRANSITIONS.get(from_state, {})


def next_state(from_state: State, event_name: str) -> State:
    try:
        return TRANSITIONS[from_state][event_name]
    except KeyError:
        raise ValueError(f"No transition from {from_state!r} on event {event_name!r}")
