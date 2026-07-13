"""Application-level conversion use cases."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from lswitch.core.auto_marker import AutoConversionMarker
from lswitch.core.layout_service import LayoutService

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


@dataclass(frozen=True)
class ManualConversionPreparation:
    selection_valid_for_convert: bool
    saved_events: list
    saved_count: int
    pending_manual_learning: "PendingManualLearning | None"


@dataclass(frozen=True)
class RecentAutoConversionResult:
    handled: bool


@dataclass(frozen=True)
class SpaceAutoConversionResult:
    space_consumed: bool
    pending_space: bool = False
    marker: AutoConversionMarker | None = None
    marker_changed: bool = False


@dataclass(frozen=True)
class MidWordAutoConversionResult:
    switched: bool
    marker: AutoConversionMarker | None = None
    marker_changed: bool = False
    reason: str = ""


@dataclass(frozen=True)
class AutoConversionCandidate:
    text: str
    events: list
    current_lang: str


class SpaceAutoConversionCandidateProvider:
    """Extract the current word-boundary candidate for auto-conversion."""

    def __init__(self, *, typed_buffer, xkb: "IXKBAdapter", layout_service):
        self.typed_buffer = typed_buffer
        self.xkb = xkb
        self.layout_service = layout_service

    def candidate_for_context(
        self,
        *,
        context: "StateContext",
        current_layout_info,
    ) -> AutoConversionCandidate:
        current_lang = self.layout_service.layout_to_lang(current_layout_info)
        token = self.typed_buffer.last_word(
            context,
            current_layout=current_layout_info,
            xkb=self.xkb,
        )
        return AutoConversionCandidate(
            text=token.text,
            events=token.events,
            current_lang=current_lang,
        )


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
        self.layout_service = LayoutService(xkb)
        self.timing = timing or {}
        self.debug = debug

    def execute(self, marker: AutoConversionMarker) -> bool:
        self.learning_service.record_auto_undo_correction(marker)

        try:
            self.virtual_kb.tap_key(
                KEY_BACKSPACE,
                n_times=marker.converted_len + (1 if marker.had_space else 0),
            )
            target = self.layout_service.find_available_layout_for_lang(
                marker.original_lang
            )
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


class RecentAutoConversionUseCase:
    """Handle a recent auto-conversion before manual conversion proceeds."""

    def __init__(self, *, undo_use_case: UndoAutoConversionUseCase):
        self.undo_use_case = undo_use_case

    def execute(
        self,
        *,
        marker: AutoConversionMarker | dict,
        chars_in_buffer: int,
    ) -> RecentAutoConversionResult:
        auto_marker = AutoConversionMarker.from_legacy(marker)
        if chars_in_buffer == 0:
            self.undo_use_case.execute(auto_marker)
            return RecentAutoConversionResult(handled=True)
        return RecentAutoConversionResult(handled=False)


class ManualConversionPreparer:
    """Prepare learning and typed-buffer state for manual conversion."""

    def __init__(
        self,
        *,
        typed_buffer,
        learning_service: "LearningService",
        layout_service: LayoutService,
        selection,
        xkb: "IXKBAdapter",
        decode_events,
    ):
        self.typed_buffer = typed_buffer
        self.learning_service = learning_service
        self.layout_service = layout_service
        self.selection = selection
        self.xkb = xkb
        self.decode_events = decode_events

    def prepare(
        self,
        *,
        context: "StateContext",
        selection_valid_for_convert: bool,
        raw_selection_valid: bool,
        raw_selection_repeat_valid: bool,
        has_auto_marker: bool,
        sticky_events: list,
        extract_last_word,
    ) -> ManualConversionPreparation:
        layout_info = self._current_layout()
        pending_manual_learning = (
            self.learning_service.prepare_pending_manual_learning(
                chars_in_buffer=context.chars_in_buffer,
                selection_valid=selection_valid_for_convert,
                has_auto_marker=has_auto_marker,
                layout_info=layout_info,
                extract_last_word=extract_last_word,
                selection=self.selection,
                layout_to_lang=self.layout_service.layout_to_lang,
            )
        )

        try:
            prepared_buffer = self.typed_buffer.prepare_retype_buffer(
                context,
                sticky_events=sticky_events,
                selection_valid=selection_valid_for_convert,
                current_layout=layout_info,
                xkb=self.xkb,
            )
        except Exception as exc:
            logger.debug("DoConversion: trim skipped: %s", exc)
            prepared_buffer = None

        if prepared_buffer is None:
            saved_events = list(context.event_buffer)
            saved_count = context.chars_in_buffer
        else:
            saved_events = prepared_buffer.events
            saved_count = prepared_buffer.count
            if prepared_buffer.restored_from_sticky:
                logger.debug(
                    "DoConversion: restored sticky buffer → chars=%d",
                    saved_count,
                )
            if prepared_buffer.trimmed_to_last_word:
                logger.debug(
                    "DoConversion: trim buffer to last word → %d events (was %d, trailing_spaces=%d)",
                    saved_count,
                    prepared_buffer.original_count,
                    prepared_buffer.trailing_space_count,
                )

        logger.debug(
            "DoConversion: selection_valid=%s, selection_repeat=%s, "
            "effective_selection=%s, chars_in_buffer=%d, "
            "saved_events=%d, sticky=%d, buffer=%r",
            raw_selection_valid,
            raw_selection_repeat_valid,
            selection_valid_for_convert,
            saved_count,
            len(saved_events),
            len(sticky_events),
            self.decode_events(saved_events),
        )

        return ManualConversionPreparation(
            selection_valid_for_convert=selection_valid_for_convert,
            saved_events=saved_events,
            saved_count=saved_count,
            pending_manual_learning=pending_manual_learning,
        )

    def _current_layout(self):
        try:
            return self.xkb.get_current_layout() if self.xkb else None
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


class SpaceAutoConversionUseCase:
    """Execute space-triggered auto conversion at a word boundary."""

    min_word_len = 1

    def __init__(
        self,
        *,
        auto_detector,
        typed_buffer,
        xkb: "IXKBAdapter",
        retype_service,
        learning_service: "LearningService",
        timing: dict | None = None,
        debug: bool = False,
        candidate_provider=None,
    ):
        self.auto_detector = auto_detector
        self.typed_buffer = typed_buffer
        self.xkb = xkb
        self.retype_service = retype_service
        self.learning_service = learning_service
        self.layout_service = LayoutService(xkb)
        self.timing = timing or {}
        self.debug = debug
        self.candidate_provider = candidate_provider
        if self.candidate_provider is None:
            self.candidate_provider = SpaceAutoConversionCandidateProvider(
                typed_buffer=typed_buffer,
                xkb=xkb,
                layout_service=self.layout_service,
            )

    def execute(
        self,
        *,
        context: "StateContext",
        threshold: int,
        last_auto_marker: AutoConversionMarker | dict | None,
        auto_confirm_enabled: bool,
    ) -> SpaceAutoConversionResult:
        if self.auto_detector is None:
            return SpaceAutoConversionResult(space_consumed=False)

        if context.chars_in_buffer == 0:
            return SpaceAutoConversionResult(space_consumed=False)

        if context.event_buffer and context.event_buffer[-1].code == KEY_SPACE:
            return SpaceAutoConversionResult(space_consumed=False)

        if context.chars_in_buffer < threshold:
            logger.debug(
                "Auto-conv skipped: buf=%d < threshold=%d",
                context.chars_in_buffer,
                threshold,
            )
            return SpaceAutoConversionResult(space_consumed=False)

        try:
            current_layout_info = self.xkb.get_current_layout() if self.xkb else None
        except Exception:
            return SpaceAutoConversionResult(space_consumed=False)

        candidate = self.candidate_provider.candidate_for_context(
            context=context,
            current_layout_info=current_layout_info,
        )

        logger.debug(
            "AutoConv: extracted word=%r (%d chars), lang=%s, buf=%d",
            candidate.text,
            len(candidate.text) if candidate.text else 0,
            candidate.current_lang,
            context.chars_in_buffer,
        )

        if not candidate.text or len(candidate.text) < self.min_word_len:
            logger.debug(
                "Auto-conv skipped: word %r too short (%d chars)",
                candidate.text,
                len(candidate.text) if candidate.text else 0,
            )
            return SpaceAutoConversionResult(space_consumed=False)

        try:
            should, reason = self.auto_detector.should_convert(
                candidate.text,
                candidate.current_lang,
            )
        except Exception as exc:
            logger.warning("AutoDetector error: %s", exc)
            return SpaceAutoConversionResult(space_consumed=False)

        marker_changed = False
        if last_auto_marker is not None:
            old = AutoConversionMarker.from_legacy(last_auto_marker)
            if auto_confirm_enabled:
                self.learning_service.record_auto_confirmation(old)
            marker_changed = True

        if not should:
            return SpaceAutoConversionResult(
                space_consumed=False,
                marker=None,
                marker_changed=marker_changed,
            )

        direction = "en_to_ru" if candidate.current_lang == "en" else "ru_to_en"
        logger.info(
            "Auto-convert at space: '%s' → %s (%s)",
            candidate.text,
            direction,
            reason,
        )
        result = self.perform_conversion(
            context=context,
            word_len=len(candidate.events),
            word_events=candidate.events,
            direction=direction,
            original_word=candidate.text,
            original_lang=candidate.current_lang,
        )
        return SpaceAutoConversionResult(
            space_consumed=True,
            pending_space=result.pending_space,
            marker=result.marker,
            marker_changed=True,
        )

    def perform_conversion(
        self,
        *,
        context: "StateContext",
        word_len: int,
        word_events: list,
        direction: str,
        original_word: str = "",
        original_lang: str = "",
    ) -> SpaceAutoConversionResult:
        from lswitch.core.states import State

        conversion_ok = False

        try:
            target_lang = "ru" if direction == "en_to_ru" else "en"
            target = self.layout_service.find_available_layout_for_lang(target_lang)
            conversion_ok = self.retype_service.retype_events(
                word_events,
                delete_count=word_len + 1,
                target_layout=target,
                before_replay_delay=self.timing.get(
                    "auto_before_replay_delay",
                    0.03,
                ),
                backspace_n_times_keyword=True,
            )

            if conversion_ok:
                time.sleep(self.timing.get("auto_before_space_delay", 0.01))
        except Exception as exc:
            logger.error("Auto-conversion at space failed: %s", exc)
        finally:
            context.reset()
            context.state = State.IDLE

        marker = None
        if original_word and conversion_ok:
            marker = AutoConversionMarker.for_space_conversion(
                original_word=original_word,
                original_lang=original_lang,
                direction=direction,
                word_events=word_events,
            )

        return SpaceAutoConversionResult(
            space_consumed=True,
            pending_space=True,
            marker=marker,
            marker_changed=marker is not None,
        )


class MidWordAutoConversionUseCase:
    """Execute mid-word auto-switch for an unfinished typed token."""

    def __init__(
        self,
        *,
        mid_word_detector,
        typed_buffer,
        xkb: "IXKBAdapter",
        retype_service,
        timing: dict | None = None,
        debug: bool = False,
        candidate_provider=None,
    ):
        self.mid_word_detector = mid_word_detector
        self.typed_buffer = typed_buffer
        self.xkb = xkb
        self.retype_service = retype_service
        self.layout_service = LayoutService(xkb)
        self.timing = timing or {}
        self.debug = debug
        self.candidate_provider = candidate_provider
        if self.candidate_provider is None:
            self.candidate_provider = SpaceAutoConversionCandidateProvider(
                typed_buffer=typed_buffer,
                xkb=xkb,
                layout_service=self.layout_service,
            )

    def execute(self, *, context: "StateContext") -> MidWordAutoConversionResult:
        if self.mid_word_detector is None:
            return MidWordAutoConversionResult(switched=False)

        if context.chars_in_buffer == 0:
            return MidWordAutoConversionResult(switched=False)

        try:
            current_layout_info = self.xkb.get_current_layout() if self.xkb else None
        except Exception:
            return MidWordAutoConversionResult(switched=False)

        candidate = self.candidate_provider.candidate_for_context(
            context=context,
            current_layout_info=current_layout_info,
        )
        if not candidate.text:
            return MidWordAutoConversionResult(switched=False, reason="empty candidate")

        decision = self.mid_word_detector.should_switch(
            candidate.text,
            candidate.current_lang,
        )
        if not decision.should_switch:
            return MidWordAutoConversionResult(
                switched=False,
                reason=decision.reason,
            )

        direction = "en_to_ru" if candidate.current_lang == "en" else "ru_to_en"
        logger.info(
            "Mid-word auto-convert: %r → %s (%s)",
            candidate.text,
            direction,
            decision.reason,
        )
        target = self.layout_service.find_available_layout_for_lang(
            decision.target_lang
        )
        conversion_ok = self.retype_service.retype_events(
            candidate.events,
            delete_count=len(candidate.events),
            target_layout=target,
            before_replay_delay=self.timing.get(
                "mid_word_before_replay_delay",
                self.timing.get("auto_before_replay_delay", 0.03),
            ),
            backspace_n_times_keyword=True,
        )
        if not conversion_ok:
            return MidWordAutoConversionResult(
                switched=False,
                reason="retype failed",
            )

        from lswitch.core.states import State

        context.reset()
        context.state = State.IDLE
        marker = AutoConversionMarker.for_mid_word_conversion(
            original_word=candidate.text,
            original_lang=candidate.current_lang,
            direction=direction,
            word_events=candidate.events,
        )
        return MidWordAutoConversionResult(
            switched=True,
            marker=marker,
            marker_changed=True,
            reason=decision.reason,
        )
