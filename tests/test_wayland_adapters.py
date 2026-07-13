"""Tests for Wayland platform adapters."""

from __future__ import annotations

import importlib
import subprocess
import sys
import types
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

from lswitch.platform.main_thread import DirectMainThreadInvoker
from lswitch.platform.wayland import (
    DbusUInt32,
    KdeKeyboardDbusClient,
    KdeLayoutBackend,
    WaylandBackendNotImplementedError,
    WaylandSelectionAdapter,
    WaylandSystemAdapter,
    WaylandLayoutAdapter,
    WaylandLayoutBackendError,
)
from lswitch.platform.xkb_adapter import LayoutInfo


class _FakeClipboard:
    def __init__(self, supports_selection: bool = False):
        self._supports_selection = supports_selection
        self.values = {
            "clipboard": "",
            "selection": "",
        }

    def supportsSelection(self) -> bool:
        return self._supports_selection

    def text(self, mode) -> str:
        return self.values[mode]

    def setText(self, text: str, mode) -> None:
        self.values[mode] = text


def _install_fake_qt_clipboard(monkeypatch, clipboard: _FakeClipboard) -> None:
    pyqt6 = types.ModuleType("PyQt6")
    qtgui = types.ModuleType("PyQt6.QtGui")
    qtgui.QClipboard = types.SimpleNamespace(
        Mode=types.SimpleNamespace(
            Clipboard="clipboard",
            Selection="selection",
        )
    )
    qtgui.QGuiApplication = types.SimpleNamespace(
        clipboard=staticmethod(lambda: clipboard)
    )
    pyqt6.QtGui = qtgui
    monkeypatch.setitem(sys.modules, "PyQt6", pyqt6)
    monkeypatch.setitem(sys.modules, "PyQt6.QtGui", qtgui)


@contextmanager
def _real_pyqt_modules():
    module_names = [
        name for name in sys.modules
        if name == "PyQt6" or name.startswith("PyQt6.")
    ]
    saved = {name: sys.modules[name] for name in module_names}
    for name in module_names:
        sys.modules.pop(name, None)
    importlib.invalidate_caches()

    try:
        yield
    finally:
        for name in [
            module_name for module_name in sys.modules
            if module_name == "PyQt6" or module_name.startswith("PyQt6.")
        ]:
            sys.modules.pop(name, None)
        sys.modules.update(saved)


class TestWaylandSystemAdapter:
    def test_applies_timing_config(self):
        adapter = WaylandSystemAdapter(
            virtual_kb=MagicMock(),
            main_thread=DirectMainThreadInvoker(),
            compositor="kde",
            enable_wl_clipboard=False,
            timing={"wl_clipboard_timeout": 2.5},
        )

        assert adapter.WL_CLIPBOARD_TIMEOUT == 2.5

    def test_send_key_sequence_uses_virtual_keyboard_combo(self):
        vk = MagicMock()
        adapter = WaylandSystemAdapter(
            virtual_kb=vk,
            main_thread=DirectMainThreadInvoker(),
            compositor="kde",
            enable_wl_clipboard=False,
        )

        adapter.send_key_sequence("ctrl+v")

        vk.send_combo.assert_called_once_with("ctrl+v")

    def test_type_text_uses_virtual_keyboard(self):
        vk = MagicMock()
        adapter = WaylandSystemAdapter(
            virtual_kb=vk,
            main_thread=DirectMainThreadInvoker(),
            compositor="kde",
            enable_wl_clipboard=False,
        )
        vk.type_text.return_value = True

        assert adapter.type_text("привет", layout_name="ru") is True
        vk.type_text.assert_called_once_with("привет", layout_name="ru")

    def test_clipboard_get_set_uses_qt_clipboard(self, monkeypatch):
        clipboard = _FakeClipboard()
        clipboard.values["clipboard"] = "old"
        _install_fake_qt_clipboard(monkeypatch, clipboard)

        adapter = WaylandSystemAdapter(
            virtual_kb=MagicMock(),
            main_thread=DirectMainThreadInvoker(),
            compositor="kde",
            enable_wl_clipboard=False,
        )

        assert adapter.get_clipboard(selection="clipboard") == "old"
        adapter.set_clipboard("new", selection="clipboard")
        assert clipboard.values["clipboard"] == "new"

    def test_primary_selection_uses_qt_selection_when_supported(self, monkeypatch):
        clipboard = _FakeClipboard(supports_selection=True)
        clipboard.values["selection"] = "selected"
        _install_fake_qt_clipboard(monkeypatch, clipboard)

        adapter = WaylandSystemAdapter(
            virtual_kb=MagicMock(),
            main_thread=DirectMainThreadInvoker(),
            compositor="kde",
            enable_wl_clipboard=False,
        )

        assert adapter.get_clipboard(selection="primary") == "selected"
        adapter.set_clipboard("changed", selection="primary")
        assert clipboard.values["selection"] == "changed"

    def test_primary_selection_fails_when_qt_does_not_support_it(self, monkeypatch):
        clipboard = _FakeClipboard(supports_selection=False)
        _install_fake_qt_clipboard(monkeypatch, clipboard)

        adapter = WaylandSystemAdapter(
            virtual_kb=MagicMock(),
            main_thread=DirectMainThreadInvoker(),
            compositor="kde",
            enable_wl_clipboard=False,
        )

        with pytest.raises(WaylandBackendNotImplementedError, match="primary selection"):
            adapter.get_clipboard(selection="primary")

    def test_run_command_remains_unsupported(self):
        adapter = WaylandSystemAdapter(
            virtual_kb=MagicMock(),
            main_thread=DirectMainThreadInvoker(),
            compositor="kde",
            enable_wl_clipboard=False,
        )

        with pytest.raises(WaylandBackendNotImplementedError, match="run_command"):
            adapter.run_command(["true"])

    def test_clipboard_get_uses_wl_paste_when_available(self):
        calls = []

        def runner(args, **kwargs):
            calls.append((args, kwargs))
            return subprocess.CompletedProcess(args, 0, stdout="global", stderr="")

        adapter = WaylandSystemAdapter(
            virtual_kb=MagicMock(),
            main_thread=DirectMainThreadInvoker(),
            compositor="kde",
            command_lookup=lambda command: f"/usr/bin/{command}",
            command_runner=runner,
        )

        assert adapter.get_clipboard(selection="clipboard") == "global"
        assert calls[0][0] == ["wl-paste", "--no-newline"]

    def test_primary_clipboard_get_uses_wl_paste_without_extra_newline(self):
        calls = []

        def runner(args, **kwargs):
            calls.append((args, kwargs))
            return subprocess.CompletedProcess(args, 0, stdout="primary", stderr="")

        adapter = WaylandSystemAdapter(
            virtual_kb=MagicMock(),
            main_thread=DirectMainThreadInvoker(),
            compositor="kde",
            command_lookup=lambda command: f"/usr/bin/{command}",
            command_runner=runner,
        )

        assert adapter.get_clipboard(selection="primary") == "primary"
        assert calls[0][0] == ["wl-paste", "--no-newline", "--primary"]

    def test_primary_clipboard_get_empty_does_not_fall_back_to_stale_qt(
        self,
        monkeypatch,
    ):
        clipboard = _FakeClipboard(supports_selection=True)
        clipboard.values["selection"] = "stale"
        _install_fake_qt_clipboard(monkeypatch, clipboard)

        def runner(args, **kwargs):
            return subprocess.CompletedProcess(
                args,
                1,
                stdout="",
                stderr="nothing is copied",
            )

        adapter = WaylandSystemAdapter(
            virtual_kb=MagicMock(),
            main_thread=DirectMainThreadInvoker(),
            compositor="kde",
            command_lookup=lambda command: f"/usr/bin/{command}",
            command_runner=runner,
        )

        assert adapter.get_clipboard(selection="primary") == ""

    def test_clipboard_set_uses_wl_copy_when_available(self):
        calls = []

        def runner(args, **kwargs):
            calls.append((args, kwargs))
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

        adapter = WaylandSystemAdapter(
            virtual_kb=MagicMock(),
            main_thread=DirectMainThreadInvoker(),
            compositor="kde",
            command_lookup=lambda command: f"/usr/bin/{command}",
            command_runner=runner,
        )

        adapter.set_clipboard("new", selection="clipboard")

        assert calls[0][0] == ["wl-copy"]
        assert calls[0][1]["input"] == "new"
        assert "capture_output" not in calls[0][1]
        assert calls[0][1]["stdout"] is subprocess.DEVNULL
        assert calls[0][1]["stderr"] is subprocess.DEVNULL

    def test_clipboard_mime_set_uses_wl_copy_type_when_available(self):
        calls = []

        def runner(args, **kwargs):
            calls.append((args, kwargs))
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

        adapter = WaylandSystemAdapter(
            virtual_kb=MagicMock(),
            main_thread=DirectMainThreadInvoker(),
            compositor="kde",
            command_lookup=lambda command: f"/usr/bin/{command}",
            command_runner=runner,
        )

        adapter.set_clipboard_mime(
            "marker",
            selection="clipboard",
            mime_type="application/x-lswitch-copy-sentinel",
        )

        assert calls[0][0] == [
            "wl-copy",
            "--type",
            "application/x-lswitch-copy-sentinel",
        ]
        assert calls[0][1]["input"] == "marker"

    def test_clipboard_get_falls_back_to_qt_when_wl_paste_fails(self, monkeypatch):
        clipboard = _FakeClipboard()
        clipboard.values["clipboard"] = "qt"
        _install_fake_qt_clipboard(monkeypatch, clipboard)

        def runner(args, **kwargs):
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="no data")

        adapter = WaylandSystemAdapter(
            virtual_kb=MagicMock(),
            main_thread=DirectMainThreadInvoker(),
            compositor="kde",
            command_lookup=lambda command: f"/usr/bin/{command}",
            command_runner=runner,
        )

        assert adapter.get_clipboard(selection="clipboard") == "qt"


class _RecordingWaylandSystem:
    def __init__(
        self,
        clipboard: str = "",
        primary: str = "",
        copy_text: str | None = None,
        copy_text_by_sequence: dict[str, str | None] | None = None,
    ):
        self.clipboard = clipboard
        self.primary = primary
        self.copy_text = copy_text
        self.copy_text_by_sequence = copy_text_by_sequence or {}
        self.keys_sent: list[str] = []
        self.typed_text: list[tuple[str, str]] = []
        self.clipboard_writes: list[str] = []
        self.clipboard_mime_writes: list[tuple[str, str]] = []

    def get_clipboard(self, selection: str = "primary") -> str:
        assert selection in {"clipboard", "primary"}
        if selection == "primary":
            return self.primary
        return self.clipboard

    def set_clipboard(self, text: str, selection: str = "clipboard") -> None:
        assert selection == "clipboard"
        self.clipboard = text
        self.clipboard_writes.append(text)

    def set_clipboard_mime(
        self,
        text: str,
        selection: str = "clipboard",
        mime_type: str = "text/plain;charset=utf-8",
    ) -> None:
        assert selection == "clipboard"
        self.clipboard = text
        self.clipboard_mime_writes.append((mime_type, text))

    def send_key_sequence(self, sequence: str, timeout: float = 0.3) -> None:
        self.keys_sent.append(sequence)
        if sequence in self.copy_text_by_sequence:
            text = self.copy_text_by_sequence[sequence]
            if text is not None:
                self.clipboard = text
        elif sequence == "ctrl+c" and self.copy_text is not None:
            self.clipboard = self.copy_text

    def type_text(self, text: str, layout_name: str = "en") -> bool:
        self.typed_text.append((text, layout_name))
        return True


class _ExpandablePrimarySystem(_RecordingWaylandSystem):
    def __init__(self, sequence_text: dict[tuple[str, int], str], primary: str = "tim"):
        super().__init__(primary=primary)
        self.sequence_text = sequence_text
        self.sequence_counts: dict[str, int] = {}

    def send_key_sequence(self, sequence: str, timeout: float = 0.3) -> None:
        self.keys_sent.append(sequence)
        count = self.sequence_counts.get(sequence, 0) + 1
        self.sequence_counts[sequence] = count
        text = self.sequence_text.get((sequence, count))
        if text is not None:
            self.primary = text


def _make_selection_adapter(system: _RecordingWaylandSystem) -> WaylandSelectionAdapter:
    adapter = WaylandSelectionAdapter(
        system=system,
        main_thread=DirectMainThreadInvoker(),
        compositor="kde",
    )
    adapter.COPY_WAIT_TIMEOUT = 0.01
    adapter.COPY_POLL_INTERVAL = 0.0
    adapter.COPY_RETRY_DELAY = 0.0
    adapter.PASTE_DELAY = 0.0
    adapter.RESTORE_DELAY = 0.0
    adapter.EXPAND_SELECTION_DELAY = 0.0
    return adapter


def _make_primary_selection_adapter(
    system: _RecordingWaylandSystem,
) -> WaylandSelectionAdapter:
    adapter = _make_selection_adapter(system)
    adapter.strategy = "primary_selection"
    return adapter


class TestWaylandSelectionAdapter:
    def test_get_selection_copies_active_selection_to_clipboard(self):
        system = _RecordingWaylandSystem(clipboard="old", copy_text="selected")
        adapter = _make_selection_adapter(system)

        info = adapter.get_selection()

        assert info.text == "selected"
        assert info.owner_id == 0
        assert system.keys_sent == ["ctrl+c"]

    def test_get_passive_selection_reads_primary_without_copy_shortcut(self):
        system = _RecordingWaylandSystem(clipboard="old", primary="selected")
        adapter = _make_selection_adapter(system)

        info = adapter.get_passive_selection()

        assert info.text == "selected"
        assert info.owner_id == 0
        assert system.keys_sent == []
        assert system.clipboard == "old"

    def test_auto_get_selection_prefers_passive_primary(self):
        system = _RecordingWaylandSystem(
            clipboard="old",
            primary="selected",
            copy_text="copied",
        )
        adapter = _make_selection_adapter(system)

        info = adapter.get_selection()

        assert info.text == "selected"
        assert system.keys_sent == []
        assert system.clipboard == "old"

    def test_primary_strategy_get_selection_never_sends_copy_shortcut(self):
        system = _RecordingWaylandSystem(
            clipboard="old",
            primary="selected",
            copy_text="copied",
        )
        adapter = _make_primary_selection_adapter(system)

        info = adapter.get_selection()

        assert info.text == "selected"
        assert system.keys_sent == []
        assert system.clipboard == "old"

    def test_get_selection_returns_same_text_as_old_clipboard(self):
        system = _RecordingWaylandSystem(clipboard="old", copy_text="old")
        adapter = _make_selection_adapter(system)

        info = adapter.get_selection()

        assert info.text == "old"
        assert info.owner_id == 0

    def test_get_selection_falls_back_to_ctrl_insert_copy(self):
        system = _RecordingWaylandSystem(
            clipboard="old",
            copy_text_by_sequence={
                "ctrl+c": None,
                "ctrl+insert": "selected",
            },
        )
        adapter = _make_selection_adapter(system)

        info = adapter.get_selection()

        assert info.text == "selected"
        assert info.owner_id == 0
        assert system.keys_sent == ["ctrl+c", "ctrl+insert"]

    def test_get_selection_returns_empty_and_restores_clipboard_when_copy_fails(self):
        system = _RecordingWaylandSystem(clipboard="old", copy_text=None)
        adapter = _make_selection_adapter(system)

        info = adapter.get_selection()

        assert info.text == ""
        assert info.owner_id == 0
        assert system.clipboard == "old"
        assert system.clipboard_mime_writes[0][0] == adapter.COPY_SENTINEL_MIME_TYPE
        assert system.clipboard_mime_writes[0][1].startswith(adapter.COPY_SENTINEL_PREFIX)
        assert system.clipboard_writes == ["old"]

    def test_has_fresh_selection_ignores_empty_copy(self):
        system = _RecordingWaylandSystem(clipboard="", copy_text="")
        adapter = _make_selection_adapter(system)

        assert adapter.has_fresh_selection() is False

    def test_replace_selection_pastes_and_restores_original_clipboard(self):
        system = _RecordingWaylandSystem(clipboard="original", copy_text="selected")
        adapter = _make_selection_adapter(system)

        adapter.get_selection()
        result = adapter.replace_selection("converted")

        assert result is True
        assert system.keys_sent == ["ctrl+c", "ctrl+v"]
        assert system.clipboard == "original"
        assert system.clipboard_mime_writes[0][0] == adapter.COPY_SENTINEL_MIME_TYPE
        assert system.clipboard_mime_writes[0][1].startswith(adapter.COPY_SENTINEL_PREFIX)
        assert system.clipboard_writes == ["converted", "original"]

    def test_replace_selection_without_prior_copy_restores_current_clipboard(self):
        system = _RecordingWaylandSystem(clipboard="current")
        adapter = _make_selection_adapter(system)

        result = adapter.replace_selection("converted")

        assert result is True
        assert system.keys_sent == ["ctrl+v"]
        assert system.clipboard == "current"

    def test_primary_strategy_replace_selection_does_not_paste(self):
        system = _RecordingWaylandSystem(clipboard="current", primary="selected")
        adapter = _make_primary_selection_adapter(system)

        result = adapter.replace_selection("converted")

        assert result is False
        assert system.keys_sent == []
        assert system.clipboard == "current"

    def test_applies_timing_config(self):
        system = _RecordingWaylandSystem(clipboard="current", primary="selected")
        adapter = WaylandSelectionAdapter(
            system=system,
            main_thread=DirectMainThreadInvoker(),
            compositor="kde",
            timing={
                "copy_wait_timeout": 0.2,
                "copy_poll_interval": 0.03,
                "copy_retry_delay": 0.04,
                "paste_delay": 0.05,
                "restore_delay": 0.06,
                "expand_selection_delay": 0.07,
            },
        )

        assert adapter.COPY_WAIT_TIMEOUT == 0.2
        assert adapter.COPY_POLL_INTERVAL == 0.03
        assert adapter.COPY_RETRY_DELAY == 0.04
        assert adapter.PASTE_DELAY == 0.05
        assert adapter.RESTORE_DELAY == 0.06
        assert adapter.EXPAND_SELECTION_DELAY == 0.07

    def test_primary_strategy_replace_selection_by_typing(self):
        system = _RecordingWaylandSystem(clipboard="current", primary="selected")
        adapter = _make_primary_selection_adapter(system)

        result = adapter.replace_selection_by_typing("привет", layout_name="ru")

        assert result is True
        assert system.typed_text == [("привет", "ru")]
        assert system.keys_sent == []
        assert system.clipboard == "current"

    def test_expand_selection_to_word_expands_then_copies(self):
        system = _RecordingWaylandSystem(clipboard="old", copy_text="word")
        adapter = _make_selection_adapter(system)

        info = adapter.expand_selection_to_word()

        assert info.text == "word"
        assert system.keys_sent == ["ctrl+shift+Left", "ctrl+c", "shift+Left", "ctrl+c"]

    def test_primary_strategy_expand_reads_primary_without_copy(self):
        system = _RecordingWaylandSystem(clipboard="old", primary="word", copy_text="copied")
        adapter = _make_primary_selection_adapter(system)

        info = adapter.expand_selection_to_word()

        assert info.text == "word"
        assert system.keys_sent == ["ctrl+shift+Left", "shift+Left"]
        assert system.clipboard == "old"

    def test_primary_strategy_expands_through_layout_punctuation(self):
        system = _ExpandablePrimarySystem(
            primary="tim",
            sequence_text={
                ("ctrl+shift+Left", 1): "tim",
                ("shift+Left", 1): ";tim",
                ("shift+Left", 2): "j;tim",
                ("shift+Left", 3): "vj;tim",
                ("shift+Left", 4): "cvj;tim",
                ("shift+Left", 5): " cvj;tim",
                ("shift+Right", 1): "cvj;tim",
            },
        )
        adapter = _make_primary_selection_adapter(system)

        info = adapter.expand_selection_to_word()

        assert info.text == "cvj;tim"
        assert system.keys_sent == [
            "ctrl+shift+Left",
            "shift+Left",
            "shift+Left",
            "shift+Left",
            "shift+Left",
            "shift+Left",
            "shift+Right",
        ]

    def test_primary_strategy_does_not_expand_through_space(self):
        system = _ExpandablePrimarySystem(
            primary="tim",
            sequence_text={
                ("ctrl+shift+Left", 1): "tim",
                ("shift+Left", 1): " tim",
                ("shift+Right", 1): "tim",
            },
        )
        adapter = _make_primary_selection_adapter(system)

        info = adapter.expand_selection_to_word()

        assert info.text == "tim"
        assert system.keys_sent == ["ctrl+shift+Left", "shift+Left", "shift+Right"]

    def test_invalid_strategy_fails_clearly(self):
        system = _RecordingWaylandSystem()

        with pytest.raises(ValueError, match="Invalid Wayland selection strategy"):
            WaylandSelectionAdapter(
                system=system,
                main_thread=DirectMainThreadInvoker(),
                compositor="kde",
                strategy="magic",
            )


class _FakeKdeDbus:
    def __init__(self, layouts=None, current=0, accepted_set_layout_signature: str = "index"):
        self.layouts = layouts if layouts is not None else ["English (US)", "Russian"]
        self.current = current
        self.accepted_set_layout_signature = accepted_set_layout_signature
        self.calls: list[tuple[str, tuple]] = []

    def call(self, method: str, *args):
        self.calls.append((method, args))
        if method == "getLayoutsList":
            return self.layouts
        if method == "getLayout":
            return self.current
        if method == "setLayout":
            if self.accepted_set_layout_signature == "uint32":
                if not (len(args) == 1 and isinstance(args[0], DbusUInt32)):
                    raise RuntimeError(f"bad signature {args!r}")
            elif self.accepted_set_layout_signature == "index":
                if not (len(args) == 1 and isinstance(args[0], int)):
                    raise RuntimeError(f"bad signature {args!r}")
            elif self.accepted_set_layout_signature == "layout":
                if not (len(args) == 1 and isinstance(args[0], str)):
                    raise RuntimeError(f"bad signature {args!r}")
            elif self.accepted_set_layout_signature == "layout_variant":
                if not (
                    len(args) == 2
                    and isinstance(args[0], str)
                    and isinstance(args[1], str)
                ):
                    raise RuntimeError(f"bad signature {args!r}")
            elif self.accepted_set_layout_signature == "next":
                raise RuntimeError("No such method 'setLayout'")
            elif self.accepted_set_layout_signature == "none":
                raise RuntimeError("No such method 'setLayout'")
            self.current = args[0].value if isinstance(args[0], DbusUInt32) else args[0]
            return None
        if method == "switchToNextLayout":
            if self.accepted_set_layout_signature == "none":
                raise RuntimeError("No such method 'switchToNextLayout'")
            self.current = (self._current_index() + 1) % len(self.layouts)
            return None
        raise AssertionError(f"Unexpected method: {method}")

    def _current_index(self) -> int:
        if isinstance(self.current, int):
            return self.current

        text = str(self.current).strip().lower()
        if text.isdigit():
            return int(text)

        for index, layout in enumerate(self.layouts):
            raw_text = KdeLayoutBackend._raw_layout_text(layout).lower()
            if text and (text == raw_text or text in raw_text):
                return index
        return 0


class TestKdeLayoutBackend:
    def test_get_layouts_maps_kde_display_names_to_layout_info(self):
        backend = KdeLayoutBackend(_FakeKdeDbus())

        layouts = backend.get_layouts()

        assert layouts == [
            LayoutInfo(name="en", index=0, xkb_name="us"),
            LayoutInfo(name="ru", index=1, xkb_name="ru"),
        ]

    def test_get_layouts_maps_real_qtdbus_tuple_rows_to_layout_info(self):
        backend = KdeLayoutBackend(_FakeKdeDbus(
            layouts=[("us", "", "English (US)"), ("ru", "", "Russian")]
        ))

        layouts = backend.get_layouts()

        assert layouts == [
            LayoutInfo(name="en", index=0, xkb_name="us"),
            LayoutInfo(name="ru", index=1, xkb_name="ru"),
        ]

    def test_get_current_layout_by_index(self):
        backend = KdeLayoutBackend(_FakeKdeDbus(current=1))

        assert backend.get_current_layout().name == "ru"

    def test_get_current_layout_by_display_name(self):
        backend = KdeLayoutBackend(_FakeKdeDbus(current="Russian"))

        assert backend.get_current_layout().name == "ru"

    def test_switch_layout_to_target_calls_set_layout_uint32_first(self):
        dbus = _FakeKdeDbus(current=0, accepted_set_layout_signature="uint32")
        backend = KdeLayoutBackend(dbus)
        target = LayoutInfo(name="ru", index=1, xkb_name="ru")

        result = backend.switch_layout(target=target)

        assert result.name == "ru"
        assert ("setLayout", (DbusUInt32(1),)) in dbus.calls
        assert ("setLayout", (1,)) not in dbus.calls
        assert backend.last_switch_method == "setLayout(uint32)"

    def test_switch_layout_falls_back_to_signed_index_signature(self):
        dbus = _FakeKdeDbus(current=0)
        backend = KdeLayoutBackend(dbus)
        target = LayoutInfo(name="ru", index=1, xkb_name="ru")

        result = backend.switch_layout(target=target)

        assert result.name == "ru"
        assert ("setLayout", (DbusUInt32(1),)) in dbus.calls
        assert ("setLayout", (1,)) in dbus.calls
        assert backend.last_switch_method == "setLayout(index)"

    def test_switch_layout_without_target_cycles(self):
        dbus = _FakeKdeDbus(current=0)
        backend = KdeLayoutBackend(dbus)

        result = backend.switch_layout()

        assert result.name == "ru"
        assert ("setLayout", (DbusUInt32(1),)) in dbus.calls
        assert ("setLayout", (1,)) in dbus.calls

    def test_switch_layout_falls_back_to_xkb_name_signature(self):
        dbus = _FakeKdeDbus(
            layouts=[("us", "", "English (US)"), ("ru", "", "Russian")],
            current=0,
            accepted_set_layout_signature="layout",
        )
        backend = KdeLayoutBackend(dbus)

        result = backend.switch_layout()

        assert result.name == "ru"
        assert ("setLayout", (DbusUInt32(1),)) in dbus.calls
        assert ("setLayout", (1,)) in dbus.calls
        assert ("setLayout", ("ru",)) in dbus.calls

    def test_switch_layout_falls_back_to_layout_variant_signature(self):
        dbus = _FakeKdeDbus(
            layouts=[("us", "", "English (US)"), ("ru", "", "Russian")],
            current=0,
            accepted_set_layout_signature="layout_variant",
        )
        backend = KdeLayoutBackend(dbus)

        result = backend.switch_layout()

        assert result.name == "ru"
        assert ("setLayout", (DbusUInt32(1),)) in dbus.calls
        assert ("setLayout", ("ru", "")) in dbus.calls

    def test_switch_layout_falls_back_to_switch_to_next_layout(self):
        dbus = _FakeKdeDbus(
            layouts=[("us", "", "English (US)"), ("ru", "", "Russian")],
            current=0,
            accepted_set_layout_signature="next",
        )
        backend = KdeLayoutBackend(dbus)

        result = backend.switch_layout()

        assert result.name == "ru"
        assert ("setLayout", (DbusUInt32(1),)) in dbus.calls
        assert ("setLayout", (1,)) in dbus.calls
        assert ("setLayout", ("ru", "")) in dbus.calls
        assert ("switchToNextLayout", ()) in dbus.calls
        assert dbus.current == 1
        assert backend.last_switch_method == "switchToNextLayout x1"

    def test_switch_layout_reports_all_failures_when_kde_methods_are_missing(self):
        dbus = _FakeKdeDbus(
            layouts=[("us", "", "English (US)"), ("ru", "", "Russian")],
            current=0,
            accepted_set_layout_signature="none",
        )
        backend = KdeLayoutBackend(dbus)

        with pytest.raises(
            WaylandLayoutBackendError,
            match="layout switch failed for all known methods",
        ) as exc_info:
            backend.switch_layout()

        message = str(exc_info.value)
        assert "setLayout(uint32)" in message
        assert "setLayout(index)" in message
        assert "switchToNextLayout" in message

    def test_dbus_uint32_rejects_invalid_values(self):
        with pytest.raises(ValueError, match="out of range"):
            DbusUInt32(-1)
        with pytest.raises(ValueError, match="out of range"):
            DbusUInt32(0x100000000)

    def test_dbus_uint32_converts_to_qtdbus_uint_variant(self):
        with _real_pyqt_modules():
            try:
                qtcore = importlib.import_module("PyQt6.QtCore")
            except ImportError:
                pytest.skip("real PyQt6.QtCore is not available")
            if not hasattr(qtcore, "QMetaType") or not hasattr(qtcore, "QVariant"):
                pytest.skip("real PyQt6.QtCore is not available")

            arg = KdeKeyboardDbusClient._qtdbus_argument(DbusUInt32(1))

            assert arg.typeName() == "uint"
            assert arg.value() == 1

    def test_empty_layout_list_fails_clearly(self):
        backend = KdeLayoutBackend(_FakeKdeDbus(layouts=[]))

        with pytest.raises(WaylandLayoutBackendError, match="no layouts"):
            backend.get_layouts()


class TestWaylandLayoutAdapter:
    def test_delegates_layout_operations_to_backend(self):
        backend = KdeLayoutBackend(_FakeKdeDbus(current=0))
        adapter = WaylandLayoutAdapter(
            main_thread=DirectMainThreadInvoker(),
            compositor="kde",
            backend=backend,
        )

        assert [layout.name for layout in adapter.get_layouts()] == ["en", "ru"]
        assert adapter.get_current_layout().name == "en"
        assert adapter.switch_layout().name == "ru"

    def test_validate_backend_when_requested(self):
        backend = MagicMock()

        WaylandLayoutAdapter(
            main_thread=DirectMainThreadInvoker(),
            compositor="kde",
            backend=backend,
            validate_backend=True,
        )

        backend.validate.assert_called_once()

    def test_non_kde_layout_backend_fails_fast(self):
        adapter = WaylandLayoutAdapter(
            main_thread=DirectMainThreadInvoker(),
            compositor="unknown",
        )

        with pytest.raises(WaylandBackendNotImplementedError, match="get_layouts"):
            adapter.get_layouts()

    def test_keycode_to_char_supports_us_and_ru_mvp(self):
        adapter = WaylandLayoutAdapter(
            main_thread=DirectMainThreadInvoker(),
            compositor="unknown",
        )
        en = LayoutInfo(name="en", index=0, xkb_name="us")
        ru = LayoutInfo(name="ru", index=1, xkb_name="ru")

        assert adapter.keycode_to_char(16, en) == "q"
        assert adapter.keycode_to_char(16, ru) == "й"
        assert adapter.keycode_to_char(51, ru) == "б"
        assert adapter.keycode_to_char(52, ru) == "ю"
        assert adapter.keycode_to_char(39, ru) == "ж"

    def test_keycode_to_char_supports_shift_for_ru_punctuation(self):
        adapter = WaylandLayoutAdapter(
            main_thread=DirectMainThreadInvoker(),
            compositor="unknown",
        )
        ru = LayoutInfo(name="ru", index=1, xkb_name="ru")

        assert adapter.keycode_to_char(51, ru, shift=True) == "Б"
        assert adapter.keycode_to_char(52, ru, shift=True) == "Ю"
        assert adapter.keycode_to_char(39, ru, shift=True) == "Ж"
