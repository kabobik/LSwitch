"""Tests for Wayland platform adapters."""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest

from lswitch.platform.main_thread import DirectMainThreadInvoker
from lswitch.platform.wayland import (
    WaylandBackendNotImplementedError,
    WaylandSelectionAdapter,
    WaylandSystemAdapter,
)


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


class TestWaylandSystemAdapter:
    def test_send_key_sequence_uses_virtual_keyboard_combo(self):
        vk = MagicMock()
        adapter = WaylandSystemAdapter(
            virtual_kb=vk,
            main_thread=DirectMainThreadInvoker(),
            compositor="kde",
        )

        adapter.send_key_sequence("ctrl+v")

        vk.send_combo.assert_called_once_with("ctrl+v")

    def test_clipboard_get_set_uses_qt_clipboard(self, monkeypatch):
        clipboard = _FakeClipboard()
        clipboard.values["clipboard"] = "old"
        _install_fake_qt_clipboard(monkeypatch, clipboard)

        adapter = WaylandSystemAdapter(
            virtual_kb=MagicMock(),
            main_thread=DirectMainThreadInvoker(),
            compositor="kde",
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
        )

        with pytest.raises(WaylandBackendNotImplementedError, match="primary selection"):
            adapter.get_clipboard(selection="primary")

    def test_run_command_remains_unsupported(self):
        adapter = WaylandSystemAdapter(
            virtual_kb=MagicMock(),
            main_thread=DirectMainThreadInvoker(),
            compositor="kde",
        )

        with pytest.raises(WaylandBackendNotImplementedError, match="run_command"):
            adapter.run_command(["true"])


class _RecordingWaylandSystem:
    def __init__(self, clipboard: str = "", copy_text: str | None = None):
        self.clipboard = clipboard
        self.copy_text = copy_text
        self.keys_sent: list[str] = []
        self.clipboard_writes: list[str] = []

    def get_clipboard(self, selection: str = "primary") -> str:
        assert selection == "clipboard"
        return self.clipboard

    def set_clipboard(self, text: str, selection: str = "clipboard") -> None:
        assert selection == "clipboard"
        self.clipboard = text
        self.clipboard_writes.append(text)

    def send_key_sequence(self, sequence: str, timeout: float = 0.3) -> None:
        self.keys_sent.append(sequence)
        if sequence == "ctrl+c" and self.copy_text is not None:
            self.clipboard = self.copy_text


def _make_selection_adapter(system: _RecordingWaylandSystem) -> WaylandSelectionAdapter:
    adapter = WaylandSelectionAdapter(
        system=system,
        main_thread=DirectMainThreadInvoker(),
        compositor="kde",
    )
    adapter.COPY_WAIT_TIMEOUT = 0.01
    adapter.COPY_POLL_INTERVAL = 0.0
    adapter.PASTE_DELAY = 0.0
    adapter.RESTORE_DELAY = 0.0
    return adapter


class TestWaylandSelectionAdapter:
    def test_get_selection_copies_active_selection_to_clipboard(self):
        system = _RecordingWaylandSystem(clipboard="old", copy_text="selected")
        adapter = _make_selection_adapter(system)

        info = adapter.get_selection()

        assert info.text == "selected"
        assert info.owner_id == 0
        assert system.keys_sent == ["ctrl+c"]

    def test_get_selection_returns_empty_when_clipboard_does_not_change(self):
        system = _RecordingWaylandSystem(clipboard="old", copy_text="old")
        adapter = _make_selection_adapter(system)

        info = adapter.get_selection()

        assert info.text == ""
        assert info.owner_id == 0

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
        assert system.clipboard_writes == ["converted", "original"]

    def test_replace_selection_without_prior_copy_restores_current_clipboard(self):
        system = _RecordingWaylandSystem(clipboard="current")
        adapter = _make_selection_adapter(system)

        result = adapter.replace_selection("converted")

        assert result is True
        assert system.keys_sent == ["ctrl+v"]
        assert system.clipboard == "current"

    def test_expand_selection_to_word_expands_then_copies(self):
        system = _RecordingWaylandSystem(clipboard="old", copy_text="word")
        adapter = _make_selection_adapter(system)

        info = adapter.expand_selection_to_word()

        assert info.text == "word"
        assert system.keys_sent == ["ctrl+shift+Left", "ctrl+c"]
