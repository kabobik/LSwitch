"""UI adapters: desktop-environment-specific implementations."""

from __future__ import annotations

import os

from lswitch.ui.adapters.base import BaseUIAdapter


def detect_desktop_environment() -> str:
    """Detect the current desktop environment from env vars.

    Returns one of: 'kde', 'cinnamon', 'gnome', 'xfce', or 'unknown'.
    """
    xdg = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    de = os.environ.get("DESKTOP_SESSION", "").lower()

    for token in (xdg, de):
        if "kde" in token or "plasma" in token:
            return "kde"
        if "cinnamon" in token:
            return "cinnamon"
        if "gnome" in token:
            return "gnome"
        if "xfce" in token:
            return "xfce"

    return "unknown"


def get_adapter() -> BaseUIAdapter:
    """Return the appropriate UI adapter for the current DE."""
    de = detect_desktop_environment()

    if de == "kde":
        from lswitch.ui.adapters.kde import KDEAdapter
        return KDEAdapter()

    # Cinnamon / fallback
    from lswitch.ui.adapters.cinnamon import CinnamonAdapter
    return CinnamonAdapter()


__all__ = [
    "BaseUIAdapter",
    "detect_desktop_environment",
    "get_adapter",
]
