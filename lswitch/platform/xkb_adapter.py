"""IXKBAdapter interface, LayoutInfo dataclass and X11XKBAdapter implementation."""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class LayoutInfo:
    name: str       # 'en', 'ru'
    index: int      # XKB group index: 0, 1, ...
    xkb_name: str   # 'us', 'ru' (for setxkbmap)


class IXKBAdapter(ABC):
    @abstractmethod
    def get_layouts(self) -> list[LayoutInfo]: ...

    @abstractmethod
    def get_current_layout(self) -> LayoutInfo: ...

    @abstractmethod
    def switch_layout(self, target: Optional[LayoutInfo] = None) -> LayoutInfo: ...

    @abstractmethod
    def keycode_to_char(self, keycode: int, layout: LayoutInfo, shift: bool = False) -> str: ...


# ---------------------------------------------------------------------------
# Cyrillic keysym name → character map
# ---------------------------------------------------------------------------
_CYRILLIC_MAP: dict[str, str] = {
    # Lowercase
    "a": "а", "be": "б", "tse": "ц", "de": "д",
    "ie": "е", "ef": "ф", "ghe": "г", "ha": "х",
    "i": "и", "shorti": "й", "ka": "к", "el": "л",
    "em": "м", "en": "н", "o": "о", "pe": "п",
    "ya": "я", "er": "р", "es": "с", "te": "т",
    "u": "у", "zhe": "ж", "ve": "в", "softsign": "ь",
    "yeru": "ы", "ze": "з", "sha": "ш", "e": "э",
    "shcha": "щ", "che": "ч", "hardsign": "ъ",
    "yu": "ю", "io": "ё",
    # Uppercase
    "A": "А", "BE": "Б", "TSE": "Ц", "DE": "Д",
    "IE": "Е", "EF": "Ф", "GHE": "Г", "HA": "Х",
    "I": "И", "SHORTI": "Й", "KA": "К", "EL": "Л",
    "EM": "М", "EN": "Н", "O": "О", "PE": "П",
    "YA": "Я", "ER": "Р", "ES": "С", "TE": "Т",
    "U": "У", "ZHE": "Ж", "VE": "В", "SOFTSIGN": "Ь",
    "YERU": "Ы", "ZE": "З", "SHA": "Ш", "E": "Э",
    "SHCHA": "Щ", "CHE": "Ч", "HARDSIGN": "Ъ",
    "YU": "Ю", "IO": "Ё",
}


# ---------------------------------------------------------------------------
# X11XKBAdapter — concrete implementation using libX11 ctypes bindings
# ---------------------------------------------------------------------------

class X11XKBAdapter(IXKBAdapter):
    """Real XKB adapter talking to X11 via ctypes.

    Uses libX11 directly: XkbGetState, XkbLockGroup, XkbKeycodeToKeysym.
    Falls back to setxkbmap for layout discovery.
    """

    XKB_USE_CORE_KBD = 0x0100

    def __init__(self, debug: bool = False) -> None:
        self._debug = debug
        self._libX11 = self._load_libx11()
        self._xkb_available = self._libX11 is not None
        self._layouts: list[LayoutInfo] | None = None
        self._dpy = None  # cached Display*

    # -- private helpers ----------------------------------------------------

    @staticmethod
    def _load_libx11():
        """Load and configure libX11 ctypes bindings."""
        try:
            path = ctypes.util.find_library("X11")
            if not path:
                return None
            lib = ctypes.cdll.LoadLibrary(path)

            # XOpenDisplay / XCloseDisplay
            lib.XOpenDisplay.argtypes = [ctypes.c_char_p]
            lib.XOpenDisplay.restype = ctypes.c_void_p
            lib.XCloseDisplay.argtypes = [ctypes.c_void_p]
            lib.XCloseDisplay.restype = ctypes.c_int

            # XkbGetState
            from lswitch.platform.xkb_bindings import XkbStateRec
            lib.XkbGetState.argtypes = [
                ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(XkbStateRec),
            ]
            lib.XkbGetState.restype = ctypes.c_int

            # XkbLockGroup
            lib.XkbLockGroup.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint]
            lib.XkbLockGroup.restype = ctypes.c_int

            # XFlush
            lib.XFlush.argtypes = [ctypes.c_void_p]
            lib.XFlush.restype = ctypes.c_int

            # XkbKeycodeToKeysym
            lib.XkbKeycodeToKeysym.argtypes = [
                ctypes.c_void_p, ctypes.c_ubyte, ctypes.c_uint, ctypes.c_uint,
            ]
            lib.XkbKeycodeToKeysym.restype = ctypes.c_ulong

            # XKeysymToString
            lib.XKeysymToString.argtypes = [ctypes.c_ulong]
            lib.XKeysymToString.restype = ctypes.c_char_p

            return lib
        except Exception:
            return None

    def _get_display(self):
        """Return cached Display* or open a new connection."""
        if not self._xkb_available:
            return None
        if self._dpy is None:
            ptr = self._libX11.XOpenDisplay(None)
            self._dpy = ptr if ptr else None
        return self._dpy

    def close(self) -> None:
        """Close the cached X display connection if open."""
        if self._dpy is not None and self._xkb_available:
            self._libX11.XCloseDisplay(self._dpy)
            self._dpy = None

    def __del__(self) -> None:
        self.close()

    def _query_setxkbmap(self) -> list[str]:
        """Get layout list from ``setxkbmap -query``. Returns e.g. ['us', 'ru']."""
        try:
            r = subprocess.run(
                ["setxkbmap", "-query"],
                capture_output=True, text=True, timeout=2,
            )
            for line in r.stdout.splitlines():
                if line.startswith("layout:"):
                    raw = line.split(":", 1)[1].strip()
                    return [l.strip() for l in raw.split(",") if l.strip()]
        except Exception:
            pass
        return []

    @staticmethod
    def _xkb_name_to_short(xkb: str) -> str:
        """'us' → 'en', other names stay as-is."""
        return "en" if xkb.lower() == "us" else xkb.lower()

    # -- IXKBAdapter -------------------------------------------------------

    def get_layouts(self) -> list[LayoutInfo]:
        if self._layouts is not None:
            return self._layouts

        xkb_names = self._query_setxkbmap()
        if not xkb_names:
            xkb_names = ["us", "ru"]  # sensible default

        self._layouts = [
            LayoutInfo(
                name=self._xkb_name_to_short(xn),
                index=i,
                xkb_name=xn,
            )
            for i, xn in enumerate(xkb_names)
        ]
        return self._layouts

    def get_current_layout(self) -> LayoutInfo:
        layouts = self.get_layouts()
        if not self._xkb_available:
            return layouts[0]

        dpy = self._get_display()
        if not dpy:
            return layouts[0]
        from lswitch.platform.xkb_bindings import XkbStateRec
        state = XkbStateRec()
        status = self._libX11.XkbGetState(dpy, self.XKB_USE_CORE_KBD, ctypes.byref(state))
        if status == 0 and state.group < len(layouts):
            return layouts[state.group]
        return layouts[0]

    def switch_layout(self, target: Optional[LayoutInfo] = None) -> LayoutInfo:
        layouts = self.get_layouts()

        if target is not None:
            new_index = target.index
        else:
            current = self.get_current_layout()
            new_index = (current.index + 1) % len(layouts)

        if not self._xkb_available:
            return layouts[new_index] if new_index < len(layouts) else layouts[0]

        dpy = self._get_display()
        if not dpy:
            return layouts[new_index] if new_index < len(layouts) else layouts[0]
        self._libX11.XkbLockGroup(dpy, self.XKB_USE_CORE_KBD, new_index)
        self._libX11.XFlush(dpy)

        return layouts[new_index] if new_index < len(layouts) else layouts[0]

    def keycode_to_char(self, keycode: int, layout: LayoutInfo, shift: bool = False) -> str:
        if not self._xkb_available:
            return ""

        dpy = self._get_display()
        if not dpy:
            return ""
        x11_keycode = keycode + 8  # evdev → X11 offset
        group = layout.index
        level = 1 if shift else 0
        keysym = self._libX11.XkbKeycodeToKeysym(dpy, x11_keycode, group, level)
        if keysym == 0:
            return ""
        raw = self._libX11.XKeysymToString(keysym)
        if not raw:
            return ""
        name = raw.decode("utf-8")
        # Single ASCII character
        if len(name) == 1:
            return name
        # Cyrillic keysym names
        if name.startswith("Cyrillic_"):
            return _CYRILLIC_MAP.get(name[9:], "")
        return ""
