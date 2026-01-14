"""X11 adapter wrapping xclip/xdotool calls.

Provides small, test-friendly wrappers so we can mock X11 interactions in tests.
"""
import subprocess
import time


def get_primary_selection(timeout=0.3) -> str:
    try:
        return subprocess.run(['xclip', '-o', '-selection', 'primary'], capture_output=True, timeout=timeout, text=True).stdout
    except Exception:
        return ''


def get_clipboard(timeout=0.3) -> str:
    try:
        return subprocess.run(['xclip', '-o', '-selection', 'clipboard'], capture_output=True, timeout=timeout, text=True).stdout
    except Exception:
        return ''


def set_clipboard(text: str, timeout=0.5):
    try:
        subprocess.run(['xclip', '-selection', 'clipboard'], input=text, text=True, timeout=timeout)
    except Exception:
        pass


def paste_clipboard():
    try:
        subprocess.run(['xdotool', 'key', 'ctrl+v'], timeout=1.0, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def cut_selection():
    try:
        subprocess.run(['xdotool', 'key', 'ctrl+x'], timeout=0.5, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def delete_selection():
    try:
        subprocess.run(['xdotool', 'key', 'Delete'], timeout=0.2, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def shift_left():
    try:
        subprocess.run(['xdotool', 'key', 'shift+Left'], timeout=0.1, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def ctrl_shift_left():
    try:
        subprocess.run(['xdotool', 'key', 'ctrl+shift+Left'], timeout=0.1, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def send_key(key: str):
    try:
        subprocess.run(['xdotool', 'key', key], timeout=0.5, stderr=subprocess.DEVNULL)
    except Exception:
        pass
