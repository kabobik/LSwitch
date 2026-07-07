"""Typed buffer helpers for key-event based text tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from lswitch.input.key_mapper import keycode_to_char

if TYPE_CHECKING:
    from lswitch.core.states import StateContext
    from lswitch.platform.xkb_adapter import IXKBAdapter, LayoutInfo


@dataclass(frozen=True)
class TypedToken:
    """A decoded token backed by the original physical key events."""

    text: str
    events: list = field(default_factory=list)
    has_trailing_space: bool = False

    @property
    def length(self) -> int:
        return len(self.events)


@dataclass(frozen=True)
class RetypeBufferPreparation:
    events: list
    count: int
    original_count: int = 0
    restored_from_sticky: bool = False
    trimmed_to_last_word: bool = False
    trailing_space_count: int = 0


class TypedBufferService:
    """Owns low-level operations on ``StateContext.event_buffer``.

    The service intentionally preserves the current buffer semantics: the
    buffer stores key press events only, while ``chars_in_buffer`` is maintained
    separately because Backspace press/release handling updates them at
    different points in the input flow.
    """

    def append_event(self, context: "StateContext", event_data, *, shifted: bool) -> None:
        event_data.shifted = shifted
        context.event_buffer.append(event_data)
        context.chars_in_buffer += 1

    def pop_event(self, context: "StateContext"):
        if not context.event_buffer:
            return None
        return context.event_buffer.pop()

    def decrement_count(self, context: "StateContext") -> None:
        if context.chars_in_buffer > 0:
            context.chars_in_buffer -= 1

    def decode(self, events: list | None = None) -> str:
        chars = []
        for event in events or []:
            ch = keycode_to_char(
                event.code,
                shift=getattr(event, "shifted", False),
            )
            chars.append(ch if ch else "?")
        return "".join(chars)

    def last_word(
        self,
        context: "StateContext",
        *,
        current_layout: "LayoutInfo | None" = None,
        xkb: "IXKBAdapter | None" = None,
    ) -> TypedToken:
        """Return the last word-like run from the context buffer.

        This mirrors the legacy ``LSwitchApp._extract_last_word_events()``
        behavior: trailing spaces/control keys are skipped, and the scan stops
        only on word boundary control keys. Non-alpha printable keys are kept
        for compatibility with existing auto-conversion tests and edge cases.
        """
        from lswitch.core.event_manager import (
            KEY_BACKSPACE,
            KEY_ENTER,
            KEY_ESC,
            KEY_SPACE,
            KEY_TAB,
        )

        boundary_keys = {KEY_SPACE, KEY_ENTER, KEY_TAB, KEY_ESC, KEY_BACKSPACE}
        word_events: list = []
        chars: list[str] = []
        has_trailing_space = False
        skipping_trailing = True

        for event in reversed(context.event_buffer):
            if event.code in boundary_keys:
                if skipping_trailing:
                    has_trailing_space = has_trailing_space or event.code == KEY_SPACE
                    continue
                break

            skipping_trailing = False
            if current_layout is not None and xkb is not None:
                ch = xkb.keycode_to_char(
                    event.code,
                    current_layout,
                )
            else:
                ch = keycode_to_char(event.code)

            if ch:
                chars.append(ch)
            word_events.append(event)

        word_events.reverse()
        chars.reverse()
        return TypedToken(
            text="".join(chars),
            events=word_events,
            has_trailing_space=has_trailing_space,
        )

    def prepare_retype_buffer(
        self,
        context: "StateContext",
        *,
        sticky_events: list,
        selection_valid: bool,
        current_layout: "LayoutInfo | None" = None,
        xkb: "IXKBAdapter | None" = None,
    ) -> RetypeBufferPreparation:
        """Prepare context buffer for retype conversion.

        This preserves the legacy behavior from ``LSwitchApp._do_conversion``:
        repeat Shift+Shift can restore the sticky retype buffer, and multi-word
        buffers are trimmed to the last word for retype mode while preserving
        trailing spaces for the Backspace count.
        """
        saved_events = list(context.event_buffer)
        saved_count = context.chars_in_buffer
        original_count = saved_count
        restored = False
        trimmed_to_last_word = False
        trailing_space_count = 0

        if saved_count == 0 and sticky_events:
            saved_events = list(sticky_events)
            saved_count = len(saved_events)
            original_count = saved_count
            context.event_buffer = list(saved_events)
            context.chars_in_buffer = saved_count
            restored = True

        if saved_count > 0 and not selection_valid:
            token = self.last_word(
                context,
                current_layout=current_layout,
                xkb=xkb,
            )
            last_word_events = token.events
            if last_word_events and len(last_word_events) < saved_count:
                from lswitch.core.event_manager import KEY_SPACE

                trailing = []
                for event in reversed(saved_events):
                    if event.code == KEY_SPACE:
                        trailing.append(event)
                    else:
                        break
                trailing.reverse()
                trimmed = last_word_events + trailing
                trailing_space_count = len(trailing)
                saved_events = trimmed
                saved_count = len(trimmed)
                context.event_buffer = list(trimmed)
                context.chars_in_buffer = saved_count
                trimmed_to_last_word = True

        return RetypeBufferPreparation(
            events=saved_events,
            count=saved_count,
            original_count=original_count,
            restored_from_sticky=restored,
            trimmed_to_last_word=trimmed_to_last_word,
            trailing_space_count=trailing_space_count,
        )
