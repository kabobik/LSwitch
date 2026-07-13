"""Input event routing facade."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from lswitch.core.events import Event
from lswitch.core.event_manager import (
    KEY_BACKSPACE,
    KEY_ENTER,
    KEY_SPACE,
    MODIFIER_KEYS,
    NAVIGATION_KEYS,
    SHIFT_KEYS,
)
from lswitch.input.key_mapper import keycode_to_char

if TYPE_CHECKING:
    from lswitch.core.selection_tracker import SelectionFreshnessTracker
    from lswitch.core.state_manager import StateManager
    from lswitch.core.typed_buffer import TypedBufferService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InputConversionPort:
    decode_buffer: Callable[[], str]
    auto_conversion_enabled: Callable[[], bool]
    try_auto_conversion_at_space: Callable[[int], bool]
    mid_word_auto_conversion_enabled: Callable[[], bool]
    try_mid_word_auto_conversion: Callable[[int], bool]
    get_pending_auto_space: Callable[[], bool]
    set_pending_auto_space: Callable[[bool], None]
    clear_last_retype_events: Callable[[], None]
    clear_last_auto_marker: Callable[[], None]
    inject_deferred_space: Callable[[], None]
    request_conversion: Callable[[], None]
    close_trace_session: Callable[[int], None] = lambda correlation_id: None


@dataclass(frozen=True)
class InputSelectionPort:
    prime_baseline_on_click: Callable[[], None]
    read_mouse_release_selection: Callable[[], object | None]


class InputEventRouter:
    """Routes input events to the current input handlers.

    The first migration step keeps behavior in the existing handlers while
    moving EventBus wiring to a dedicated object. Later steps can move routing
    branches here without changing the public app facade.
    """

    def __init__(
        self,
        *,
        state_manager: "StateManager",
        typed_buffer: "TypedBufferService",
        selection_tracker: "SelectionFreshnessTracker",
        conversion: InputConversionPort,
        selection: InputSelectionPort,
    ):
        self.state_manager = state_manager
        self.typed_buffer = typed_buffer
        self.selection_tracker = selection_tracker
        self.conversion = conversion
        self.selection = selection
        self._pressed_text_keys: set[int] = set()
        self._active_word_session_id: int | None = None
        self._word_was_auto_converted = False
        self._next_word_session_id = 1

    @property
    def active_word_session_id(self) -> int | None:
        return self._active_word_session_id

    def on_key_press(self, event: Event) -> None:
        data = event.data
        logger.trace(  # type: ignore[attr-defined]
            "KeyPress: code=%d dev=%s | state=%s buf=%d",
            data.code,
            data.device_name,
            self.state_manager.state.name,
            self.state_manager.context.chars_in_buffer,
        )

        if self.conversion.get_pending_auto_space():
            if data.code not in MODIFIER_KEYS and data.code != KEY_SPACE:
                self.conversion.set_pending_auto_space(False)
                logger.debug(
                    "Canceled pending auto-space due to rollover of key %d",
                    data.code,
                )

        if data.code in SHIFT_KEYS:
            self.state_manager.on_shift_down()
        elif data.code in MODIFIER_KEYS:
            pass
        elif data.code == KEY_BACKSPACE:
            self._pressed_text_keys.clear()
            ctx = self.state_manager.context
            self.typed_buffer.pop_event(ctx)
            logger.trace(  # type: ignore[attr-defined]
                "Buffer -[BS] → %r (%d chars)",
                self.conversion.decode_buffer(),
                self.state_manager.context.chars_in_buffer,
            )
            ctx.backspace_repeats = 0
            self._clear_selection_state()
        elif data.code == KEY_SPACE:
            self._pressed_text_keys.clear()
            correlation_id = self._word_session_for_boundary()
            try:
                if self._word_was_auto_converted:
                    # A user/system mid-word decision already handled this
                    # visible word. Space only finalizes it and expires undo.
                    self.conversion.clear_last_auto_marker()
                    consumed = False
                else:
                    consumed = (
                        self.conversion.auto_conversion_enabled()
                        and self.conversion.try_auto_conversion_at_space(
                            correlation_id,
                        )
                    )
            finally:
                self._close_word_session()
            if consumed:
                self.selection_tracker.clear_repeat()
                return
            self._append_text_event(data, allow_mid_word=False)
        else:
            self._append_text_event(data, allow_mid_word=True)

    def on_key_release(self, event: Event) -> None:
        data = event.data
        if data.code == KEY_SPACE and self.conversion.get_pending_auto_space():
            self.conversion.set_pending_auto_space(False)
            try:
                self.conversion.inject_deferred_space()
            except Exception as exc:
                logger.error("Failed to inject deferred auto-space: %s", exc)

        if data.code in SHIFT_KEYS:
            is_double = self.state_manager.on_shift_up()
            if is_double:
                logger.debug(
                    "DoubleShift detected → _do_conversion() "
                    "[sel_valid=%s, sel_repeat=%s, chars=%d]",
                    self.selection_tracker.valid,
                    self.selection_tracker.repeat_valid,
                    self.state_manager.context.chars_in_buffer,
                )
                try:
                    self.conversion.request_conversion()
                finally:
                    self._close_word_session()
        elif data.code in NAVIGATION_KEYS:
            self._handle_navigation()
        elif data.code == KEY_ENTER:
            self._handle_navigation()
        elif data.code == KEY_BACKSPACE:
            self.state_manager.context.backspace_repeats = 0
            self.typed_buffer.decrement_count(self.state_manager.context)
        elif data.code in self._pressed_text_keys:
            self._pressed_text_keys.discard(data.code)
            if (
                not self._pressed_text_keys
                and not self._word_was_auto_converted
                and self.conversion.mid_word_auto_conversion_enabled()
            ):
                logger.trace(  # type: ignore[attr-defined]
                    "Mid-word check after key release: code=%d buf=%d",
                    data.code,
                    self.state_manager.context.chars_in_buffer,
                )
                correlation_id = self._ensure_word_session()
                if self.conversion.try_mid_word_auto_conversion(correlation_id):
                    self._word_was_auto_converted = True
                    self.selection_tracker.clear_repeat()
                    # Retype resets the input buffer, so finalize this trace
                    # segment.  The visible word is still being typed: keep
                    # its correlation ID until a real word boundary.
                    self.conversion.close_trace_session(correlation_id)

    def on_key_repeat(self, event: Event) -> None:
        data = event.data
        if data.code == KEY_BACKSPACE:
            ctx = self.state_manager.context
            ctx.backspace_repeats += 1
            self.typed_buffer.pop_event(ctx)
            logger.trace(  # type: ignore[attr-defined]
                "Buffer -[BS repeat] → %r (%d chars)",
                self.conversion.decode_buffer(),
                len(self.state_manager.context.event_buffer),
            )
            self.typed_buffer.decrement_count(ctx)
            if ctx.backspace_repeats >= 3:
                self.state_manager.on_backspace_hold()
        elif data.code in self._pressed_text_keys:
            # The buffer stores one press event, while the focused application
            # may receive many repeated characters. Retyping that incomplete
            # buffer would delete/replay the wrong number of characters.
            self._pressed_text_keys.clear()

    def on_mouse_click(self, event: Event) -> None:
        self._pressed_text_keys.clear()
        self._close_word_session()
        self.conversion.clear_last_auto_marker()
        self._clear_selection_state()
        self.selection.prime_baseline_on_click()
        self.state_manager.on_mouse_click()

    def on_mouse_release(self, event: Event) -> None:
        try:
            info = self.selection.read_mouse_release_selection()
            if info is None:
                return
            text = getattr(info, "text", "") or ""
            owner_id = getattr(info, "owner_id", 0)
            result = self.selection_tracker.on_release_selection(text, owner_id)
            if result == "empty":
                logger.trace(  # type: ignore[attr-defined]
                    "MouseRelease: selection empty"
                )
                return
            if result == "initial":
                logger.trace(  # type: ignore[attr-defined]
                    "MouseRelease: initial selection baseline — text=%r",
                    text[:50],
                )
                return
            if result == "fresh":
                logger.debug(
                    "MouseRelease: fresh selection — text=%r owner=0x%x",
                    text[:50],
                    owner_id,
                )
            else:
                logger.trace(  # type: ignore[attr-defined]
                    "MouseRelease: selection unchanged — text=%r",
                    text[:50],
                )
        except Exception:
            pass

    def _append_text_event(self, data, *, allow_mid_word: bool = False) -> None:
        if allow_mid_word and keycode_to_char(
            data.code,
            shift=self.state_manager.context.shift_pressed,
        ):
            self._ensure_word_session()
        self.state_manager.on_key_press(data.code)
        self.typed_buffer.append_event(
            self.state_manager.context,
            data,
            shifted=self.state_manager.context.shift_pressed,
        )
        logger.trace(  # type: ignore[attr-defined]
            "Buffer +[%d:%s] → %r (%d chars)",
            data.code,
            keycode_to_char(data.code, shift=data.shifted) or "?",
            self.conversion.decode_buffer(),
            self.state_manager.context.chars_in_buffer,
        )
        self.state_manager.context.backspace_repeats = 0
        self._clear_selection_state()
        if allow_mid_word:
            self._pressed_text_keys.add(data.code)

    def _clear_selection_state(self) -> None:
        self.selection_tracker.set_valid(False)
        self.selection_tracker.clear_repeat()
        self.conversion.clear_last_retype_events()

    def _handle_navigation(self) -> None:
        self._pressed_text_keys.clear()
        self._close_word_session()
        self.conversion.clear_last_auto_marker()
        self._clear_selection_state()
        self.state_manager.on_navigation()

    def _ensure_word_session(self) -> int:
        if self._active_word_session_id is None:
            self._active_word_session_id = self._next_word_session_id
            self._next_word_session_id += 1
        return self._active_word_session_id

    def _word_session_for_boundary(self) -> int:
        if (
            self._active_word_session_id is None
            and self.state_manager.context.chars_in_buffer > 0
        ):
            return self._ensure_word_session()
        return self._active_word_session_id or 0

    def _close_word_session(self) -> None:
        correlation_id = self._active_word_session_id
        self._word_was_auto_converted = False
        if correlation_id is None:
            return
        self._active_word_session_id = None
        self.conversion.close_trace_session(correlation_id)
