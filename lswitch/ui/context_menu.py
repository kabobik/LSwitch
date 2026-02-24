"""ContextMenu — right-click tray menu."""

from __future__ import annotations

# TODO: implement dynamic menu with checkboxes for auto_switch etc.


class ContextMenu:
    """Context menu shown on tray icon right-click."""

    def __init__(self, state_manager=None, config=None):
        self.state_manager = state_manager
        self.config = config

    def build(self):
        raise NotImplementedError
