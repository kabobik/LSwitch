"""keycode ↔ char mapping helpers."""

from __future__ import annotations

# Basic QWERTY keycode → char map (evdev keycodes)
KEYCODE_TO_CHAR_EN: dict[int, str] = {
    2: "1", 3: "2", 4: "3", 5: "4", 6: "5", 7: "6", 8: "7", 9: "8", 10: "9", 11: "0",
    12: "-", 13: "=",
    16: "q", 17: "w", 18: "e", 19: "r", 20: "t", 21: "y", 22: "u", 23: "i", 24: "o",
    25: "p", 26: "[", 27: "]",
    30: "a", 31: "s", 32: "d", 33: "f", 34: "g", 35: "h", 36: "j", 37: "k", 38: "l",
    39: ";", 40: "'",
    44: "z", 45: "x", 46: "c", 47: "v", 48: "b", 49: "n", 50: "m", 51: ",", 52: ".", 53: "/",
    57: " ",
}


def keycode_to_char(keycode: int, layout: str = "en", shift: bool = False) -> str:
    """Return character for given keycode and layout. Empty string if unknown."""
    # TODO: full XKB-aware lookup will be in platform/xkb_adapter.py
    ch = KEYCODE_TO_CHAR_EN.get(keycode, "")
    if ch and shift:
        ch = ch.upper()
    return ch
