"""Wayland platform adapter skeletons.

These classes are the hard boundary for future compositor-specific backends.
They intentionally fail fast for operations that still need QtBridge,
KDE/GNOME/Sway/Hyprland integration, or Wayland clipboard support.
"""

from __future__ import annotations

import time
from typing import Optional

from lswitch.input.virtual_keyboard import VirtualKeyboard
from lswitch.platform.selection_adapter import ISelectionAdapter, SelectionInfo
from lswitch.platform.system_adapter import CommandResult, ISystemAdapter
from lswitch.platform.xkb_adapter import IXKBAdapter, LayoutInfo


class WaylandBackendNotImplementedError(NotImplementedError):
    """Raised when a Wayland adapter path is not implemented yet."""


class _WaylandUnsupported:
    def __init__(self, compositor: str = "unknown", debug: bool = False) -> None:
        self.compositor = compositor or "unknown"
        self.debug = debug

    def _unsupported(self, operation: str) -> WaylandBackendNotImplementedError:
        return WaylandBackendNotImplementedError(
            f"Wayland backend operation '{operation}' is not implemented yet "
            f"for compositor '{self.compositor}'. "
            "See docs/WAYLAND_IMPLEMENTATION_PLAN.md."
        )


class WaylandSystemAdapter(_WaylandUnsupported, ISystemAdapter):
    """Wayland implementation placeholder for key sequences and clipboard."""

    def __init__(
        self,
        virtual_kb: VirtualKeyboard,
        compositor: str = "unknown",
        debug: bool = False,
    ) -> None:
        super().__init__(compositor=compositor, debug=debug)
        self.virtual_kb = virtual_kb

    def run_command(self, args: list[str], timeout: float = 1.0) -> CommandResult:
        raise self._unsupported("run_command")

    def send_key_sequence(self, sequence: str, timeout: float = 0.3) -> None:
        raise self._unsupported("send_key_sequence")

    def get_clipboard(self, selection: str = "primary") -> str:
        raise self._unsupported("get_clipboard")

    def set_clipboard(self, text: str, selection: str = "clipboard") -> None:
        raise self._unsupported("set_clipboard")


class WaylandSelectionAdapter(_WaylandUnsupported, ISelectionAdapter):
    """Wayland selection placeholder.

    ``owner_id`` is always ``0`` on Wayland because there is no portable X11
    selection owner equivalent. Concrete backends will use clipboard copy/paste
    flow or compositor-specific primary selection support.
    """

    def __init__(
        self,
        system: ISystemAdapter,
        compositor: str = "unknown",
        debug: bool = False,
    ) -> None:
        super().__init__(compositor=compositor, debug=debug)
        self.system = system

    def get_selection(self) -> SelectionInfo:
        raise self._unsupported("get_selection")

    def has_fresh_selection(self) -> bool:
        raise self._unsupported("has_fresh_selection")

    def replace_selection(self, new_text: str) -> bool:
        raise self._unsupported("replace_selection")

    def expand_selection_to_word(self) -> SelectionInfo:
        raise self._unsupported("expand_selection_to_word")

    @staticmethod
    def empty_selection() -> SelectionInfo:
        return SelectionInfo(text="", owner_id=0, timestamp=time.time())


class WaylandLayoutAdapter(_WaylandUnsupported, IXKBAdapter):
    """Wayland layout placeholder for future compositor-specific backends."""

    def get_layouts(self) -> list[LayoutInfo]:
        raise self._unsupported("get_layouts")

    def get_current_layout(self) -> LayoutInfo:
        raise self._unsupported("get_current_layout")

    def switch_layout(self, target: Optional[LayoutInfo] = None) -> LayoutInfo:
        raise self._unsupported("switch_layout")

    def keycode_to_char(
        self,
        keycode: int,
        layout: LayoutInfo,
        shift: bool = False,
    ) -> str:
        raise self._unsupported("keycode_to_char")
