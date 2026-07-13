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
        timing: dict | None = None,
        layout_switch_controller=None,
    ):
        self.virtual_kb = virtual_kb
        self.xkb = xkb
        self.system = system
        self.debug = debug
        self.layout_switch_controller = layout_switch_controller
        timing = timing or {}
        self.before_replay_delay = float(
            timing.get("retype_before_replay_delay", 0.05)
        )
        self.last_trace_steps = ()

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

        from lswitch.core.retype_service import RetypeService

        service = RetypeService(
            self.virtual_kb,
            self.xkb,
            debug=self.debug,
            layout_switch_controller=self.layout_switch_controller,
        )
        success = service.retype_events(
            saved_events,
            delete_count=n_chars,
            switch_to_next=True,
            before_replay_delay=self.before_replay_delay,
        )
        self.last_trace_steps = service.last_trace_steps
        return success


class SelectionMode(BaseMode):
    """Read PRIMARY selection, convert text, paste back."""

    def __init__(
        self,
        selection: "ISelectionAdapter",
        xkb: "IXKBAdapter",
        system: "ISystemAdapter",
        debug: bool = False,
        expand: bool = False,
        timing: dict | None = None,
        layout_switch_controller=None,
    ):
        self.selection = selection
        self.xkb = xkb
        self.system = system
        self.debug = debug
        self.expand = expand
        self.layout_switch_controller = layout_switch_controller
        self.last_original: str = ""
        self.last_converted: str = ""
        self.last_target_lang: str | None = None
        timing = timing or {}
        self.direct_type_after_layout_switch_delay = float(
            timing.get("direct_type_after_layout_switch_delay", 0.03)
        )

    def execute(self, context: "StateContext") -> bool:
        from lswitch.core.text_converter import invert_layout_runs

        self.last_original = ""
        self.last_converted = ""
        self.last_target_lang = None

        if self.expand or context.backspace_hold_active:
            logger.debug(f"SelectionMode: expanding selection... (expand={self.expand}, backspace_hold={context.backspace_hold_active})")
            sel = self.selection.expand_selection_to_word()
        else:
            sel = self.selection.get_selection()

        if not sel.text:
            return False

        # Selection can contain fragments from both layouts. Convert each
        # alphabet run independently instead of forcing one global direction
        # for the whole selection.
        converted_runs = invert_layout_runs(sel.text)
        converted = "".join(text for text, _target_lang in converted_runs)
        target_langs = [lang for _text, lang in converted_runs if lang]
        final_target_lang = target_langs[-1] if target_langs else None

        layouts = self.xkb.get_layouts()
        target_layout = self._find_layout_for_lang(layouts, final_target_lang)
        operation = (
            self.layout_switch_controller.begin_operation()
            if self.layout_switch_controller is not None
            else None
        )

        direct_replacement = None
        if getattr(type(self.selection), "prefers_direct_replacement", None) is not None:
            direct_replacement = getattr(
                self.selection,
                "prefers_direct_replacement",
                None,
            )
        if callable(direct_replacement) and direct_replacement():
            replace_by_typing = getattr(self.selection, "replace_selection_by_typing")
            if not callable(replace_by_typing):
                return False
            fallback_lang = final_target_lang or "en"
            for run_text, run_lang in converted_runs:
                layout = self._find_layout_for_lang(layouts, run_lang or fallback_lang)
                if layout is None:
                    logger.debug(
                        "SelectionMode: direct replacement skipped, no target layout for %s",
                        run_lang or fallback_lang,
                    )
                    if operation is not None:
                        operation.finish(success=False)
                    return False
                try:
                    if operation is not None:
                        operation.switch_to(layout)
                    else:
                        self.xkb.switch_layout(target=layout)
                except Exception as exc:
                    logger.error("SelectionMode: layout switch failed: %s", exc)
                    if operation is not None:
                        operation.finish(success=False)
                    return False
                time.sleep(self.direct_type_after_layout_switch_delay)
                if not replace_by_typing(run_text, layout_name=layout.name):
                    if operation is not None:
                        operation.finish(success=False)
                    return False
        else:
            if not self.selection.replace_selection(converted):
                return False
            try:
                if operation is None:
                    self.xkb.switch_layout(target=target_layout)
                elif operation.keep_target_after_conversion:
                    operation.switch_to(target_layout)
            except Exception as exc:
                logger.error("SelectionMode: layout switch failed: %s", exc)
                if operation is not None:
                    operation.finish(success=False)
                return False

        if operation is not None:
            operation.finish(success=True)

        logger.debug(
            "SelectionMode: '%s' → '%s', target_langs=%s, switching to layout '%s'",
            sel.text[:50],
            converted[:50],
            target_langs,
            target_layout.name if target_layout else "next",
        )
        self.last_original = sel.text
        self.last_converted = converted
        self.last_target_lang = final_target_lang
        return True

    @staticmethod
    def _find_layout_for_lang(layouts, lang: str | None):
        from lswitch.core.layout_service import LayoutService

        return LayoutService.find_layout_for_lang(layouts, lang)
