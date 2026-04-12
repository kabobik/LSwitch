"""UdevMonitor — watches for device plug/unplug events via pyudev."""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

try:
    import pyudev

    PYUDEV_AVAILABLE = True
except ImportError:  # pragma: no cover
    pyudev = None  # type: ignore[assignment]
    PYUDEV_AVAILABLE = False

logger = logging.getLogger(__name__)


class UdevMonitor:
    """Monitors udev events and notifies on device changes.

    Parameters:
        on_added:   Called with device path (``/dev/input/eventX``) on plug.
        on_removed: Called with device path on unplug.
    """

    def __init__(
        self,
        on_added: Callable[[str], None] | None = None,
        on_removed: Callable[[str], None] | None = None,
    ):
        self.on_added = on_added
        self.on_removed = on_removed
        self._thread: threading.Thread | None = None
        self._running = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> bool:
        """Start the udev monitoring daemon thread.

        Returns:
            True if the thread was started, False if pyudev is unavailable.
        """
        if not PYUDEV_AVAILABLE:
            logger.warning("pyudev not installed — hot-plug disabled")
            return False

        if self._thread is not None and self._thread.is_alive():
            return True

        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        """Signal the monitoring loop to stop."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    @property
    def is_running(self) -> bool:
        return self._running and self._thread is not None and self._thread.is_alive()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run(self) -> None:
        """Main monitoring loop — runs in a daemon thread."""
        try:
            context = pyudev.Context()
            monitor = pyudev.Monitor.from_netlink(context)
            monitor.filter_by(subsystem="input")
            monitor.start()

            while self._running:
                device = monitor.poll(timeout=1)
                if device is None:
                    continue

                dev_path = device.device_node
                if not dev_path or not dev_path.startswith("/dev/input/event"):
                    continue

                if device.action == "add":
                    time.sleep(0.1)  # let the device initialise
                    if self.on_added:
                        try:
                            self.on_added(dev_path)
                        except Exception as exc:
                            logger.debug("on_added callback error: %s", exc)

                elif device.action == "remove":
                    if self.on_removed:
                        try:
                            self.on_removed(dev_path)
                        except Exception as exc:
                            logger.debug("on_removed callback error: %s", exc)

        except Exception as exc:
            logger.error("UdevMonitor error: %s", exc)
