#!/usr/bin/env python3
"""
Standalone test: проверяет переключение раскладки тем же методом, что и LSwitch.

Использование:
    python3 scripts/test_xkb_switch.py

Тестирует два подхода:
  A) XkbLockGroup напрямую через libX11
  B) Cinnamon D-Bus ActivateInputSourceIndex (используется в программе)
"""

import ctypes
import ctypes.util
import re
import subprocess
import sys
import time


# ---------------------------------------------------------------------------
# Structs (из xkb_bindings.py)
# ---------------------------------------------------------------------------

class XkbStateRec(ctypes.Structure):
    _fields_ = [
        ("group",               ctypes.c_ubyte),
        ("locked_group",        ctypes.c_ubyte),
        ("base_group",          ctypes.c_ushort),
        ("latched_group",       ctypes.c_ushort),
        ("mods",                ctypes.c_ubyte),
        ("base_mods",           ctypes.c_ubyte),
        ("latched_mods",        ctypes.c_ubyte),
        ("locked_mods",         ctypes.c_ubyte),
        ("compat_state",        ctypes.c_ubyte),
        ("grab_mods",           ctypes.c_ubyte),
        ("compat_grab_mods",    ctypes.c_ubyte),
        ("lookup_mods",         ctypes.c_ubyte),
        ("compat_lookup_mods",  ctypes.c_ubyte),
        ("ptr_buttons",         ctypes.c_ushort),
    ]

XKB_USE_CORE_KBD = 0x0100


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_libx11():
    path = ctypes.util.find_library("X11")
    if not path:
        print("FAIL: libX11 not found")
        sys.exit(1)
    lib = ctypes.cdll.LoadLibrary(path)
    lib.XInitThreads.argtypes = []
    lib.XInitThreads.restype = ctypes.c_int
    lib.XOpenDisplay.argtypes = [ctypes.c_char_p]
    lib.XOpenDisplay.restype = ctypes.c_void_p
    lib.XCloseDisplay.argtypes = [ctypes.c_void_p]
    lib.XCloseDisplay.restype = ctypes.c_int
    lib.XkbGetState.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(XkbStateRec)]
    lib.XkbGetState.restype = ctypes.c_int
    lib.XkbLockGroup.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint]
    lib.XkbLockGroup.restype = ctypes.c_int
    lib.XFlush.argtypes = [ctypes.c_void_p]
    lib.XFlush.restype = ctypes.c_int
    lib.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.XSync.restype = ctypes.c_int
    return lib


def get_group(lib, dpy) -> int:
    state = XkbStateRec()
    rc = lib.XkbGetState(dpy, XKB_USE_CORE_KBD, ctypes.byref(state))
    return state.group if rc == 0 else -1


def dbus_get_sources():
    """Вернуть [(index, xkb_name, is_active)] через Cinnamon D-Bus."""
    try:
        r = subprocess.run(
            ["gdbus", "call", "--session",
             "--dest", "org.Cinnamon", "--object-path", "/org/Cinnamon",
             "--method", "org.Cinnamon.GetInputSources"],
            capture_output=True, text=True, timeout=3,
        )
        if r.returncode != 0:
            return None
        sources = []
        for m in re.finditer(
            r"\('xkb',\s*'(\w+)',\s*(\d+),(?:[^()]|\([^)]*\))+,\s*(true|false)\)",
            r.stdout,
        ):
            sources.append((int(m.group(2)), m.group(1), m.group(3) == "true"))
        return sources or None
    except Exception:
        return None


def dbus_activate(index: int) -> bool:
    try:
        r = subprocess.run(
            ["gdbus", "call", "--session",
             "--dest", "org.Cinnamon", "--object-path", "/org/Cinnamon",
             "--method", "org.Cinnamon.ActivateInputSourceIndex", str(index)],
            capture_output=True, text=True, timeout=3,
        )
        return r.returncode == 0
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=== LSwitch XKB layout switch test ===\n")

    lib = load_libx11()
    lib.XInitThreads()
    dpy = lib.XOpenDisplay(None)
    if not dpy:
        print("FAIL: XOpenDisplay returned NULL")
        sys.exit(1)

    # --- Cinnamon D-Bus info ---
    print("[ Cinnamon D-Bus ]")
    sources = dbus_get_sources()
    if sources:
        for idx, name, active in sources:
            mark = " ← active" if active else ""
            print(f"  [{idx}] {name}{mark}")
        current_dbus = next((idx for idx, _, act in sources if act), 0)
        next_dbus = (current_dbus + 1) % len(sources)
    else:
        print("  Cinnamon D-Bus недоступен")
        current_dbus = None

    # --- XkbGetState before ---
    g0 = get_group(lib, dpy)
    print(f"\n[ XkbGetState ] group before = {g0}")

    # === Test A: XkbLockGroup ===
    print("\n--- Test A: XkbLockGroup (прямой) ---")
    new_g = (g0 + 1) % max(len(sources) if sources else 2, 1)
    lib.XkbLockGroup(dpy, XKB_USE_CORE_KBD, new_g)
    lib.XSync(dpy, 0)
    g_after = get_group(lib, dpy)
    time.sleep(0.3)
    dpy2 = lib.XOpenDisplay(None)
    g_fresh = get_group(lib, dpy2) if dpy2 else -1
    if dpy2:
        lib.XCloseDisplay(dpy2)
    print(f"  same conn after XSync: {g_after} ({'✓' if g_after == new_g else '✗'})")
    print(f"  new conn after 300ms:  {g_fresh} ({'✓ stable' if g_fresh == new_g else '✗ reverted by WM'})")

    # Restore via D-Bus
    if sources:
        dbus_activate(current_dbus)
        time.sleep(0.1)

    # === Test B: Cinnamon D-Bus ===
    print("\n--- Test B: Cinnamon D-Bus ActivateInputSourceIndex ---")
    if sources is None:
        print("  SKIP — Cinnamon D-Bus недоступен")
    else:
        ok = dbus_activate(next_dbus)
        print(f"  ActivateInputSourceIndex({next_dbus}) → {'OK' if ok else 'FAIL'}")
        time.sleep(0.2)
        sources2 = dbus_get_sources()
        if sources2:
            active_now = next((idx for idx, _, act in sources2 if act), -1)
            stable = active_now == next_dbus
            print(f"  active after 200ms: {active_now} ({'✓ stable' if stable else '✗ reverted'})")
        # XKB group via XkbGetState
        dpy3 = lib.XOpenDisplay(None)
        g_dbus = get_group(lib, dpy3) if dpy3 else -1
        if dpy3:
            lib.XCloseDisplay(dpy3)
        print(f"  XkbGetState on new conn: group={g_dbus}")

        # Restore
        dbus_activate(current_dbus)

    lib.XCloseDisplay(dpy)

    print("\n=== Вывод ===")
    if sources:
        xkb_ok = g_fresh == new_g
        print(f"  XkbLockGroup:  {'✓ работает (другое DE?)' if xkb_ok else '✗ Cinnamon откатывает'}")
        print(f"  Cinnamon DBus: ✓ использован в программе")
    else:
        print("  Cinnamon D-Bus: недоступен — используется XkbLockGroup")


if __name__ == "__main__":
    main()
