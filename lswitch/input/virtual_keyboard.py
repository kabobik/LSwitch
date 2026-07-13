"""VirtualKeyboard — wraps evdev.UInput for typing and event replay."""

from __future__ import annotations

import time
import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)


class VirtualKeyboard:
    """Creates and manages a UInput virtual keyboard device."""

    DEVICE_NAME = "LSwitch Virtual Keyboard"

    def __init__(self, debug: bool = False, timing: dict | None = None):
        self.debug = debug
        self._uinput: Any = None
        self._timing_lock = threading.RLock()
        self.reconfigure_timing(timing or {})
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

    def reconfigure_timing(self, timing: dict) -> None:
        """Atomically replace delays used by subsequent input operations."""
        press_delay = float(timing.get("key_press_delay", self.KEY_PRESS_DELAY))
        repeat_delay = float(timing.get("key_repeat_delay", self.KEY_REPEAT_DELAY))
        with self._timing_lock:
            self.KEY_PRESS_DELAY = press_delay
            self.KEY_REPEAT_DELAY = repeat_delay

    def set_debug(self, enabled: bool) -> None:
        self.debug = bool(enabled)

    def _timing_snapshot(self) -> tuple[float, float]:
        lock = getattr(self, "_timing_lock", None)
        if lock is None:
            return self.KEY_PRESS_DELAY, self.KEY_REPEAT_DELAY
        with lock:
            return self.KEY_PRESS_DELAY, self.KEY_REPEAT_DELAY

    _KEY_NAME_MAP: dict[str, int] = {
        "ctrl": 29,
        "control": 29,
        "leftctrl": 29,
        "rightctrl": 97,
        "shift": 42,
        "leftshift": 42,
        "rightshift": 54,
        "alt": 56,
        "leftalt": 56,
        "rightalt": 100,
        "super": 125,
        "meta": 125,
        "win": 125,
        "leftmeta": 125,
        "rightmeta": 126,
        "left": 105,
        "right": 106,
        "up": 103,
        "down": 108,
        "backspace": 14,
        "return": 28,
        "enter": 28,
        "space": 57,
        "tab": 15,
        "esc": 1,
        "escape": 1,
        "insert": 110,
        "ins": 110,
        "capslock": 58,
        "a": 30,
        "b": 48,
        "c": 46,
        "d": 32,
        "e": 18,
        "f": 33,
        "g": 34,
        "h": 35,
        "i": 23,
        "j": 36,
        "k": 37,
        "l": 38,
        "m": 50,
        "n": 49,
        "o": 24,
        "p": 25,
        "q": 16,
        "r": 19,
        "s": 31,
        "t": 20,
        "u": 22,
        "v": 47,
        "w": 17,
        "x": 45,
        "y": 21,
        "z": 44,
        "0": 11,
        "1": 2,
        "2": 3,
        "3": 4,
        "4": 5,
        "5": 6,
        "6": 7,
        "7": 8,
        "8": 9,
        "9": 10,
        "f1": 59,
        "f2": 60,
        "f3": 61,
        "f4": 62,
        "f5": 63,
        "f6": 64,
        "f7": 65,
        "f8": 66,
        "f9": 67,
        "f10": 68,
        "f11": 87,
        "f12": 88,
    }

    _SHIFTED_EN_TO_BASE: dict[str, str] = {
        "!": "1",
        "@": "2",
        "#": "3",
        "$": "4",
        "%": "5",
        "^": "6",
        "&": "7",
        "*": "8",
        "(": "9",
        ")": "0",
        "_": "-",
        "+": "=",
        "{": "[",
        "}": "]",
        ":": ";",
        '"': "'",
        "<": ",",
        ">": ".",
        "?": "/",
        "~": "`",
    }

    def tap_key(self, keycode: int, n_times: int = 1) -> None:
        """Press and release a keycode n times."""
        logger.debug("VirtualKeyboard: tap_key code=%s n_times=%s", keycode, n_times)
        press_delay, repeat_delay = self._timing_snapshot()
        for i in range(n_times):
            self._write(keycode, 1)
            time.sleep(press_delay)
            self._write(keycode, 0)
            if i < n_times - 1:
                time.sleep(repeat_delay)

    @classmethod
    def _key_name_to_code(cls, name: str) -> int:
        normalized = name.strip().lower().replace("_", "").replace("-", "")
        if normalized.startswith("key"):
            normalized = normalized[3:]
        try:
            return cls._KEY_NAME_MAP[normalized]
        except KeyError as exc:
            raise ValueError(f"Unsupported key name in sequence: {name!r}") from exc

    def send_combo(self, sequence: str) -> None:
        """Send a key combination such as ``ctrl+v`` via UInput."""
        names = [part.strip() for part in sequence.split("+") if part.strip()]
        if not names:
            return
        keycodes = [self._key_name_to_code(name) for name in names]
        press_delay, _ = self._timing_snapshot()
        logger.debug("VirtualKeyboard: send_combo sequence=%s codes=%s", sequence, keycodes)
        for code in keycodes:
            self._write(code, 1)
            time.sleep(press_delay)
        for code in reversed(keycodes):
            self._write(code, 0)
            time.sleep(press_delay)

    def type_text(self, text: str, layout_name: str = "en") -> bool:
        """Type text through the currently active keyboard layout.

        ``layout_name`` describes the layout that is active in the compositor,
        not the source language. For ``ru`` text we convert each desired
        character back to the physical US key that produces it on a Russian
        layout, then send that key via UInput.
        """
        if self._uinput is None:
            logger.debug("VirtualKeyboard: type_text skipped, UInput is unavailable")
            return False
        logger.debug(
            "VirtualKeyboard: type_text chars=%d layout=%s",
            len(text),
            layout_name,
        )
        press_delay, repeat_delay = self._timing_snapshot()
        for ch in text:
            key = self._text_char_to_key(ch, layout_name=layout_name)
            if key is None:
                logger.debug("VirtualKeyboard: unsupported text char %r", ch)
                return False
            code, shifted = key
            if shifted:
                self._write(self.KEY_LEFTSHIFT, 1)
                time.sleep(press_delay)
            self._write(code, 1)
            time.sleep(press_delay)
            self._write(code, 0)
            if shifted:
                self._write(self.KEY_LEFTSHIFT, 0)
            time.sleep(repeat_delay)
        return True

    @classmethod
    def _text_char_to_key(
        cls,
        ch: str,
        layout_name: str = "en",
    ) -> tuple[int, bool] | None:
        from lswitch.input.key_mapper import KEYCODE_TO_CHAR_EN

        if ch == "\n":
            return cls._KEY_NAME_MAP["enter"], False
        if ch == "\t":
            return cls._KEY_NAME_MAP["tab"], False

        physical = ch
        normalized_layout = (layout_name or "en").strip().lower()
        if normalized_layout.startswith("ru"):
            from lswitch.intelligence.maps import RU_TO_EN

            physical = RU_TO_EN.get(ch, ch)

        base_to_code = {value: code for code, value in KEYCODE_TO_CHAR_EN.items()}
        if physical in base_to_code:
            return base_to_code[physical], False

        if len(physical) == 1 and physical.isalpha():
            lowered = physical.lower()
            if lowered in base_to_code:
                return base_to_code[lowered], physical.isupper()

        base = cls._SHIFTED_EN_TO_BASE.get(physical)
        if base and base in base_to_code:
            return base_to_code[base], True

        return None

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
        logger.debug("VirtualKeyboard: replay_events %d events", len(events))
        press_delay, repeat_delay = self._timing_snapshot()
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
                time.sleep(press_delay)
            self._write(code, value)
            # Send synthetic release if this is a press without a paired release
            if value == 1 and code not in released_codes:
                time.sleep(press_delay)
                self._write(code, 0)
            if shifted:
                self._write(self.KEY_LEFTSHIFT, 0)
            time.sleep(repeat_delay)

    def _write(self, code: int, value: int) -> None:
        if self._uinput is None:
            return
        logger.trace("VK_out: write code=%s value=%s", code, value)  # type: ignore[attr-defined]
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
