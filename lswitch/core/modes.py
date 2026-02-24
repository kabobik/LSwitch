"""Conversion mode strategy classes."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lswitch.core.states import StateContext
    from lswitch.input.virtual_keyboard import VirtualKeyboard
    from lswitch.platform.selection_adapter import ISelectionAdapter
    from lswitch.platform.system_adapter import ISystemAdapter
    from lswitch.platform.xkb_adapter import IXKBAdapter

logger = logging.getLogger(__name__)

# evdev keycodes for shift keys
KEY_LEFTSHIFT = 42
KEY_RIGHTSHIFT = 54
SHIFT_KEYS = {KEY_LEFTSHIFT, KEY_RIGHTSHIFT}
KEY_BACKSPACE = 14


class _SyntheticEvent:
    """Minimal event-like object for VirtualKeyboard.replay_events()."""
    __slots__ = ("code", "value")

    def __init__(self, code: int, value: int):
        self.code = code
        self.value = value


class BaseMode(ABC):
    @abstractmethod
    def execute(self, context: "StateContext") -> bool:
        """Execute the conversion. Returns True on success."""


class RetypeMode(BaseMode):
    """Delete typed chars, switch layout, replay events.

    Key v2 fix: Shift release is sent ONLY when the event buffer
    actually contains Shift press events.  In v1 an unconditional
    Shift release in a finally-block triggered the XKB Shift+Shift
    layout toggle — the root cause of the duplication bug.
    """

    def __init__(
        self,
        virtual_kb: "VirtualKeyboard",
        xkb: "IXKBAdapter",
        system: "ISystemAdapter",
        debug: bool = False,
    ):
        self.virtual_kb = virtual_kb
        self.xkb = xkb
        self.system = system
        self.debug = debug

    def execute(self, context: "StateContext") -> bool:
        if context.chars_in_buffer <= 0:
            return False

        # Save events before context is cleared
        saved_events = list(context.event_buffer)

        # 1. Delete typed characters
        self.virtual_kb.tap_key(KEY_BACKSPACE, context.chars_in_buffer)

        # 2. Switch layout
        self.xkb.switch_layout()

        # 3. Replay saved events
        self.virtual_kb.replay_events(saved_events)

        # 4. Release Shift ONLY for unpaired Shift presses (no matching
        #    release already in the buffer).  This avoids sending a duplicate
        #    release that would trigger the XKB Shift+Shift layout toggle.
        shift_codes_pressed: set[int] = set()
        for ev in saved_events:
            _code = getattr(ev, "code", None)
            _value = getattr(ev, "value", None)
            if _code in SHIFT_KEYS:
                if _value == 1:
                    shift_codes_pressed.add(_code)
                elif _value == 0:
                    shift_codes_pressed.discard(_code)
        if shift_codes_pressed:
            release_events = [
                _SyntheticEvent(code, 0) for code in sorted(shift_codes_pressed)
            ]
            self.virtual_kb.replay_events(release_events)

        if self.debug:
            logger.debug(
                "RetypeMode: deleted %d chars, replayed %d events, shift_release=%s",
                context.chars_in_buffer,
                len(saved_events),
                bool(shift_codes_pressed),
            )

        return True


class SelectionMode(BaseMode):
    """Read PRIMARY selection, convert text, paste back."""

    def __init__(
        self,
        selection: "ISelectionAdapter",
        xkb: "IXKBAdapter",
        system: "ISystemAdapter",
        debug: bool = False,
    ):
        self.selection = selection
        self.xkb = xkb
        self.system = system
        self.debug = debug

    def execute(self, context: "StateContext") -> bool:
        from lswitch.core.text_converter import convert_text

        sel = self.selection.get_selection()
        if not sel.text:
            return False

        converted = convert_text(sel.text)
        self.selection.replace_selection(converted)
        self.xkb.switch_layout()

        if self.debug:
            logger.debug(
                "SelectionMode: '%s' → '%s'",
                sel.text,
                converted,
            )
        return True
