"""LSwitch — Layout Switcher for Linux.

Re-exports key symbols so that ``import lswitch`` followed by
``lswitch.LSwitch``, ``lswitch.XLIB_AVAILABLE`` etc. works as
tests and legacy code expect.
"""

from lswitch.core import (
    LSwitch,
    XLIB_AVAILABLE,
    DICT_AVAILABLE,
    USER_DICT_AVAILABLE,
    x11_adapter,
    LS_INSTANCES,
    register_instance,
    force_release_virtual_keyboards,
)

__all__ = [
    "LSwitch",
    "XLIB_AVAILABLE",
    "DICT_AVAILABLE",
    "USER_DICT_AVAILABLE",
    "x11_adapter",
    "LS_INSTANCES",
    "register_instance",
    "force_release_virtual_keyboards",
]
