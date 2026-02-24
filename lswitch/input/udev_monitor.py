"""UdevMonitor — watches for device plug/unplug events."""

from __future__ import annotations

import threading
from typing import Callable

# TODO: implement using pyudev
# Placeholder to define the interface

class UdevMonitor:
    """Monitors udev events and notifies on device changes."""

    def __init__(
        self,
        on_added: Callable[[str], None] | None = None,
        on_removed: Callable[[str], None] | None = None,
    ):
        self.on_added = on_added
        self.on_removed = on_removed
        self._thread: threading.Thread | None = None
        self._running = False

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def _run(self) -> None:
        raise NotImplementedError("UdevMonitor._run() not yet implemented")
