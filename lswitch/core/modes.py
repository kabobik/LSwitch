"""Conversion mode strategy classes."""

from __future__ import annotations

import logging
import time
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
            logger.debug("RetypeMode: skip — chars_in_buffer=%d", context.chars_in_buffer)
            return False

        # Save events before context is cleared
        saved_events = list(context.event_buffer)
        n_chars = context.chars_in_buffer

        if self.debug:
            logger.debug(
                "RetypeMode: start — chars=%d, buffer_events=%d, event_codes=%s",
                n_chars,
                len(saved_events),
                [getattr(e, 'code', '?') for e in saved_events],
            )

        # 1. Delete typed characters
        logger.debug("RetypeMode: sending %d backspaces", n_chars)
        self.virtual_kb.tap_key(KEY_BACKSPACE, n_chars)

        # 2. Switch layout BEFORE replay so events land in the correct layout.
        # We switch here (not after) so the XKB group is set when UInput events
        # are processed. The system Shift+Shift shortcut may fire afterwards
        # (after replay) and switch back — that's a separate GNOME/KDE setting
        # users should disable in keyboard preferences.
        try:
            new_layout = self.xkb.switch_layout()
            logger.debug("RetypeMode: switched layout → %s", getattr(new_layout, 'name', new_layout))
        except Exception as exc:
            logger.error("RetypeMode: switch_layout failed: %s", exc)
            return False

        # 3. Brief pause so the application finishes processing the backspaces
        # before receiving the replayed characters.
        time.sleep(0.05)

        # 4. Replay saved events.
        # event_buffer contains KEY_PRESS events only (value=1).
        # replay_events() automatically appends synthetic releases so that
        # the kernel does not trigger infinite auto-repeat (value=2).
        if self.debug:
            logger.debug(
                "RetypeMode: replaying %d events (codes=%s)",
                len(saved_events),
                [getattr(e, 'code', '?') for e in saved_events],
            )
        self.virtual_kb.replay_events(saved_events)

        logger.debug(
            "RetypeMode: done — deleted=%d, replayed=%d",
            n_chars,
            len(saved_events),
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
        from lswitch.core.text_converter import convert_text, detect_language

        sel = self.selection.get_selection()
        if not sel.text:
            return False

        # Detect source language to determine conversion direction and
        # which layout to switch to after replacing the selection.
        source_lang = detect_language(sel.text)  # 'en' or 'ru'
        target_lang = "ru" if source_lang == "en" else "en"
        direction = "en_to_ru" if source_lang == "en" else "ru_to_en"

        converted = convert_text(sel.text, direction=direction)
        self.selection.replace_selection(converted)

        # Switch to the layout that matches the converted text.
        layouts = self.xkb.get_layouts()
        target_layout = next(
            (l for l in layouts if l.name == target_lang),
            None,
        )
        self.xkb.switch_layout(target=target_layout)  # None = cycle, which is ok as fallback

        logger.debug(
            "SelectionMode: '%s' (%s) → '%s' (%s), switching to layout '%s'",
            sel.text[:50], source_lang,
            converted[:50], target_lang,
            target_layout.name if target_layout else "next",
        )
        return True
