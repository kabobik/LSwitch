"""ctypes bindings to libX11 / libxkbfile for XKB operations.

NOTE: Low-level XKB structs and function signatures.
Implementation ported from archive/lswitch/core.py XKB section.
"""

from __future__ import annotations

import ctypes
import ctypes.util


def _load_libx11():
    name = ctypes.util.find_library("X11")
    if name:
        return ctypes.cdll.LoadLibrary(name)
    return None


libX11 = _load_libx11()


class XkbStateRec(ctypes.Structure):
    """Minimal XkbStateRec — only the fields we need."""
    _fields_ = [
        ("group", ctypes.c_ubyte),
        ("locked_group", ctypes.c_ubyte),
        ("base_group", ctypes.c_ushort),
        ("latched_group", ctypes.c_ushort),
        ("mods", ctypes.c_ubyte),
        ("base_mods", ctypes.c_ubyte),
        ("latched_mods", ctypes.c_ubyte),
        ("locked_mods", ctypes.c_ubyte),
        ("compat_state", ctypes.c_ubyte),
        ("grab_mods", ctypes.c_ubyte),
        ("compat_grab_mods", ctypes.c_ubyte),
        ("lookup_mods", ctypes.c_ubyte),
        ("compat_lookup_mods", ctypes.c_ubyte),
        ("ptr_buttons", ctypes.c_ushort),
    ]


XKB_USE_CORE_KBD = 0x0100


def get_current_group(display_ptr) -> int:
    """Return current XKB group index (0-based)."""
    state = XkbStateRec()
    if libX11 and libX11.XkbGetState(display_ptr, XKB_USE_CORE_KBD, ctypes.byref(state)) == 0:
        return int(state.group)
    return 0


def lock_group(display_ptr, group: int) -> None:
    """Switch to XKB group by index."""
    if libX11:
        libX11.XkbLockGroup(display_ptr, XKB_USE_CORE_KBD, group)
        libX11.XFlush(display_ptr)
