"""Application-level conversion use cases."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from lswitch.core.auto_marker import AutoConversionMarker

if TYPE_CHECKING:
    from lswitch.input.virtual_keyboard import VirtualKeyboard
    from lswitch.platform.xkb_adapter import IXKBAdapter
    from lswitch.core.learning_service import LearningService
    from lswitch.intelligence.user_dictionary import UserDictionary

logger = logging.getLogger(__name__)

KEY_BACKSPACE = 14
KEY_SPACE = 57


class UndoAutoConversionUseCase:
    """Undo the latest automatic conversion and record a keep correction."""

    def __init__(
        self,
        *,
        virtual_kb: "VirtualKeyboard",
        xkb: "IXKBAdapter",
        user_dict: "UserDictionary | None" = None,
        learning_service: "LearningService | None" = None,
        timing: dict | None = None,
        debug: bool = False,
    ):
        self.virtual_kb = virtual_kb
        self.xkb = xkb
        if learning_service is None:
            from lswitch.core.learning_service import LearningService

            learning_service = LearningService(user_dict, debug=debug)
        self.learning_service = learning_service
        self.timing = timing or {}
        self.debug = debug

    def execute(self, marker: AutoConversionMarker) -> bool:
        self.learning_service.record_auto_undo_correction(marker)

        try:
            self.virtual_kb.tap_key(
                KEY_BACKSPACE,
                n_times=marker.converted_len + (1 if marker.had_space else 0),
            )
            target = self._find_layout_for_lang(marker.original_lang)
            if target is not None:
                self.xkb.switch_layout(target=target)
            time.sleep(self.timing.get("undo_before_replay_delay", 0.03))
            self.virtual_kb.replay_events(marker.word_events)
            if marker.had_space:
                self.virtual_kb.tap_key(KEY_SPACE)
            return True
        except Exception as exc:
            logger.error("Undo auto-conversion failed: %s", exc)
            return False

    def _find_layout_for_lang(self, lang: str):
        if self.xkb is None:
            return None
        try:
            return next(
                (
                    layout
                    for layout in self.xkb.get_layouts()
                    if layout.name.lower().startswith(lang)
                ),
                None,
            )
        except Exception:
            return None
