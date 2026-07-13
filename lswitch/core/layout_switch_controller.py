"""Verified layout switching with a live-configurable shortcut fallback."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

from lswitch.platform.xkb_adapter import LayoutInfo


logger = logging.getLogger(__name__)


class LayoutSwitchError(RuntimeError):
    """Raised when neither the direct backend nor shortcut fallback succeeds."""


_ALIASES = {
    "ctrl": "Ctrl",
    "control": "Ctrl",
    "ctrl_l": "Ctrl",
    "control_l": "Ctrl",
    "leftctrl": "Ctrl",
    "ctrl_r": "Ctrl",
    "control_r": "Ctrl",
    "rightctrl": "Ctrl",
    "alt": "Alt",
    "alt_l": "Alt",
    "leftalt": "Alt",
    "alt_r": "Alt",
    "rightalt": "Alt",
    "shift": "Shift",
    "shift_l": "Shift",
    "leftshift": "Shift",
    "shift_r": "Shift",
    "rightshift": "Shift",
    "meta": "Meta",
    "super": "Meta",
    "win": "Meta",
    "meta_l": "Meta",
    "super_l": "Meta",
    "leftmeta": "Meta",
    "meta_r": "Meta",
    "super_r": "Meta",
    "rightmeta": "Meta",
    "space": "Space",
    "caps_lock": "CapsLock",
    "capslock": "CapsLock",
    "tab": "Tab",
    "enter": "Enter",
    "return": "Enter",
    "esc": "Escape",
    "escape": "Escape",
    "insert": "Insert",
    "ins": "Insert",
    "left": "Left",
    "right": "Right",
    "up": "Up",
    "down": "Down",
}
_MODIFIER_ORDER = {"Ctrl": 0, "Alt": 1, "Shift": 2, "Meta": 3}


@dataclass(frozen=True)
class ParsedKeySequence:
    """Canonical single keyboard combination accepted by VirtualKeyboard."""

    keys: tuple[str, ...]

    @property
    def canonical(self) -> str:
        return "+".join(self.keys)


def parse_key_sequence(value: str) -> ParsedKeySequence:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("layout_switch_key must be a non-empty shortcut")
    raw_parts = value.split("+")
    if any(not part.strip() for part in raw_parts):
        raise ValueError(f"Invalid layout_switch_key shortcut: {value!r}")

    normalized: list[str] = []
    for part in raw_parts:
        raw = part.strip()
        lower = raw.lower().replace("-", "_").replace(" ", "_")
        key = _ALIASES.get(lower)
        if key is None and len(lower) == 1 and lower.isalnum():
            key = lower.upper()
        if key is None and lower.startswith("f") and lower[1:].isdigit():
            number = int(lower[1:])
            if 1 <= number <= 12:
                key = f"F{number}"
        if key is None:
            raise ValueError(
                f"Unsupported key {raw!r} in layout_switch_key shortcut"
            )
        if key in normalized:
            raise ValueError(
                f"Duplicate key {key!r} in layout_switch_key shortcut"
            )
        normalized.append(key)

    modifiers = sorted(
        (key for key in normalized if key in _MODIFIER_ORDER),
        key=_MODIFIER_ORDER.__getitem__,
    )
    regular = [key for key in normalized if key not in _MODIFIER_ORDER]
    if len(regular) > 1:
        raise ValueError(
            "layout_switch_key must contain at most one non-modifier key"
        )
    return ParsedKeySequence(tuple(modifiers + regular))


def normalize_key_sequence(value: str) -> str:
    return parse_key_sequence(value).canonical


@dataclass(frozen=True)
class LayoutSwitchPolicy:
    keep_target_after_conversion: bool
    fallback_shortcut: ParsedKeySequence


class LayoutSwitchOperation:
    """One conversion's stable policy and source-layout snapshot."""

    def __init__(
        self,
        controller: "LayoutSwitchController",
        *,
        source_layout: LayoutInfo | None,
        policy: LayoutSwitchPolicy,
    ) -> None:
        self.controller = controller
        self.source_layout = source_layout
        self.policy = policy
        self.switched = False

    @property
    def keep_target_after_conversion(self) -> bool:
        return self.policy.keep_target_after_conversion

    def switch_to(self, target: LayoutInfo | None = None) -> LayoutInfo:
        result = self.controller.switch_to(target, policy=self.policy)
        self.switched = self.source_layout is None or not _same_layout(
            result,
            self.source_layout,
        )
        return result

    def finish(self, *, success: bool) -> None:
        if (
            self.policy.keep_target_after_conversion
            or not self.switched
            or self.source_layout is None
        ):
            return
        try:
            self.controller.switch_to(self.source_layout, policy=self.policy)
            self.switched = False
        except Exception as exc:
            logger.error(
                "Could not restore source layout %s after conversion (success=%s): %s",
                self.source_layout.name,
                success,
                exc,
            )


class LayoutSwitchController:
    """Prefer exact backend switching and verify a shortcut fallback."""

    def __init__(
        self,
        *,
        xkb,
        virtual_kb,
        keep_target_after_conversion: bool = True,
        fallback_shortcut: str = "Alt+Shift",
    ) -> None:
        self.xkb = xkb
        self.virtual_kb = virtual_kb
        self._lock = threading.RLock()
        self._policy = LayoutSwitchPolicy(
            keep_target_after_conversion=bool(keep_target_after_conversion),
            fallback_shortcut=parse_key_sequence(fallback_shortcut),
        )

    def reconfigure(
        self,
        *,
        keep_target_after_conversion: bool,
        fallback_shortcut: str,
    ) -> None:
        parsed = parse_key_sequence(fallback_shortcut)
        with self._lock:
            self._policy = LayoutSwitchPolicy(
                keep_target_after_conversion=bool(keep_target_after_conversion),
                fallback_shortcut=parsed,
            )

    def policy_snapshot(self) -> LayoutSwitchPolicy:
        with self._lock:
            return self._policy

    def begin_operation(self) -> LayoutSwitchOperation:
        try:
            source = self.xkb.get_current_layout()
        except Exception:
            source = None
        return LayoutSwitchOperation(
            self,
            source_layout=source,
            policy=self.policy_snapshot(),
        )

    def switch_to(
        self,
        target: LayoutInfo | None = None,
        *,
        policy: LayoutSwitchPolicy | None = None,
    ) -> LayoutInfo:
        policy = policy or self.policy_snapshot()
        try:
            before = self.xkb.get_current_layout()
        except Exception:
            before = None
        try:
            direct_result = self.xkb.switch_layout(target=target)
            current = self.xkb.get_current_layout()
            if target is None and (
                before is None or not _same_layout(current, before)
            ):
                return current or direct_result
            if target is not None and _same_layout(current, target):
                return current or direct_result
            expected = target.name if target is not None else "a different layout"
            raise LayoutSwitchError(
                f"backend reached {current.name!r}, expected {expected!r}"
            )
        except Exception as direct_error:
            logger.warning(
                "Direct layout switch failed, trying shortcut: %s",
                direct_error,
            )
            return self._fallback_switch(target, policy=policy, cause=direct_error)

    def _fallback_switch(
        self,
        target: LayoutInfo | None,
        *,
        policy: LayoutSwitchPolicy,
        cause: Exception,
    ) -> LayoutInfo:
        if self.virtual_kb is None:
            raise LayoutSwitchError(
                f"Layout switch failed and shortcut fallback is unavailable: {cause}"
            ) from cause
        try:
            layouts = list(self.xkb.get_layouts())
            before = self.xkb.get_current_layout()
        except Exception as exc:
            raise LayoutSwitchError(
                f"Could not inspect layouts for shortcut fallback: {exc}"
            ) from cause

        if target is not None and _same_layout(before, target):
            return before

        max_steps = 1 if target is None else max(0, len(layouts) - 1)
        for _ in range(max_steps):
            self.virtual_kb.send_combo(policy.fallback_shortcut.canonical)
            current = self.xkb.get_current_layout()
            if target is None:
                if not _same_layout(current, before):
                    return current
            elif _same_layout(current, target):
                return current
        target_name = target.name if target is not None else "next layout"
        raise LayoutSwitchError(
            f"Shortcut {policy.fallback_shortcut.canonical!r} did not reach {target_name}"
        ) from cause


def _same_layout(left: LayoutInfo | None, right: LayoutInfo | None) -> bool:
    if left is None or right is None:
        return left is right
    return left.index == right.index and (
        left.xkb_name == right.xkb_name or left.name == right.name
    )
