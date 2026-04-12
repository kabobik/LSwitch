"""ctypes bindings to libX11 / libxkbfile for XKB operations.

NOTE: Low-level XKB structs and constants.
Implementation ported from archive/lswitch/core.py XKB section.
"""

from __future__ import annotations

import ctypes


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
