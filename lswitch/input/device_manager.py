"""DeviceManager — hot-plug monitoring of evdev input devices.

Ported from archive/lswitch/device_manager.py (production-ready).
"""

from __future__ import annotations

import selectors
import threading
import logging
from typing import Dict, Optional, Callable, Iterator, Any

try:
    import evdev
    from evdev import ecodes

    EVDEV_AVAILABLE = True
except ImportError:  # pragma: no cover
    evdev = None  # type: ignore[assignment]
    ecodes = None  # type: ignore[assignment]
    EVDEV_AVAILABLE = False

from lswitch.input.device_filter import should_include_device

logger = logging.getLogger(__name__)


class DeviceManager:
    """Manages physical evdev input devices with hot-plug support."""

    def __init__(
        self,
        debug: bool = False,
        on_device_added: Optional[Callable] = None,
        on_device_removed: Optional[Callable] = None,
    ):
        self.debug = debug
        self.devices: Dict[str, Any] = {}
        self.selector = selectors.DefaultSelector()
        self.on_device_added = on_device_added
        self.on_device_removed = on_device_removed
        self._lock = threading.Lock()
        self._virtual_kb_name: Optional[str] = None

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def set_virtual_kb_name(self, name: str) -> None:
        """Set the virtual keyboard name so it's excluded from scanning."""
        self._virtual_kb_name = name

    @property
    def device_count(self) -> int:
        """Number of currently tracked devices."""
        return len(self.devices)

    # ------------------------------------------------------------------
    # Device scanning
    # ------------------------------------------------------------------

    def scan_devices(self) -> int:
        """Scan ``/dev/input/`` and register suitable devices.

        Returns:
            Number of newly registered devices.
        """
        if not EVDEV_AVAILABLE:  # pragma: no cover
            logger.warning("evdev not available — cannot scan devices")
            return 0

        count = 0
        for path in evdev.list_devices():
            if self._try_add_device(path):
                count += 1
        return count

    def _is_suitable_device(self, device: Any) -> bool:
        """Return True if *device* should be monitored."""
        # Exclude our own virtual keyboard
        if self._virtual_kb_name and self._virtual_kb_name in device.name:
            return False

        # Exclude known virtual / unwanted devices via device_filter
        if not should_include_device(device.name):
            return False

        caps = device.capabilities()
        if ecodes.EV_KEY not in caps:
            return False

        keys = caps.get(ecodes.EV_KEY, [])

        is_keyboard = ecodes.KEY_A in keys
        is_mouse = ecodes.BTN_LEFT in keys or ecodes.BTN_RIGHT in keys

        return is_keyboard or is_mouse

    def _try_add_device(self, path: str) -> bool:
        """Try to open and register device at *path*.

        Returns:
            True if the device was successfully added.
        """
        with self._lock:
            if path in self.devices:
                return False

            try:
                device = evdev.InputDevice(path)
                if not self._is_suitable_device(device):
                    device.close()
                    return False

                self.devices[path] = device
                self.selector.register(device, selectors.EVENT_READ)

                if self.debug:
                    logger.info("Device added: %s (%s)", device.name, path)

                if self.on_device_added:
                    try:
                        self.on_device_added(device)
                    except Exception:
                        pass

                return True

            except (OSError, PermissionError) as exc:
                if self.debug:
                    logger.warning("Cannot add %s: %s", path, exc)
                return False

    # ------------------------------------------------------------------
    # Device removal
    # ------------------------------------------------------------------

    def remove_device(self, path: str) -> bool:
        """Safely remove device at *path*.

        Returns:
            True if the device was present and removed.
        """
        with self._lock:
            device = self.devices.pop(path, None)
            if device is None:
                return False

            try:
                self.selector.unregister(device)
            except Exception:
                pass

            device_name = getattr(device, "name", "unknown")
            try:
                device.close()
            except Exception:
                pass

            if self.debug:
                logger.info("Device removed: %s (%s)", device_name, path)

            if self.on_device_removed:
                try:
                    self.on_device_removed(device)
                except Exception:
                    pass

            return True

    # ------------------------------------------------------------------
    # Event reading
    # ------------------------------------------------------------------

    def handle_read_error(self, device: Any, error: Exception) -> None:
        """Handle a read error — graceful removal."""
        path = device.path
        if self.debug:
            logger.warning("Read error on %s: %s", device.name, error)
        self.remove_device(path)

    def get_events(self, timeout: float = 0.1) -> Iterator[tuple]:
        """Yield ``(device, event)`` tuples from ready devices."""
        ready = self.selector.select(timeout=timeout)
        for key, _mask in ready:
            device = key.fileobj
            try:
                for event in device.read():
                    yield (device, event)
            except (OSError, IOError) as exc:
                self.handle_read_error(device, exc)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Release all resources."""
        with self._lock:
            for path in list(self.devices.keys()):
                device = self.devices.pop(path, None)
                if device:
                    try:
                        self.selector.unregister(device)
                    except Exception:
                        pass
                    try:
                        device.close()
                    except Exception:
                        pass

            try:
                self.selector.close()
            except Exception:
                pass

    def __enter__(self) -> "DeviceManager":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        self.close()
        return False
