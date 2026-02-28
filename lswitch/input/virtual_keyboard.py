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

    # Delay between press and release, and between successive key taps.
    # Without a pause many applications (GTK, Qt, X terminals) drop events
    # when they arrive faster than the input processing loop runs.
    KEY_PRESS_DELAY  = 0.001   # 1 ms between press and release
    KEY_REPEAT_DELAY = 0.001   # 1 ms between successive key taps

    def tap_key(self, keycode: int, n_times: int = 1) -> None:
        """Press and release a keycode n times."""
        for i in range(n_times):
            self._write(keycode, 1)
            time.sleep(self.KEY_PRESS_DELAY)
            self._write(keycode, 0)
            if i < n_times - 1:
                time.sleep(self.KEY_REPEAT_DELAY)

    # evdev keycode for Left Shift — used to replay shifted keys.
    KEY_LEFTSHIFT = 42

    def replay_events(self, events: list) -> None:
        """Replay a list of evdev InputEvent objects.

        If an event has value=1 (key press) and no matching release follows in
        the list, a synthetic release (value=0) is appended automatically.
        This prevents the kernel from generating infinite auto-repeat events.

        If an event carries ``shifted=True`` (set by app.py when Shift was held
        during the original keypress), the replay wraps that key with a
        synthetic Shift press/release so the target application sees an
        uppercase letter in the new layout.
        """
        # Build a set of codes that get a release in the list already
        released_codes: set[int] = set()
        for ev in events:
            if getattr(ev, 'value', None) == 0:
                released_codes.add(getattr(ev, 'code', -1))

        for ev in events:
            code = getattr(ev, 'code', None)
            value = getattr(ev, 'value', None)
            if code is None or value is None:
                continue
            # Use strict identity check so that MagicMock attrs (truthy but
            # not literally True) don't accidentally trigger Shift injection.
            shifted = getattr(ev, 'shifted', False) is True
            if shifted:
                self._write(self.KEY_LEFTSHIFT, 1)
                time.sleep(self.KEY_PRESS_DELAY)
            self._write(code, value)
            # Send synthetic release if this is a press without a paired release
            if value == 1 and code not in released_codes:
                time.sleep(self.KEY_PRESS_DELAY)
                self._write(code, 0)
            if shifted:
                self._write(self.KEY_LEFTSHIFT, 0)
            time.sleep(self.KEY_REPEAT_DELAY)

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
