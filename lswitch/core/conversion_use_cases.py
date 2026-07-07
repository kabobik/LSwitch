"""Application-level conversion use cases."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from lswitch.core.auto_marker import AutoConversionMarker

if TYPE_CHECKING:
    from lswitch.core.conversion_engine import ConversionEngine
    from lswitch.input.virtual_keyboard import VirtualKeyboard
    from lswitch.platform.xkb_adapter import IXKBAdapter
    from lswitch.core.learning_service import LearningService
    from lswitch.core.learning_service import PendingManualLearning
    from lswitch.core.selection_tracker import SelectionFreshnessTracker
    from lswitch.intelligence.user_dictionary import UserDictionary
    from lswitch.core.states import StateContext

logger = logging.getLogger(__name__)

KEY_BACKSPACE = 14
KEY_SPACE = 57


@dataclass(frozen=True)
class ManualConversionResult:
    success: bool
    sticky_events: list


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


class PostConversionStateUpdater:
    """Update repeat-selection and sticky-retype state after conversion."""

    def __init__(self, selection_tracker: "SelectionFreshnessTracker"):
        self.selection_tracker = selection_tracker

    def update(
        self,
        *,
        success: bool,
        saved_count: int,
        saved_events: list,
        selection_valid_for_convert: bool,
    ) -> list:
        if success and saved_count == 0 and selection_valid_for_convert:
            self.selection_tracker.mark_repeat_for_current_generation()
        elif not success:
            self.selection_tracker.clear_repeat()

        if success and saved_count > 0 and not selection_valid_for_convert:
            return list(saved_events)
        return []


class ManualConversionUseCase:
    """Execute manual conversion and related learning/state updates."""

    def __init__(
        self,
        *,
        conversion_engine: "ConversionEngine",
        learning_service: "LearningService",
        post_conversion_updater: PostConversionStateUpdater,
    ):
        self.conversion_engine = conversion_engine
        self.learning_service = learning_service
        self.post_conversion_updater = post_conversion_updater

    def execute(
        self,
        *,
        context: "StateContext",
        selection_valid_for_convert: bool,
        saved_events: list,
        saved_count: int,
        pending_manual_learning: "PendingManualLearning | None",
    ) -> ManualConversionResult:
        success = self.conversion_engine.convert(
            context,
            selection_valid=selection_valid_for_convert,
        )

        if success and self.learning_service.user_dict is not None:
            if pending_manual_learning is not None:
                self.learning_service.record_manual_conversion(
                    pending_manual_learning.word,
                    pending_manual_learning.lang,
                    pending_manual_learning.is_selection_conversion,
                )
            elif saved_count == 0:
                self.learning_service.record_selection_conversion(
                    getattr(self.conversion_engine, "last_conversion", None)
                )

        sticky_events = self.post_conversion_updater.update(
            success=success,
            saved_count=saved_count,
            saved_events=saved_events,
            selection_valid_for_convert=selection_valid_for_convert,
        )
        return ManualConversionResult(
            success=success,
            sticky_events=sticky_events,
        )
