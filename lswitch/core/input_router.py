"""Input event routing facade."""

from __future__ import annotations

import logging
from collections.abc import Callable
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
        decode_buffer: Callable[[], str],
        auto_conversion_enabled: Callable[[], bool],
        try_auto_conversion_at_space: Callable[[], bool],
        get_pending_auto_space: Callable[[], bool],
        set_pending_auto_space: Callable[[bool], None],
        clear_last_retype_events: Callable[[], None],
        clear_last_auto_marker: Callable[[], None],
        inject_deferred_space: Callable[[], None],
        request_conversion: Callable[[], None],
        prime_selection_baseline_on_click: Callable[[], None],
        on_mouse_release: Callable[[Event], None],
    ):
        self.state_manager = state_manager
        self.typed_buffer = typed_buffer
        self.selection_tracker = selection_tracker
        self.decode_buffer = decode_buffer
        self.auto_conversion_enabled = auto_conversion_enabled
        self.try_auto_conversion_at_space = try_auto_conversion_at_space
        self.get_pending_auto_space = get_pending_auto_space
        self.set_pending_auto_space = set_pending_auto_space
        self.clear_last_retype_events = clear_last_retype_events
        self.clear_last_auto_marker = clear_last_auto_marker
        self.inject_deferred_space = inject_deferred_space
        self.request_conversion = request_conversion
        self.prime_selection_baseline_on_click = prime_selection_baseline_on_click
        self._on_mouse_release = on_mouse_release

    def on_key_press(self, event: Event) -> None:
        data = event.data
        logger.trace(  # type: ignore[attr-defined]
            "KeyPress: code=%d dev=%s | state=%s buf=%d",
            data.code,
            data.device_name,
            self.state_manager.state.name,
            self.state_manager.context.chars_in_buffer,
        )

        if self.get_pending_auto_space():
            if data.code not in MODIFIER_KEYS and data.code != KEY_SPACE:
                self.set_pending_auto_space(False)
                logger.debug(
                    "Canceled pending auto-space due to rollover of key %d",
                    data.code,
                )

        if data.code in SHIFT_KEYS:
            self.state_manager.on_shift_down()
        elif data.code in MODIFIER_KEYS:
            pass
        elif data.code == KEY_BACKSPACE:
            ctx = self.state_manager.context
            self.typed_buffer.pop_event(ctx)
            logger.trace(  # type: ignore[attr-defined]
                "Buffer -[BS] → %r (%d chars)",
                self.decode_buffer(),
                self.state_manager.context.chars_in_buffer,
            )
            ctx.backspace_repeats = 0
            self._clear_selection_state()
        elif data.code == KEY_SPACE:
            if self.auto_conversion_enabled():
                if self.try_auto_conversion_at_space():
                    self.selection_tracker.clear_repeat()
                    return
            self._append_text_event(data)
        else:
            self._append_text_event(data)

    def on_key_release(self, event: Event) -> None:
        data = event.data
        if data.code == KEY_SPACE and self.get_pending_auto_space():
            self.set_pending_auto_space(False)
            try:
                self.inject_deferred_space()
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
                self.request_conversion()
        elif data.code in NAVIGATION_KEYS:
            self._handle_navigation()
        elif data.code == KEY_ENTER:
            self._handle_navigation()
        elif data.code == KEY_BACKSPACE:
            self.state_manager.context.backspace_repeats = 0
            self.typed_buffer.decrement_count(self.state_manager.context)

    def on_key_repeat(self, event: Event) -> None:
        data = event.data
        if data.code == KEY_BACKSPACE:
            ctx = self.state_manager.context
            ctx.backspace_repeats += 1
            self.typed_buffer.pop_event(ctx)
            logger.trace(  # type: ignore[attr-defined]
                "Buffer -[BS repeat] → %r (%d chars)",
                self.decode_buffer(),
                len(self.state_manager.context.event_buffer),
            )
            self.typed_buffer.decrement_count(ctx)
            if ctx.backspace_repeats >= 3:
                self.state_manager.on_backspace_hold()

    def on_mouse_click(self, event: Event) -> None:
        self.clear_last_auto_marker()
        self._clear_selection_state()
        self.prime_selection_baseline_on_click()
        self.state_manager.on_mouse_click()

    def on_mouse_release(self, event: Event) -> None:
        self._on_mouse_release(event)

    def _append_text_event(self, data) -> None:
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
            self.decode_buffer(),
            self.state_manager.context.chars_in_buffer,
        )
        self.state_manager.context.backspace_repeats = 0
        self._clear_selection_state()

    def _clear_selection_state(self) -> None:
        self.selection_tracker.set_valid(False)
        self.selection_tracker.clear_repeat()
        self.clear_last_retype_events()

    def _handle_navigation(self) -> None:
        self.clear_last_auto_marker()
        self._clear_selection_state()
        self.state_manager.on_navigation()
