"""Tests for verified layout switching and conversion policy snapshots."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from lswitch.core.layout_switch_controller import (
    LayoutSwitchController,
    LayoutSwitchError,
    normalize_key_sequence,
    parse_key_sequence,
)
from lswitch.platform.xkb_adapter import LayoutInfo
from tests.conftest import MockXKBAdapter


@pytest.mark.parametrize(
    ("raw", "canonical"),
    [
        ("Alt_L+Shift_L", "Alt+Shift"),
        ("Ctrl_L+Shift_L", "Ctrl+Shift"),
        ("Caps_Lock", "CapsLock"),
        ("Meta+Space", "Meta+Space"),
        ("shift+ctrl+l", "Ctrl+Shift+L"),
    ],
)
def test_shortcut_parser_normalizes_legacy_and_gui_formats(raw, canonical):
    parsed = parse_key_sequence(raw)

    assert parsed.canonical == canonical
    assert normalize_key_sequence(raw) == canonical


@pytest.mark.parametrize(
    "raw",
    ["", "Alt++Shift", "Hyper+Space", "Ctrl+Ctrl", "A+B"],
)
def test_shortcut_parser_rejects_invalid_combinations(raw):
    with pytest.raises(ValueError):
        parse_key_sequence(raw)


def test_direct_target_switch_is_verified():
    xkb = MockXKBAdapter(["en", "ru", "de"])
    controller = LayoutSwitchController(xkb=xkb, virtual_kb=MagicMock())
    target = xkb.get_layouts()[2]

    result = controller.switch_to(target)

    assert result is target
    assert xkb.get_current_layout() is target
    assert xkb.switch_calls == [target]


class _FallbackKeyboard:
    def __init__(self, xkb):
        self.xkb = xkb
        self.sequences = []

    def send_combo(self, sequence: str) -> None:
        self.sequences.append(sequence)
        self.xkb.cycle_from_shortcut()


class _FallbackXkb:
    def __init__(self, *, advance_on_shortcut: bool = True):
        self.layouts = [
            LayoutInfo("en", 0, "us"),
            LayoutInfo("ru", 1, "ru"),
            LayoutInfo("de", 2, "de"),
        ]
        self.current = 0
        self.advance_on_shortcut = advance_on_shortcut
        self.direct_calls = []

    def get_layouts(self):
        return self.layouts

    def get_current_layout(self):
        return self.layouts[self.current]

    def switch_layout(self, target=None):
        self.direct_calls.append(target)
        raise RuntimeError("direct backend unavailable")

    def cycle_from_shortcut(self):
        if self.advance_on_shortcut:
            self.current = (self.current + 1) % len(self.layouts)


def test_fallback_reaches_exact_target_in_bounded_multi_layout_cycle():
    xkb = _FallbackXkb()
    keyboard = _FallbackKeyboard(xkb)
    controller = LayoutSwitchController(
        xkb=xkb,
        virtual_kb=keyboard,
        fallback_shortcut="Ctrl_L+Shift_L",
    )

    result = controller.switch_to(xkb.layouts[2])

    assert result is xkb.layouts[2]
    assert keyboard.sequences == ["Ctrl+Shift", "Ctrl+Shift"]


def test_fallback_failure_is_bounded_and_explicit():
    xkb = _FallbackXkb(advance_on_shortcut=False)
    keyboard = _FallbackKeyboard(xkb)
    controller = LayoutSwitchController(xkb=xkb, virtual_kb=keyboard)

    with pytest.raises(LayoutSwitchError, match="did not reach de"):
        controller.switch_to(xkb.layouts[2])

    assert keyboard.sequences == ["Alt+Shift", "Alt+Shift"]


def test_operation_restores_source_when_policy_disables_keep_target():
    xkb = MockXKBAdapter()
    controller = LayoutSwitchController(
        xkb=xkb,
        virtual_kb=MagicMock(),
        keep_target_after_conversion=False,
    )
    source = xkb.get_current_layout()
    target = xkb.get_layouts()[1]
    operation = controller.begin_operation()

    operation.switch_to(target)
    operation.finish(success=True)

    assert xkb.get_current_layout() is source
    assert xkb.switch_calls == [target, source]


def test_operation_uses_stable_policy_while_next_operation_gets_live_update():
    xkb = MockXKBAdapter()
    controller = LayoutSwitchController(
        xkb=xkb,
        virtual_kb=MagicMock(),
        keep_target_after_conversion=False,
    )
    old_operation = controller.begin_operation()
    controller.reconfigure(
        keep_target_after_conversion=True,
        fallback_shortcut="Caps_Lock",
    )

    assert old_operation.keep_target_after_conversion is False
    assert controller.begin_operation().keep_target_after_conversion is True
    assert controller.policy_snapshot().fallback_shortcut.canonical == "CapsLock"
