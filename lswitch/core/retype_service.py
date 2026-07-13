"""Shared typed-event retype primitive."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lswitch.input.virtual_keyboard import VirtualKeyboard
    from lswitch.platform.xkb_adapter import IXKBAdapter, LayoutInfo

logger = logging.getLogger(__name__)

KEY_BACKSPACE = 14


class RetypeService:
    """Delete typed characters, switch layout, and replay physical events."""

    def __init__(
        self,
        virtual_kb: "VirtualKeyboard",
        xkb: "IXKBAdapter",
        *,
        debug: bool = False,
    ):
        self.virtual_kb = virtual_kb
        self.xkb = xkb
        self.debug = debug

    def retype_events(
        self,
        events: list,
        *,
        delete_count: int,
        target_layout: "LayoutInfo | None" = None,
        switch_to_next: bool = False,
        before_replay_delay: float = 0.05,
        backspace_n_times_keyword: bool = False,
    ) -> bool:
        if delete_count <= 0:
            logger.debug("RetypeService: skip — delete_count=%d", delete_count)
            return False

        saved_events = list(events)
        if self.debug:
            logger.debug(
                "RetypeService: start — delete=%d, events=%d, codes=%s",
                delete_count,
                len(saved_events),
                [getattr(event, "code", "?") for event in saved_events],
            )

        logger.debug("RetypeService: sending %d backspaces", delete_count)
        if backspace_n_times_keyword:
            self.virtual_kb.tap_key(KEY_BACKSPACE, n_times=delete_count)
        else:
            self.virtual_kb.tap_key(KEY_BACKSPACE, delete_count)

        try:
            if target_layout is not None:
                new_layout = self.xkb.switch_layout(target=target_layout)
            elif switch_to_next:
                new_layout = self.xkb.switch_layout()
            else:
                new_layout = None
            if new_layout is not None:
                logger.debug(
                    "RetypeService: switched layout → %s",
                    getattr(new_layout, "name", new_layout),
                )
        except Exception as exc:
            logger.error("RetypeService: switch_layout failed: %s", exc)
            return False

        time.sleep(before_replay_delay)

        if self.debug:
            logger.debug(
                "RetypeService: replaying %d events (codes=%s)",
                len(saved_events),
                [getattr(event, "code", "?") for event in saved_events],
            )
        self.virtual_kb.replay_events(saved_events)

        logger.debug(
            "RetypeService: done — deleted=%d, replayed=%d",
            delete_count,
            len(saved_events),
        )
        return True
