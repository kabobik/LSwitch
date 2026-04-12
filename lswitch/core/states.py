"""State definitions and StateContext dataclass."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto


class State(Enum):
    IDLE = auto()
    TYPING = auto()
    SHIFT_PRESSED = auto()
    CONVERTING = auto()
    BACKSPACE_HOLD = auto()


@dataclass
class StateContext:
    state: State = State.IDLE

    # Text and event buffers
    text_buffer: list[str] = field(default_factory=list)
    event_buffer: list = field(default_factory=list)
    chars_in_buffer: int = 0

    # Timing
    last_shift_time: float = 0.0
    backspace_hold_at: float = 0.0

    # Flags
    shift_pressed: bool = False
    backspace_repeats: int = 0
    backspace_hold_active: bool = False

    # Layout
    current_layout: str = "en"

    def reset(self) -> None:
        """Clear buffers and reset transient flags."""
        self.text_buffer.clear()
        self.event_buffer.clear()
        self.chars_in_buffer = 0
        self.last_shift_time = 0.0
        self.shift_pressed = False
        self.backspace_repeats = 0
        self.backspace_hold_active = False
