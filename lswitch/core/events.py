"""Typed event definitions (dataclasses)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


class EventType(Enum):
    # Input events
    KEY_PRESS = auto()
    KEY_RELEASE = auto()
    KEY_REPEAT = auto()
    # Gesture events
    DOUBLE_SHIFT = auto()
    BACKSPACE_HOLD = auto()
    MOUSE_CLICK = auto()
    MOUSE_RELEASE = auto()
    # Conversion lifecycle
    CONVERSION_START = auto()
    CONVERSION_COMPLETE = auto()
    CONVERSION_CANCELLED = auto()
    # Layout
    LAYOUT_CHANGED = auto()
    # Config
    CONFIG_CHANGED = auto()
    # App lifecycle
    APP_QUIT = auto()


@dataclass
class Event:
    type: EventType
    data: Any
    timestamp: float


@dataclass
class KeyEventData:
    code: int
    value: int          # 0=release, 1=press, 2=repeat
    device_name: str = ""
    shifted: bool = False   # True if Shift was held when this key was pressed


@dataclass
class ConversionEventData:
    original: str
    converted: str
    mode: str           # "retype" | "selection"
    is_auto: bool = False
