"""ConfigDialog — settings window."""

from __future__ import annotations

# TODO: implement using PyQt5/PyQt6 QDialog


class ConfigDialog:
    """Settings dialog opened from the tray menu."""

    def __init__(self, config=None, event_bus=None):
        self.config = config
        self.event_bus = event_bus

    def show(self) -> None:
        raise NotImplementedError
