"""TrayIcon — system tray icon with status indicator."""

from __future__ import annotations

# TODO: implement using PyQt5/PyQt6 QSystemTrayIcon


class TrayIcon:
    """System tray icon showing current layout and LSwitch status."""

    def __init__(self, event_bus=None):
        self.event_bus = event_bus

    def show(self) -> None:
        raise NotImplementedError

    def hide(self) -> None:
        raise NotImplementedError

    def set_layout(self, layout_name: str) -> None:
        """Update tray icon to reflect current layout."""
        raise NotImplementedError
