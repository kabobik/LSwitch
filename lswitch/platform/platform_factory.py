"""Platform adapter factory and session detection."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

from lswitch.input.virtual_keyboard import VirtualKeyboard
from lswitch.platform.selection_adapter import ISelectionAdapter
from lswitch.platform.system_adapter import ISystemAdapter
from lswitch.platform.xkb_adapter import IXKBAdapter


@dataclass(frozen=True)
class PlatformAdapters:
    """Concrete adapter set for the current desktop session."""

    session_type: str
    compositor: str
    system: ISystemAdapter
    xkb: IXKBAdapter
    selection: ISelectionAdapter
    virtual_kb: VirtualKeyboard
    selection_polling_enabled: bool = False


def detect_session_type(env: Mapping[str, str] | None = None) -> str:
    """Return ``x11``, ``wayland`` or ``unknown`` for the current session."""
    env = os.environ if env is None else env
    explicit = env.get("XDG_SESSION_TYPE", "").strip().lower()
    if explicit in {"x11", "wayland"}:
        return explicit
    if env.get("WAYLAND_DISPLAY"):
        return "wayland"
    if env.get("DISPLAY"):
        return "x11"
    return "unknown"


def detect_compositor(env: Mapping[str, str] | None = None) -> str:
    """Best-effort compositor/desktop detection."""
    env = os.environ if env is None else env

    if env.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return "hyprland"
    if env.get("SWAYSOCK"):
        return "sway"

    desktop = (
        env.get("XDG_CURRENT_DESKTOP", "")
        + ":"
        + env.get("DESKTOP_SESSION", "")
        + ":"
        + env.get("GDMSESSION", "")
    ).lower()

    if env.get("KDE_FULL_SESSION") or "kde" in desktop or "plasma" in desktop:
        return "kde"
    if "gnome" in desktop:
        return "gnome"
    if "cinnamon" in desktop:
        return "cinnamon"
    return "unknown"


def create_platform_adapters(
    debug: bool = False,
    env: Mapping[str, str] | None = None,
) -> PlatformAdapters:
    """Create adapters for the current session.

    This is the only place that maps the host desktop session to concrete
    adapters. Application/core code should consume the returned capabilities
    and never branch on X11/Wayland directly.
    """
    session_type = detect_session_type(env)
    compositor = detect_compositor(env)

    if session_type == "wayland":
        return create_wayland_platform_adapters(
            debug=debug,
            compositor=compositor,
        )
    if session_type == "unknown":
        raise RuntimeError(
            "LSwitch requires an active X11 or Wayland graphical session "
            "(DISPLAY or WAYLAND_DISPLAY is not set)."
        )
    return create_x11_platform_adapters(debug=debug, compositor=compositor)


def create_x11_platform_adapters(
    debug: bool = False,
    compositor: str | None = None,
) -> PlatformAdapters:
    """Create the current production X11 adapter set."""
    from lswitch.platform.selection_adapter import X11SelectionAdapter
    from lswitch.platform.subprocess_impl import SubprocessSystemAdapter
    from lswitch.platform.xkb_adapter import X11XKBAdapter

    system = SubprocessSystemAdapter(debug=debug)
    xkb = X11XKBAdapter(debug=debug)
    selection = X11SelectionAdapter(system=system, debug=debug)
    virtual_kb = VirtualKeyboard(debug=debug)
    return PlatformAdapters(
        session_type="x11",
        compositor=compositor or "unknown",
        system=system,
        xkb=xkb,
        selection=selection,
        virtual_kb=virtual_kb,
        selection_polling_enabled=True,
    )


def create_wayland_platform_adapters(
    debug: bool = False,
    compositor: str | None = None,
) -> PlatformAdapters:
    """Create the Wayland adapter skeleton.

    The concrete backends are intentionally conservative for now: they satisfy
    the same interfaces as X11 adapters, but unsupported operations fail at
    the adapter boundary with actionable messages.
    """
    from lswitch.platform.wayland import (
        WaylandLayoutAdapter,
        WaylandSelectionAdapter,
        WaylandSystemAdapter,
    )

    virtual_kb = VirtualKeyboard(debug=debug)
    system = WaylandSystemAdapter(
        virtual_kb=virtual_kb,
        compositor=compositor or "unknown",
        debug=debug,
    )
    xkb = WaylandLayoutAdapter(
        compositor=compositor or "unknown",
        debug=debug,
    )
    selection = WaylandSelectionAdapter(
        system=system,
        compositor=compositor or "unknown",
        debug=debug,
    )
    return PlatformAdapters(
        session_type="wayland",
        compositor=compositor or "unknown",
        system=system,
        xkb=xkb,
        selection=selection,
        virtual_kb=virtual_kb,
        selection_polling_enabled=False,
    )
