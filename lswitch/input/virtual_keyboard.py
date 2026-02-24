"""VirtualKeyboard — wraps evdev.UInput for typing and event replay."""

from __future__ import annotations

import time
import logging
from typing import Any

logger = logging.getLogger(__name__)


class VirtualKeyboard:
    """Creates and manages a UInput virtual keyboard device."""

    DEVICE_NAME = "LSwitch Virtual Keyboard"

    def __init__(self, debug: bool = False):
        self.debug = debug
        self._uinput: Any = None
        self._open()

    def _open(self) -> None:
        try:
            import evdev
            self._uinput = evdev.UInput(name=self.DEVICE_NAME)
        except Exception as e:
            logger.warning("Cannot create UInput device: %s", e)

    def tap_key(self, keycode: int, n_times: int = 1) -> None:
        """Press and release a keycode n times."""
        for _ in range(n_times):
            self._write(keycode, 1)
            self._write(keycode, 0)

    def replay_events(self, events: list) -> None:
        """Replay a list of evdev InputEvent objects."""
        for ev in events:
            self._write(ev.code, ev.value)

    def _write(self, code: int, value: int) -> None:
        if self._uinput is None:
            return
        try:
            from evdev import ecodes
            self._uinput.write(ecodes.EV_KEY, code, value)
            self._uinput.syn()
        except Exception as e:
            logger.debug("VirtualKeyboard write error: %s", e)

    def close(self) -> None:
        if self._uinput is not None:
            try:
                self._uinput.close()
            except Exception:
                pass
            self._uinput = None
