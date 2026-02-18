"""X11 adapter wrapping xclip/xdotool calls.

Provides small, test-friendly wrappers so we can mock X11 interactions in tests.
"""
import os
import sys

import lswitch.system as system_mod

# Adapter-level override for DI in tests. By default we prefer
# to call functions on `lswitch.system.SYSTEM` (the module-level instance)
# which allows consistent mocking via `lswitch.system.SYSTEM = MockSystem()`.
# For explicit adapter-level injection tests we provide `set_system()`.
_adapter_system = None

def set_system(sys_impl):
    global _adapter_system
    _adapter_system = sys_impl


def get_system():
    if _adapter_system is not None:
        return _adapter_system
    # if system_mod exposes a SYSTEM instance use it, otherwise fall back to module
    return getattr(system_mod, 'SYSTEM', system_mod)

import time
import subprocess


def get_primary_selection(timeout=0.3) -> str:
    try:
        return get_system().xclip_get(selection='primary', timeout=timeout).stdout
    except Exception:
        return ''


def get_clipboard(timeout=0.3) -> str:
    try:
        return get_system().xclip_get(selection='clipboard', timeout=timeout).stdout
    except Exception:
        return ''


def set_clipboard(text: str, timeout=0.5):
    try:
        get_system().xclip_set(text, selection='clipboard', timeout=timeout)
    except Exception:
        pass


def paste_clipboard():
    try:
        get_system().xdotool_key('ctrl+v', timeout=1.0, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def cut_selection():
    try:
        get_system().xdotool_key('ctrl+x', timeout=0.5, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def delete_selection():
    try:
        get_system().xdotool_key('Delete', timeout=0.2, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def shift_left():
    try:
        get_system().xdotool_key('shift+Left', timeout=0.1, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def get_active_window_name():
    """Return active window name using xdotool, or empty string on failure."""
    try:
        res = get_system().run(['xdotool', 'getwindowfocus', 'getwindowname'], capture_output=True, timeout=0.5, text=True)
        return res.stdout.strip()
    except Exception:
        return ''


def get_active_window_class():
    """Return active window WM_CLASS via xprop, or empty string on failure."""
    try:
        # get window id
        wid = get_system().run(['xdotool', 'getwindowfocus'], capture_output=True, timeout=0.3, text=True).stdout.strip()
        if not wid:
            return ''
        # query WM_CLASS
        res = get_system().run(['xprop', '-id', wid, 'WM_CLASS'], capture_output=True, timeout=0.5, text=True).stdout
        # WM_CLASS(STRING) = "code", "Code"
        if 'WM_CLASS' in res and '"' in res:
            parts = [p.strip().strip('"') for p in res.split('=')[-1].split(',')]
            # return first non-empty part
            for p in parts:
                if p:
                    return p
        return ''
    except Exception:
        return ''

def ctrl_shift_left():
    try:
        get_system().xdotool_key('ctrl+shift+Left', timeout=0.1, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def send_key(key: str):
    try:
        get_system().xdotool_key(key, timeout=0.5, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def expand_selection_to_space(max_steps: int = 100, stable_timeout: float = 0.5) -> str:
    """Expand selection leftwards until a space is included or max_steps reached.

    Returns the current PRIMARY selection (possibly unchanged).
    """
    sel = get_primary_selection()
    try:
        prev = sel
        no_growth = 0
        for _ in range(max_steps):
            shift_left()
            time.sleep(0.01)
            new_sel = get_primary_selection()
            if new_sel == prev:
                no_growth += 1
            else:
                prev = new_sel
                no_growth = 0
            if ' ' in new_sel:
                sel = new_sel
                break
            if no_growth >= 3:
                # try word-wise once
                ctrl_shift_left()
                time.sleep(0.01)
                new_sel = get_primary_selection()
                if new_sel != prev:
                    sel = new_sel
                    break
                else:
                    # can't expand more
                    break
        # Stabilize
        stable_prev = None
        stable_count = 0
        start_t = time.time()
        while time.time() - start_t < stable_timeout and stable_count < 3:
            cur = get_primary_selection()
            if cur == stable_prev:
                stable_count += 1
            else:
                stable_prev = cur
                stable_count = 1
            time.sleep(0.02)
        if stable_prev:
            sel = stable_prev
    except Exception:
        pass
    return sel


def safe_replace_selection(converted: str, selected_text: str = None, debug: bool = False) -> str:
    """Safely replace current PRIMARY selection with converted text.

    Simple 4-step algorithm:
    1. Save old clipboard
    2. Set clipboard to converted text
    3. Paste (Ctrl+V automatically replaces selection)
    4. Restore old clipboard

    Returns the converted text.
    """
    if debug:
        print(f"🔍 safe_replace: converted={converted!r}", flush=True)

    old_clip = get_clipboard()
    try:
        set_clipboard(converted)
        time.sleep(0.02)
        paste_clipboard()
        time.sleep(0.05)
    finally:
        if old_clip:
            set_clipboard(old_clip)

    if debug:
        print(f"🔍 safe_replace EXIT: returning {converted!r}", flush=True)
    return converted
