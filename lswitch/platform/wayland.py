"""Wayland platform adapters.

These classes are the hard boundary for future compositor-specific backends.
Implemented paths use Wayland-safe primitives; unsupported compositor-specific
paths fail fast with actionable errors.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import re
import shutil
import subprocess
import time
from typing import Callable, Optional

from lswitch.input.virtual_keyboard import VirtualKeyboard
from lswitch.platform.main_thread import MainThreadInvoker
from lswitch.platform.selection_adapter import ISelectionAdapter, SelectionInfo
from lswitch.platform.system_adapter import CommandResult, ISystemAdapter
from lswitch.platform.xkb_adapter import IXKBAdapter, LayoutInfo


logger = logging.getLogger(__name__)


class WaylandBackendNotImplementedError(NotImplementedError):
    """Raised when a Wayland adapter path is not implemented yet."""


class WaylandLayoutBackendError(RuntimeError):
    """Raised when a compositor layout backend is unavailable or invalid."""


@dataclass(frozen=True)
class DbusUInt32:
    """Typed D-Bus uint32 argument for QtDBus calls."""

    value: int

    def __post_init__(self) -> None:
        if not isinstance(self.value, int) or isinstance(self.value, bool):
            raise TypeError("D-Bus uint32 value must be an integer")
        if self.value < 0 or self.value > 0xFFFFFFFF:
            raise ValueError("D-Bus uint32 value is out of range")


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

    WL_CLIPBOARD_TIMEOUT = 1.0

    def __init__(
        self,
        virtual_kb: VirtualKeyboard,
        main_thread: MainThreadInvoker,
        compositor: str = "unknown",
        debug: bool = False,
        enable_wl_clipboard: bool = True,
        command_lookup: Callable[[str], str | None] | None = None,
        command_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    ) -> None:
        super().__init__(compositor=compositor, debug=debug)
        self.virtual_kb = virtual_kb
        self.main_thread = main_thread
        self.enable_wl_clipboard = enable_wl_clipboard
        self._command_lookup = command_lookup or shutil.which
        self._command_runner = command_runner or subprocess.run
        self._wl_clipboard_available: bool | None = None

    def run_command(self, args: list[str], timeout: float = 1.0) -> CommandResult:
        raise self._unsupported("run_command")

    def send_key_sequence(self, sequence: str, timeout: float = 0.3) -> None:
        self.virtual_kb.send_combo(sequence)

    def get_clipboard(self, selection: str = "primary") -> str:
        text = self._get_wl_clipboard(selection)
        if text is not None:
            return text
        return self.main_thread.call(
            self._get_clipboard_on_main_thread,
            selection,
            timeout=1.0,
        )

    def set_clipboard(self, text: str, selection: str = "clipboard") -> None:
        if self._set_wl_clipboard(text, selection):
            return
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

        normalized = self._normalize_clipboard_selection(selection)
        if normalized == "clipboard":
            return clipboard, QClipboard.Mode.Clipboard
        if normalized == "primary":
            if clipboard.supportsSelection():
                return clipboard, QClipboard.Mode.Selection
            raise WaylandBackendNotImplementedError(
                "Qt primary selection is not supported by this Wayland session; "
                "use clipboard copy/paste flow instead."
            )
        raise ValueError(f"Unsupported clipboard selection: {selection!r}")

    @staticmethod
    def _normalize_clipboard_selection(selection: str) -> str:
        normalized = (selection or "clipboard").strip().lower()
        if normalized == "selection":
            return "primary"
        return normalized

    def _get_wl_clipboard(self, selection: str) -> str | None:
        if not self._can_use_wl_clipboard(selection):
            return None

        result = self._run_wl_command(
            self._wl_clipboard_args("wl-paste", selection),
            timeout=self.WL_CLIPBOARD_TIMEOUT,
        )
        if result.returncode == 0:
            return result.stdout

        logger.debug("wl-paste failed: %s", result.stderr.strip() or result.returncode)
        return None

    def _set_wl_clipboard(self, text: str, selection: str) -> bool:
        if not self._can_use_wl_clipboard(selection):
            return False

        result = self._run_wl_command(
            self._wl_clipboard_args("wl-copy", selection),
            input_text=text,
            timeout=self.WL_CLIPBOARD_TIMEOUT,
        )
        if result.returncode == 0:
            return True

        logger.debug("wl-copy failed: %s", result.stderr.strip() or result.returncode)
        return False

    def _can_use_wl_clipboard(self, selection: str) -> bool:
        if not self.enable_wl_clipboard:
            return False

        normalized = self._normalize_clipboard_selection(selection)
        if normalized not in {"clipboard", "primary"}:
            return False

        if self._wl_clipboard_available is None:
            self._wl_clipboard_available = (
                self._command_lookup("wl-copy") is not None
                and self._command_lookup("wl-paste") is not None
            )
            if self._wl_clipboard_available:
                logger.debug("Wayland wl-clipboard backend is available")
            else:
                logger.debug("Wayland wl-clipboard backend is not available")
        return self._wl_clipboard_available

    def _wl_clipboard_args(self, command: str, selection: str) -> list[str]:
        args = [command]
        if self._normalize_clipboard_selection(selection) == "primary":
            args.append("--primary")
        return args

    def _run_wl_command(
        self,
        args: list[str],
        *,
        input_text: str | None = None,
        timeout: float,
    ) -> CommandResult:
        try:
            result = self._command_runner(
                args,
                input=input_text,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return CommandResult(
                stdout=result.stdout or "",
                stderr=result.stderr or "",
                returncode=result.returncode,
            )
        except subprocess.TimeoutExpired:
            return CommandResult(stdout="", stderr="timeout", returncode=-1)
        except Exception as exc:
            return CommandResult(stdout="", stderr=str(exc), returncode=-1)


class WaylandSelectionAdapter(_WaylandUnsupported, ISelectionAdapter):
    """Wayland selection adapter using explicit clipboard copy/paste flow.

    ``owner_id`` is always ``0`` on Wayland because there is no portable X11
    selection owner equivalent.
    """

    COPY_WAIT_TIMEOUT = 1.0
    COPY_POLL_INTERVAL = 0.05
    COPY_RETRY_DELAY = 0.1
    PASTE_DELAY = 0.12
    RESTORE_DELAY = 0.15
    EXPAND_SELECTION_DELAY = 0.2
    COPY_SENTINEL_PREFIX = "__LSWITCH_COPY_SENTINEL__"
    COPY_SHORTCUTS = ("ctrl+c", "ctrl+insert")

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
        sentinel = self._copy_sentinel()
        self.system.set_clipboard(sentinel, selection="clipboard")
        text = self._copy_selection_to_clipboard(sentinel)
        if not text:
            logger.debug("Wayland selection copy returned empty text")
            self.system.set_clipboard(old_clipboard, selection="clipboard")
            self._saved_clipboard = None
            return self.empty_selection()
        logger.debug("Wayland selection copied %d chars", len(text))
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
        time.sleep(self.EXPAND_SELECTION_DELAY)
        return self.get_selection()

    @staticmethod
    def empty_selection() -> SelectionInfo:
        return SelectionInfo(text="", owner_id=0, timestamp=time.time())

    def _wait_for_clipboard_copy(self, sentinel: str) -> str:
        deadline = time.time() + self.COPY_WAIT_TIMEOUT
        while time.time() < deadline:
            current = self.system.get_clipboard(selection="clipboard")
            if current and current != sentinel:
                return current
            time.sleep(self.COPY_POLL_INTERVAL)
        return ""

    def _copy_selection_to_clipboard(self, sentinel: str) -> str:
        for sequence in self.COPY_SHORTCUTS:
            self.system.send_key_sequence(sequence)
            text = self._wait_for_clipboard_copy(sentinel)
            if text:
                logger.debug("Wayland selection copy succeeded via %s", sequence)
                return text
            logger.debug("Wayland selection copy via %s returned no text", sequence)
            time.sleep(self.COPY_RETRY_DELAY)
        return ""

    def _copy_sentinel(self) -> str:
        return f"{self.COPY_SENTINEL_PREFIX}{time.monotonic_ns()}"


class KdeKeyboardDbusClient:
    """Small QtDBus wrapper for KDE keyboard layout service."""

    SERVICE = "org.kde.keyboard"
    PATH = "/Layouts"
    INTERFACE = "org.kde.KeyboardLayouts"
    INTROSPECTABLE_INTERFACE = "org.freedesktop.DBus.Introspectable"

    def __init__(self, main_thread: MainThreadInvoker) -> None:
        self.main_thread = main_thread

    def call(self, method: str, *args):
        return self.call_interface(self.INTERFACE, method, *args)

    def call_interface(self, interface: str, method: str, *args):
        return self.main_thread.call(
            self._call_on_main_thread,
            interface,
            method,
            *args,
            timeout=1.0,
        )

    def introspect(self) -> str:
        return self.call_interface(self.INTROSPECTABLE_INTERFACE, "Introspect")

    def _call_on_main_thread(self, interface: str, method: str, *args):
        try:
            from PyQt6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage
        except ImportError as exc:
            raise WaylandLayoutBackendError(
                "PyQt6.QtDBus is required for KDE Wayland layout backend"
            ) from exc

        iface = QDBusInterface(
            self.SERVICE,
            self.PATH,
            interface,
            QDBusConnection.sessionBus(),
        )
        if not iface.isValid():
            error = iface.lastError()
            message = error.message() if error else ""
            raise WaylandLayoutBackendError(
                "KDE keyboard D-Bus interface is unavailable: "
                f"{self.SERVICE} {self.PATH} {interface}"
                + (f" ({message})" if message else "")
            )

        reply = iface.call(method, *(self._qtdbus_argument(arg) for arg in args))
        if reply.type() == QDBusMessage.MessageType.ErrorMessage:
            raise WaylandLayoutBackendError(
                f"KDE keyboard D-Bus method {method!r} failed: {reply.errorMessage()}"
            )

        values = reply.arguments()
        if not values:
            return None
        if len(values) == 1:
            return values[0]
        return values

    @staticmethod
    def _qtdbus_argument(arg):
        if not isinstance(arg, DbusUInt32):
            return arg

        try:
            from PyQt6.QtCore import QMetaType, QVariant
        except ImportError as exc:
            raise WaylandLayoutBackendError(
                "PyQt6.QtCore QMetaType/QVariant is required for D-Bus uint32"
            ) from exc

        variant = QVariant(arg.value)
        uint_type = QMetaType(int(QMetaType.Type.UInt.value))
        if not variant.convert(uint_type):
            raise WaylandLayoutBackendError(
                f"Could not convert {arg.value!r} to D-Bus uint32"
            )
        return variant


class KdeLayoutBackend:
    """KDE Plasma keyboard layout backend using ``org.kde.KeyboardLayouts``."""

    def __init__(self, dbus_client, debug: bool = False) -> None:
        self.dbus = dbus_client
        self.debug = debug
        self._layouts: list[LayoutInfo] | None = None
        self._raw_layouts: list = []
        self.last_switch_method: str | None = None

    def validate(self) -> None:
        self.get_layouts()
        self.get_current_layout()

    def invalidate_cache(self) -> None:
        self._layouts = None
        self._raw_layouts = []

    def get_layouts(self) -> list[LayoutInfo]:
        if self._layouts is not None:
            return self._layouts

        raw = self.dbus.call("getLayoutsList")
        raw_layouts = self._coerce_layout_list(raw)
        if not raw_layouts:
            raise WaylandLayoutBackendError(
                "KDE keyboard D-Bus getLayoutsList returned no layouts"
            )

        self._raw_layouts = raw_layouts
        self._layouts = [
            LayoutInfo(
                name=self._layout_name_from_xkb(xkb_name),
                index=index,
                xkb_name=xkb_name,
            )
            for index, xkb_name in enumerate(
                self._xkb_name_from_raw(raw_layout)
                for raw_layout in raw_layouts
            )
        ]
        return self._layouts

    def get_current_layout(self) -> LayoutInfo:
        layouts = self.get_layouts()
        raw_current = self.dbus.call("getLayout")
        index = self._current_index_from_raw(raw_current, layouts)
        return layouts[index]

    def switch_layout(self, target: Optional[LayoutInfo] = None) -> LayoutInfo:
        layouts = self.get_layouts()
        if target is None:
            current = self.get_current_layout()
            new_index = (current.index + 1) % len(layouts)
        else:
            new_index = target.index

        if new_index < 0 or new_index >= len(layouts):
            raise WaylandLayoutBackendError(
                f"KDE layout index out of range: {new_index}"
            )

        self._set_layout(new_index, layouts[new_index])
        return layouts[new_index]

    @staticmethod
    def _coerce_layout_list(raw) -> list:
        if raw is None:
            return []
        if isinstance(raw, str):
            return [item.strip() for item in raw.splitlines() if item.strip()]
        return [item for item in raw if str(item).strip()]

    @staticmethod
    def _layout_name_from_xkb(xkb_name: str) -> str:
        return "en" if xkb_name == "us" else xkb_name

    @staticmethod
    def _xkb_name_from_raw(raw_layout) -> str:
        text = KdeLayoutBackend._raw_layout_text(raw_layout)
        lower = text.lower()

        if isinstance(raw_layout, (tuple, list)) and raw_layout:
            first = str(raw_layout[0]).strip().lower()
            if first:
                return "us" if first == "en" else first

        if lower in {"us", "en"} or "english" in lower or "(us)" in lower:
            return "us"
        if (
            lower == "ru"
            or lower.startswith("ru(")
            or "russian" in lower
            or "рус" in lower
        ):
            return "ru"

        match = re.search(r"[a-z]{2,}", lower)
        return match.group(0) if match else lower

    @staticmethod
    def _raw_layout_text(raw_layout) -> str:
        if isinstance(raw_layout, (tuple, list)):
            return " ".join(str(part).strip() for part in raw_layout if str(part).strip())
        return str(raw_layout).strip()

    def _current_index_from_raw(self, raw_current, layouts: list[LayoutInfo]) -> int:
        if isinstance(raw_current, int):
            if 0 <= raw_current < len(layouts):
                return raw_current
            raise WaylandLayoutBackendError(
                f"KDE current layout index out of range: {raw_current}"
            )

        text = str(raw_current).strip()
        if text.isdigit():
            index = int(text)
            if 0 <= index < len(layouts):
                return index

        current_xkb = self._xkb_name_from_raw(text)
        lower = text.lower()
        for layout, raw_layout in zip(layouts, self._raw_layouts):
            if current_xkb in {layout.name, layout.xkb_name}:
                return layout.index
            if lower == self._raw_layout_text(raw_layout).lower():
                return layout.index

        raise WaylandLayoutBackendError(
            f"KDE current layout {raw_current!r} is not in configured layouts"
        )

    def _set_layout(self, new_index: int, layout: LayoutInfo) -> None:
        self.last_switch_method = None
        attempts = self._set_layout_attempts(new_index, layout)
        failures: list[str] = []
        for label, args in attempts:
            try:
                result = self.dbus.call("setLayout", *args)
                if result is False:
                    raise WaylandLayoutBackendError(f"{label} returned false")
                self.last_switch_method = label
                return
            except Exception as exc:
                failures.append(f"{label}: {exc}")

        if self._switch_layout_by_next_cycle(new_index, failures):
            return

        raise WaylandLayoutBackendError(
            "KDE keyboard D-Bus layout switch failed for all known methods: "
            + "; ".join(failures)
        )

    def _switch_layout_by_next_cycle(
        self,
        new_index: int,
        failures: list[str],
    ) -> bool:
        layouts = self.get_layouts()
        try:
            current = self.get_current_layout()
            steps = (new_index - current.index) % len(layouts)
            if steps == 0:
                self.last_switch_method = "already-current"
                return True

            for _ in range(steps):
                self.dbus.call("switchToNextLayout")

            updated = self.get_current_layout()
            if updated.index != new_index:
                raise WaylandLayoutBackendError(
                    "switchToNextLayout did not reach requested layout: "
                    f"expected index {new_index}, got {updated.index}"
                )
            self.last_switch_method = f"switchToNextLayout x{steps}"
            return True
        except Exception as exc:
            failures.append(f"switchToNextLayout: {exc}")
            return False

    def _set_layout_attempts(
        self,
        new_index: int,
        layout: LayoutInfo,
    ) -> list[tuple[str, tuple]]:
        raw_layout = self._raw_layouts[new_index] if new_index < len(self._raw_layouts) else None
        candidates: list[tuple[str, tuple]] = [
            ("setLayout(uint32)", (DbusUInt32(new_index),)),
            ("setLayout(index)", (new_index,)),
            ("setLayout(xkb_name)", (layout.xkb_name,)),
        ]

        if layout.name != layout.xkb_name:
            candidates.append(("setLayout(name)", (layout.name,)))

        if isinstance(raw_layout, (tuple, list)) and raw_layout:
            xkb_name = str(raw_layout[0]).strip()
            variant = str(raw_layout[1]).strip() if len(raw_layout) > 1 else ""
            if xkb_name:
                candidates.append(("setLayout(raw layout)", (xkb_name,)))
                candidates.append(("setLayout(raw layout, variant)", (xkb_name, variant)))

        deduped: list[tuple[str, tuple]] = []
        seen: set[tuple] = set()
        for label, args in candidates:
            if args in seen:
                continue
            seen.add(args)
            deduped.append((label, args))
        return deduped


class WaylandLayoutAdapter(_WaylandUnsupported, IXKBAdapter):
    """Wayland layout adapter with compositor-specific backend delegation."""

    _SHIFTED_EN: dict[str, str] = {
        "1": "!", "2": "@", "3": "#", "4": "$", "5": "%",
        "6": "^", "7": "&", "8": "*", "9": "(", "0": ")",
        "-": "_", "=": "+", "[": "{", "]": "}", ";": ":",
        "'": '"', ",": "<", ".": ">", "/": "?",
    }

    def __init__(
        self,
        main_thread: MainThreadInvoker,
        compositor: str = "unknown",
        debug: bool = False,
        backend=None,
        validate_backend: bool = False,
    ) -> None:
        super().__init__(compositor=compositor, debug=debug)
        self.main_thread = main_thread
        self.backend = backend
        if self.backend is None and self.compositor == "kde":
            self.backend = KdeLayoutBackend(
                KdeKeyboardDbusClient(main_thread=main_thread),
                debug=debug,
            )
        if self.backend is not None and validate_backend:
            self.backend.validate()

    def get_layouts(self) -> list[LayoutInfo]:
        if self.backend is None:
            raise self._unsupported("get_layouts")
        return self.backend.get_layouts()

    def get_current_layout(self) -> LayoutInfo:
        if self.backend is None:
            raise self._unsupported("get_current_layout")
        return self.backend.get_current_layout()

    def switch_layout(self, target: Optional[LayoutInfo] = None) -> LayoutInfo:
        if self.backend is None:
            raise self._unsupported("switch_layout")
        return self.backend.switch_layout(target=target)

    def keycode_to_char(
        self,
        keycode: int,
        layout: LayoutInfo,
        shift: bool = False,
    ) -> str:
        from lswitch.input.key_mapper import KEYCODE_TO_CHAR_EN

        ch = KEYCODE_TO_CHAR_EN.get(keycode, "")
        if not ch:
            return ""

        if shift:
            ch = ch.upper() if ch.isalpha() else self._SHIFTED_EN.get(ch, ch)

        if layout.name == "ru" or layout.xkb_name.startswith("ru"):
            from lswitch.intelligence.maps import EN_TO_RU
            return EN_TO_RU.get(ch, ch)

        return ch
