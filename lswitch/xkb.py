"""XKB / X11 helper utilities for LSwitch.

Contains functions to discover layouts and translate keycodes using XKB
and libX11. Designed to be imported and used from `lswitch.core` so the
heavy platform-specific logic is isolated and testable.
"""

from __future__ import annotations

import os
import json
from lswitch import system as system
import ctypes
import ctypes.util

# Try to load libX11 and bind XKB functions. If not available, we
# set XKB_AVAILABLE=False and provide safe fallbacks.
try:
    libX11_path = ctypes.util.find_library('X11')
    if libX11_path:
        libX11 = ctypes.CDLL(libX11_path)

        class XkbStateRec(ctypes.Structure):
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

        # Bind signatures
        libX11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        libX11.XOpenDisplay.restype = ctypes.c_void_p

        libX11.XkbGetState.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(XkbStateRec)]
        libX11.XkbGetState.restype = ctypes.c_int

        libX11.XkbLockGroup.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint]
        libX11.XkbLockGroup.restype = ctypes.c_int

        libX11.XFlush.argtypes = [ctypes.c_void_p]
        libX11.XFlush.restype = ctypes.c_int

        libX11.XCloseDisplay.argtypes = [ctypes.c_void_p]

        libX11.XkbKeycodeToKeysym.argtypes = [ctypes.c_void_p, ctypes.c_ubyte, ctypes.c_uint, ctypes.c_uint]
        libX11.XkbKeycodeToKeysym.restype = ctypes.c_ulong

        libX11.XKeysymToString.argtypes = [ctypes.c_ulong]
        libX11.XKeysymToString.restype = ctypes.c_char_p

        XKB_AVAILABLE = True
    else:
        libX11 = None
        XkbStateRec = None
        XKB_AVAILABLE = False
except Exception:
    libX11 = None
    XkbStateRec = None
    XKB_AVAILABLE = False


def get_layouts_from_xkb(runtime_dir: str | None = None, debug: bool = False) -> list:
    """Return list of layouts (e.g. ['en', 'ru']).

    First attempts to read `{XDG_RUNTIME_DIR}/lswitch_layouts.json` if present and
    fresh, then falls back to `setxkbmap -query`.
    """
    try:
        if runtime_dir is None:
            runtime_dir = os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')
        layouts_file = os.path.join(runtime_dir, 'lswitch_layouts.json')

        if os.path.exists(layouts_file):
            file_age = 0
            try:
                file_age = __import__('time').time() - os.path.getmtime(layouts_file)
            except Exception:
                file_age = 9999

            if file_age < 60:
                with open(layouts_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    layouts = data.get('layouts', [])
                    if layouts and len(layouts) >= 1:
                        if debug:
                            print(f"✓ Layouts from control panel: {layouts}")
                        return layouts
    except Exception:
        if debug:
            print("⚠️ Failed to read runtime layouts file")

    # Fallback to setxkbmap
    try:
        result = system.setxkbmap_query(timeout=2)
        for line in result.stdout.split('\n'):
            if line.startswith('layout:'):
                layouts_str = line.split(':', 1)[1].strip()
                layouts = [l.strip() for l in layouts_str.split(',') if l.strip()]
                result_list = ['en' if l == 'us' else l for l in layouts]
                if debug:
                    print(f"✓ Layouts from setxkbmap: {result_list}")
                return result_list
    except Exception:
        if debug:
            print("⚠️ Failed to call setxkbmap")

    # default
    if debug:
        print("⚠️ Using fallback layouts ['en','ru']")
    return ['en', 'ru']


def get_current_layout(layouts: list, debug: bool = False) -> str:
    """Return the current layout name using libX11 XkbGetState when available.

    If XKB is not available, returns layouts[0] or 'en'.
    """
    if not XKB_AVAILABLE or not libX11:
        return layouts[0] if layouts else 'en'

    try:
        display_ptr = libX11.XOpenDisplay(None)
        if not display_ptr:
            return layouts[0] if layouts else 'en'
        try:
            state = XkbStateRec()
            status = libX11.XkbGetState(display_ptr, 0x100, ctypes.byref(state))
            if status == 0:
                group = state.group
                if group < len(layouts):
                    return layouts[group]
                else:
                    return layouts[0] if layouts else 'en'
        finally:
            libX11.XCloseDisplay(display_ptr)
    except Exception:
        if debug:
            print("⚠️ Error in get_current_layout")
    return layouts[0] if layouts else 'en'


def keycode_to_char(keycode: int, layout: str, layouts: list, shift: bool = False, debug: bool = False) -> str:
    """Map evdev keycode to character using XKB via libX11. Returns '' on failure."""
    if not XKB_AVAILABLE or not libX11:
        return ''

    try:
        display_ptr = libX11.XOpenDisplay(None)
        if not display_ptr:
            return ''
        try:
            x11_keycode = keycode + 8
            # determine group index
            group = 0
            for i, lay in enumerate(layouts):
                if lay == layout:
                    group = i
                    break
            level = 1 if shift else 0
            keysym = libX11.XkbKeycodeToKeysym(display_ptr, x11_keycode, group, level)
            if keysym == 0:
                return ''
            keysym_str = libX11.XKeysymToString(keysym)
            if not keysym_str:
                return ''
            keysym_name = keysym_str.decode('utf-8')
            if len(keysym_name) == 1:
                return keysym_name
            if keysym_name.startswith('Cyrillic_'):
                cyrillic_map = {
                    'io': 'ё', 'IO': 'Ё',
                    # partial mapping left intentionally minimal for fallback purposes
                }
                key = keysym_name[9:]
                return cyrillic_map.get(key, '')
            return ''
        finally:
            libX11.XCloseDisplay(display_ptr)
    except Exception:
        if debug:
            print(f"⚠️ keycode_to_char failed for {keycode} {layout}")
        return ''
