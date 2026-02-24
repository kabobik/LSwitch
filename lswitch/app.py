"""LSwitchApp — main application class, unifies service and GUI."""

from __future__ import annotations


class LSwitchApp:
    """Single-process application combining input daemon and tray GUI.

    Modes:
        headless=True  — no GUI, runs as a background service
        headless=False — with tray icon (default)
    """

    def __init__(self, headless: bool = False, debug: bool = False):
        self.headless = headless
        self.debug = debug

    def run(self):
        raise NotImplementedError("LSwitchApp.run() is not yet implemented")
