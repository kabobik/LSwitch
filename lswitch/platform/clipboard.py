"""Low-level clipboard/selection operations via xclip/xdotool."""

from __future__ import annotations

import subprocess


def get_primary_selection(timeout: float = 0.3) -> str:
    """Read X11 PRIMARY selection. Returns empty string on failure."""
    try:
        result = subprocess.run(
            ["xclip", "-o", "-selection", "primary"],
            capture_output=True, text=True, timeout=timeout,
        )
        return result.stdout
    except Exception:
        return ""


def set_clipboard(text: str, selection: str = "clipboard", timeout: float = 1.0) -> None:
    """Write text to clipboard or primary selection."""
    try:
        subprocess.run(
            ["xclip", "-i", "-selection", selection],
            input=text, text=True, timeout=timeout,
        )
    except Exception:
        pass


def get_selection_owner_id() -> int:
    """Return window ID of the current PRIMARY selection owner (0 if none)."""
    try:
        result = subprocess.run(
            ["xprop", "-root", "XA_PRIMARY"],
            capture_output=True, text=True, timeout=0.5,
        )
        # Parse "XA_PRIMARY: window id # 0x..." — fallback to xdotool
    except Exception:
        pass
    # Prefer Xlib-based lookup when available
    try:
        from Xlib import display as xdisplay, Xatom
        d = xdisplay.Display()
        owner = d.get_selection_owner(Xatom.PRIMARY)
        d.close()
        return owner.id if owner else 0
    except Exception:
        return 0
