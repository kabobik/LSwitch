"""Mutable session state for automatic conversion flows."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AutoConversionSessionState:
    """Tracks transient auto-conversion state shared by input and conversion flows."""

    last_marker: object | None = None
    sticky_events: list = field(default_factory=list)
    pending_space: bool = False

    def clear_marker(self) -> None:
        self.last_marker = None

    def clear_sticky_events(self) -> None:
        self.sticky_events = []

    def set_pending_space(self, value: bool) -> None:
        self.pending_space = bool(value)
