"""Wayland platform adapters.

These classes are the hard boundary for future compositor-specific backends.
Implemented paths use Wayland-safe primitives; unsupported compositor-specific
paths fail fast with actionable errors.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from lswitch.input.virtual_keyboard import VirtualKeyboard
from lswitch.platform.main_thread import MainThreadInvoker
from lswitch.platform.selection_adapter import ISelectionAdapter, SelectionInfo
from lswitch.platform.system_adapter import CommandResult, ISystemAdapter
from lswitch.platform.xkb_adapter import IXKBAdapter, LayoutInfo


logger = logging.getLogger(__name__)


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
    """Wayland implementation for key sequences and Qt clipboard access."""

    def __init__(
        self,
        virtual_kb: VirtualKeyboard,
        main_thread: MainThreadInvoker,
        compositor: str = "unknown",
        debug: bool = False,
    ) -> None:
        super().__init__(compositor=compositor, debug=debug)
        self.virtual_kb = virtual_kb
        self.main_thread = main_thread

    def run_command(self, args: list[str], timeout: float = 1.0) -> CommandResult:
        raise self._unsupported("run_command")

    def send_key_sequence(self, sequence: str, timeout: float = 0.3) -> None:
        self.virtual_kb.send_combo(sequence)

    def get_clipboard(self, selection: str = "primary") -> str:
        return self.main_thread.call(
            self._get_clipboard_on_main_thread,
            selection,
            timeout=1.0,
        )

    def set_clipboard(self, text: str, selection: str = "clipboard") -> None:
        self.main_thread.call(
            self._set_clipboard_on_main_thread,
            text,
            selection,
            timeout=1.0,
        )

    def _get_clipboard_on_main_thread(self, selection: str) -> str:
        clipboard, mode = self._qt_clipboard_and_mode(selection)
        return clipboard.text(mode)

    def _set_clipboard_on_main_thread(self, text: str, selection: str) -> None:
        clipboard, mode = self._qt_clipboard_and_mode(selection)
        clipboard.setText(text, mode)

    def _qt_clipboard_and_mode(self, selection: str):
        from PyQt6.QtGui import QClipboard, QGuiApplication

        clipboard = QGuiApplication.clipboard()
        if clipboard is None:
            raise RuntimeError("Qt clipboard is not available")

        normalized = (selection or "clipboard").strip().lower()
        if normalized == "clipboard":
            return clipboard, QClipboard.Mode.Clipboard
        if normalized in {"primary", "selection"}:
            if clipboard.supportsSelection():
                return clipboard, QClipboard.Mode.Selection
            raise WaylandBackendNotImplementedError(
                "Qt primary selection is not supported by this Wayland session; "
                "use clipboard copy/paste flow instead."
            )
        raise ValueError(f"Unsupported clipboard selection: {selection!r}")


class WaylandSelectionAdapter(_WaylandUnsupported, ISelectionAdapter):
    """Wayland selection adapter using explicit clipboard copy/paste flow.

    ``owner_id`` is always ``0`` on Wayland because there is no portable X11
    selection owner equivalent.
    """

    COPY_WAIT_TIMEOUT = 0.35
    COPY_POLL_INTERVAL = 0.01
    PASTE_DELAY = 0.05
    RESTORE_DELAY = 0.08

    def __init__(
        self,
        system: ISystemAdapter,
        main_thread: MainThreadInvoker,
        compositor: str = "unknown",
        debug: bool = False,
    ) -> None:
        super().__init__(compositor=compositor, debug=debug)
        self.system = system
        self.main_thread = main_thread
        self._prev_text: str = ""
        self._saved_clipboard: str | None = None

    def get_selection(self) -> SelectionInfo:
        old_clipboard = self.system.get_clipboard(selection="clipboard")
        self._saved_clipboard = old_clipboard
        self.system.send_key_sequence("ctrl+c")
        text = self._wait_for_clipboard_copy(old_clipboard)
        if not text:
            self._saved_clipboard = None
            return self.empty_selection()
        return SelectionInfo(text=text, owner_id=0, timestamp=time.time())

    def has_fresh_selection(self) -> bool:
        info = self.get_selection()
        if not info.text:
            return False
        fresh = info.text != self._prev_text
        if fresh:
            self._prev_text = info.text
        else:
            self._saved_clipboard = None
        return fresh

    def replace_selection(self, new_text: str) -> bool:
        old_clipboard = self._saved_clipboard
        if old_clipboard is None:
            old_clipboard = self.system.get_clipboard(selection="clipboard")
        try:
            self.system.set_clipboard(new_text, selection="clipboard")
            time.sleep(self.PASTE_DELAY)
            self.system.send_key_sequence("ctrl+v")
            time.sleep(self.RESTORE_DELAY)
            self.system.set_clipboard(old_clipboard, selection="clipboard")
            return True
        except Exception as exc:
            logger.warning("Wayland selection replace failed: %s", exc)
            return False
        finally:
            self._saved_clipboard = None

    def expand_selection_to_word(self) -> SelectionInfo:
        self.system.send_key_sequence("ctrl+shift+Left")
        time.sleep(self.PASTE_DELAY)
        return self.get_selection()

    @staticmethod
    def empty_selection() -> SelectionInfo:
        return SelectionInfo(text="", owner_id=0, timestamp=time.time())

    def _wait_for_clipboard_copy(self, old_clipboard: str) -> str:
        deadline = time.time() + self.COPY_WAIT_TIMEOUT
        last_seen = old_clipboard
        while time.time() < deadline:
            current = self.system.get_clipboard(selection="clipboard")
            if current and current != old_clipboard:
                return current
            last_seen = current
            time.sleep(self.COPY_POLL_INTERVAL)
        return "" if last_seen == old_clipboard else last_seen


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
