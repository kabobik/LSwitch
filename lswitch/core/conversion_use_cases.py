"""Application-level conversion use cases."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from lswitch.core.auto_marker import AutoConversionMarker
from lswitch.core.decision_trace import (
    DecisionAttempt,
    DecisionOutcome,
    DecisionTrace,
    DecisionTraceStep,
    ExecutionOutcome,
    StepState,
    TraceFact,
    TraceTrigger,
)
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


def _trace_step(
    rule_id: str,
    state: StepState,
    *,
    decisive: bool = False,
    **facts,
) -> DecisionTraceStep:
    return DecisionTraceStep(
        rule_id=rule_id,
        state=state,
        decisive=decisive,
        facts=tuple(
            TraceFact(
                key=key,
                value=(
                    value
                    if isinstance(
                        value,
                        (str, int, float, bool, type(None)),
                    )
                    else str(value)
                ),
            )
            for key, value in facts.items()
        ),
    )


def _record_trace_safely(recorder, trace: DecisionTrace) -> None:
    if recorder is None:
        return
    try:
        recorder.record(trace)
    except Exception:
        logger.exception("Could not record conversion decision trace")


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
    original_text: str = ""


@dataclass(frozen=True)
class RecentAutoConversionResult:
    handled: bool


@dataclass(frozen=True)
class SpaceAutoConversionResult:
    space_consumed: bool
    pending_space: bool = False
    marker: AutoConversionMarker | None = None
    marker_changed: bool = False
    execution_succeeded: bool | None = None
    execution_steps: tuple[DecisionTraceStep, ...] = ()
    duration_ms: float = 0.0


@dataclass(frozen=True)
class MidWordAutoConversionResult:
    switched: bool
    marker: AutoConversionMarker | None = None
    marker_changed: bool = False
    reason: str = ""
    execution_succeeded: bool | None = None
    execution_steps: tuple[DecisionTraceStep, ...] = ()
    duration_ms: float = 0.0


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
        layout_switch_controller=None,
        trace_recorder=None,
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
        self.layout_switch_controller = layout_switch_controller
        self.trace_recorder = trace_recorder

    def execute(self, marker: AutoConversionMarker) -> bool:
        started = time.perf_counter()
        execution_steps: list[DecisionTraceStep] = []
        try:
            self.learning_service.record_auto_undo_correction(marker)
            execution_steps.append(
                _trace_step(
                    "execution.learning",
                    StepState.SUCCEEDED,
                    correction=True,
                )
            )
        except Exception as exc:
            execution_steps.append(
                _trace_step(
                    "execution.learning",
                    StepState.FAILED,
                    decisive=True,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
            )
            self._record_undo_trace(
                marker,
                success=False,
                execution_steps=tuple(execution_steps),
                duration_ms=(time.perf_counter() - started) * 1000.0,
            )
            raise

        operation = (
            self.layout_switch_controller.begin_operation()
            if self.layout_switch_controller is not None
            else None
        )

        try:
            self.virtual_kb.tap_key(
                KEY_BACKSPACE,
                n_times=marker.converted_len + (1 if marker.had_space else 0),
            )
            execution_steps.append(
                _trace_step(
                    "execution.delete",
                    StepState.SUCCEEDED,
                    delete_count=(
                        marker.converted_len
                        + (1 if marker.had_space else 0)
                    ),
                )
            )
            target = self.layout_service.find_available_layout_for_lang(
                marker.original_lang
            )
            execution_steps.append(
                _trace_step(
                    "execution.target_layout",
                    (
                        StepState.SUCCEEDED
                        if target is not None
                        else StepState.NOT_MATCHED
                    ),
                    target_lang=marker.original_lang,
                    target_layout=getattr(target, "name", None),
                )
            )
            if target is not None:
                if operation is not None:
                    operation.switch_to(target)
                else:
                    self.xkb.switch_layout(target=target)
                execution_steps.append(
                    _trace_step(
                        "execution.layout_switch",
                        StepState.SUCCEEDED,
                        target_layout=getattr(target, "name", None),
                    )
                )
            time.sleep(self.timing.get("undo_before_replay_delay", 0.03))
            self.virtual_kb.replay_events(marker.word_events)
            execution_steps.append(
                _trace_step(
                    "execution.replay",
                    StepState.SUCCEEDED,
                    event_count=len(marker.word_events),
                )
            )
            if marker.had_space:
                self.virtual_kb.tap_key(KEY_SPACE)
                execution_steps.append(
                    _trace_step(
                        "execution.space",
                        StepState.SUCCEEDED,
                    )
                )
            if operation is not None:
                operation.finish(success=True)
                execution_steps.append(
                    _trace_step(
                        "execution.layout_policy",
                        StepState.SUCCEEDED,
                        keep_target=operation.keep_target_after_conversion,
                    )
                )
            execution_steps.append(
                _trace_step(
                    "execution.success",
                    StepState.SUCCEEDED,
                    decisive=True,
                )
            )
            self._record_undo_trace(
                marker,
                success=True,
                execution_steps=tuple(execution_steps),
                duration_ms=(time.perf_counter() - started) * 1000.0,
            )
            return True
        except Exception as exc:
            logger.error("Undo auto-conversion failed: %s", exc)
            if operation is not None:
                operation.finish(success=False)
            execution_steps.append(
                _trace_step(
                    "execution.error",
                    StepState.FAILED,
                    decisive=True,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
            )
            self._record_undo_trace(
                marker,
                success=False,
                execution_steps=tuple(execution_steps),
                duration_ms=(time.perf_counter() - started) * 1000.0,
            )
            return False

    def _record_undo_trace(
        self,
        marker: AutoConversionMarker,
        *,
        success: bool,
        execution_steps: tuple[DecisionTraceStep, ...],
        duration_ms: float,
    ) -> None:
        if not (
            self.trace_recorder is not None
            and self.trace_recorder.enabled
        ):
            return
        try:
            from lswitch.intelligence.auto_detector import AutoDetector

            current_text, source_lang = AutoDetector._converted_word(
                marker.original_word.lower(),
                marker.original_lang,
            )
        except Exception:
            current_text = None
            source_lang = marker.target_lang
        current_text = current_text or marker.original_word
        attempt = DecisionAttempt(
            candidate=current_text,
            converted_candidate=marker.original_word,
            source_lang=source_lang or marker.target_lang,
            target_lang=marker.original_lang,
            outcome=DecisionOutcome.CONVERT,
            steps=(
                _trace_step(
                    "undo.recent_auto_marker",
                    StepState.MATCHED,
                    decisive=True,
                    marker_kind=marker.kind,
                    had_space=marker.had_space,
                ),
            ),
        )
        _record_trace_safely(
            self.trace_recorder,
            DecisionTrace(
                correlation_id=-time.monotonic_ns(),
                trigger=TraceTrigger.UNDO,
                original=current_text,
                converted=marker.original_word,
                source_lang=source_lang or marker.target_lang,
                target_lang=marker.original_lang,
                decision=DecisionOutcome.CONVERT,
                execution=(
                    ExecutionOutcome.SUCCEEDED
                    if success
                    else ExecutionOutcome.FAILED
                ),
                conversion_mode="undo",
                attempts=(attempt,),
                execution_steps=execution_steps,
                duration_ms=duration_ms,
            ),
        )


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

        original_text = self.decode_events(saved_events)
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
            original_text,
        )

        return ManualConversionPreparation(
            selection_valid_for_convert=selection_valid_for_convert,
            saved_events=saved_events,
            saved_count=saved_count,
            pending_manual_learning=pending_manual_learning,
            original_text=original_text,
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
        trace_recorder=None,
    ):
        self.conversion_engine = conversion_engine
        self.learning_service = learning_service
        self.post_conversion_updater = post_conversion_updater
        self.trace_recorder = trace_recorder

    def execute(
        self,
        *,
        context: "StateContext",
        selection_valid_for_convert: bool,
        saved_events: list,
        saved_count: int,
        pending_manual_learning: "PendingManualLearning | None",
        original_text: str = "",
    ) -> ManualConversionResult:
        started = time.perf_counter()
        success: bool | None = None
        learning_recorded = False
        try:
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
                    learning_recorded = True
                elif saved_count == 0:
                    self.learning_service.record_selection_conversion(
                        getattr(self.conversion_engine, "last_conversion", None)
                    )
                    learning_recorded = True

            sticky_events = self.post_conversion_updater.update(
                success=success,
                saved_count=saved_count,
                saved_events=saved_events,
                selection_valid_for_convert=selection_valid_for_convert,
            )
        except Exception as exc:
            self._record_manual_trace(
                original_text=original_text,
                pending_manual_learning=pending_manual_learning,
                success=success,
                duration_ms=(time.perf_counter() - started) * 1000.0,
                learning_recorded=learning_recorded,
                error=exc,
            )
            raise

        self._record_manual_trace(
            original_text=original_text,
            pending_manual_learning=pending_manual_learning,
            success=success,
            duration_ms=(time.perf_counter() - started) * 1000.0,
            learning_recorded=learning_recorded,
        )
        return ManualConversionResult(
            success=bool(success),
            sticky_events=sticky_events,
        )

    def _record_manual_trace(
        self,
        *,
        original_text: str,
        pending_manual_learning: "PendingManualLearning | None",
        success: bool | None,
        duration_ms: float,
        learning_recorded: bool,
        error: Exception | None = None,
    ) -> None:
        if not (
            self.trace_recorder is not None
            and self.trace_recorder.enabled
        ):
            return

        from lswitch.core.conversion_engine import ConversionModeDecision

        mode_decision = getattr(
            self.conversion_engine,
            "last_mode_decision",
            None,
        )
        if isinstance(mode_decision, ConversionModeDecision):
            mode = mode_decision.mode
            decision_steps = mode_decision.steps
        else:
            mode = "unknown"
            decision_steps = (
                _trace_step(
                    "manual.mode.unknown",
                    StepState.SKIPPED,
                    decisive=True,
                ),
            )

        last_conversion = getattr(
            self.conversion_engine,
            "last_conversion",
            None,
        )
        if not isinstance(last_conversion, dict):
            last_conversion = {}
        original = (
            last_conversion.get("original")
            or (
                pending_manual_learning.word
                if pending_manual_learning is not None
                else original_text
            )
            or ""
        )
        converted = last_conversion.get("converted") or None
        if converted is None and original and success:
            try:
                from lswitch.core.text_converter import invert_layout_runs

                converted = "".join(
                    text
                    for text, _lang in invert_layout_runs(original)
                )
            except Exception:
                converted = None

        source_lang = (
            pending_manual_learning.lang
            if pending_manual_learning is not None
            else None
        )
        target_lang = last_conversion.get("target_lang")
        if target_lang is None and source_lang in ("en", "ru"):
            target_lang = "ru" if source_lang == "en" else "en"

        execution_steps = list(
            getattr(
                self.conversion_engine,
                "last_execution_steps",
                (),
            )
            or ()
        )
        if learning_recorded:
            execution_steps.append(
                _trace_step(
                    "execution.learning",
                    StepState.SUCCEEDED,
                )
            )
        if error is not None:
            execution_steps.append(
                _trace_step(
                    "execution.error",
                    StepState.FAILED,
                    decisive=True,
                    error_type=type(error).__name__,
                    error=str(error),
                )
            )

        decision_outcome = (
            DecisionOutcome.SKIP
            if not original and not success
            else DecisionOutcome.CONVERT
        )
        attempt = DecisionAttempt(
            candidate=original,
            converted_candidate=converted,
            source_lang=source_lang,
            target_lang=target_lang,
            outcome=decision_outcome,
            steps=decision_steps,
        )
        _record_trace_safely(
            self.trace_recorder,
            DecisionTrace(
                correlation_id=-time.monotonic_ns(),
                trigger=TraceTrigger.MANUAL,
                original=original,
                converted=converted,
                source_lang=source_lang,
                target_lang=target_lang,
                decision=decision_outcome,
                execution=(
                    ExecutionOutcome.SUCCEEDED
                    if success and error is None
                    else ExecutionOutcome.FAILED
                ),
                conversion_mode=mode,
                attempts=(attempt,),
                execution_steps=tuple(execution_steps),
                duration_ms=duration_ms,
                truncated=attempt.truncated,
            ),
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
        trace_recorder=None,
    ):
        self.auto_detector = auto_detector
        self.typed_buffer = typed_buffer
        self.xkb = xkb
        self.retype_service = retype_service
        self.learning_service = learning_service
        self.layout_service = LayoutService(xkb)
        self.timing = timing or {}
        self.debug = debug
        self.trace_recorder = trace_recorder
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
        correlation_id: int = 0,
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
            self._record_gate(
                correlation_id=correlation_id,
                original=self._buffer_text(context),
                outcome=DecisionOutcome.SKIP,
                rule_id="auto.buffer_threshold",
                state=StepState.NOT_MATCHED,
                facts={
                    "chars_in_buffer": context.chars_in_buffer,
                    "threshold": threshold,
                },
            )
            return SpaceAutoConversionResult(space_consumed=False)

        try:
            current_layout_info = self.xkb.get_current_layout() if self.xkb else None
        except Exception as exc:
            self._record_gate(
                correlation_id=correlation_id,
                original=self._buffer_text(context),
                outcome=DecisionOutcome.ERROR,
                rule_id="execution.current_layout",
                state=StepState.FAILED,
                facts={
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
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
            self._record_gate(
                correlation_id=correlation_id,
                original=candidate.text or "",
                outcome=DecisionOutcome.SKIP,
                rule_id="candidate.min_length",
                state=StepState.NOT_MATCHED,
                facts={
                    "length": len(candidate.text) if candidate.text else 0,
                    "minimum": self.min_word_len,
                },
                source_lang=candidate.current_lang,
            )
            return SpaceAutoConversionResult(space_consumed=False)

        evaluation_started = time.perf_counter()
        try:
            should, reason, attempt = self._evaluate_candidate(
                candidate.text,
                candidate.current_lang,
            )
        except Exception as exc:
            logger.warning("AutoDetector error: %s", exc)
            duration_ms = (time.perf_counter() - evaluation_started) * 1000.0
            attempt = DecisionAttempt(
                candidate=candidate.text,
                outcome=DecisionOutcome.ERROR,
                source_lang=candidate.current_lang,
                steps=(
                    _trace_step(
                        "auto.detector.error",
                        StepState.FAILED,
                        decisive=True,
                        error_type=type(exc).__name__,
                        error=str(exc),
                    ),
                ),
                duration_ms=duration_ms,
            )
            self._record_attempt(
                correlation_id=correlation_id,
                attempt=attempt,
            )
            return SpaceAutoConversionResult(space_consumed=False)

        duration_ms = (time.perf_counter() - evaluation_started) * 1000.0
        attempt = DecisionAttempt(
            candidate=attempt.candidate,
            converted_candidate=attempt.converted_candidate,
            source_lang=attempt.source_lang,
            target_lang=attempt.target_lang,
            outcome=attempt.outcome,
            steps=attempt.steps,
            duration_ms=duration_ms,
            truncated=attempt.truncated,
        )

        marker_changed = False
        if last_auto_marker is not None:
            old = AutoConversionMarker.from_legacy(last_auto_marker)
            if auto_confirm_enabled:
                self.learning_service.record_auto_confirmation(old)
            marker_changed = True

        if not should:
            self._record_attempt(
                correlation_id=correlation_id,
                attempt=attempt,
            )
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
        execution = (
            ExecutionOutcome.SUCCEEDED
            if result.execution_succeeded
            else ExecutionOutcome.FAILED
        )
        self._record_attempt(
            correlation_id=correlation_id,
            attempt=attempt,
            execution=execution,
            execution_steps=result.execution_steps,
            duration_ms=result.duration_ms,
            conversion_mode="retype",
        )
        return SpaceAutoConversionResult(
            space_consumed=True,
            pending_space=result.pending_space,
            marker=result.marker,
            marker_changed=True,
            execution_succeeded=result.execution_succeeded,
            execution_steps=result.execution_steps,
            duration_ms=result.duration_ms,
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
        execution_steps: list[DecisionTraceStep] = []
        started = time.perf_counter()

        try:
            target_lang = "ru" if direction == "en_to_ru" else "en"
            target = self.layout_service.find_available_layout_for_lang(target_lang)
            execution_steps.append(
                _trace_step(
                    "execution.target_layout",
                    (
                        StepState.SUCCEEDED
                        if target is not None
                        else StepState.NOT_MATCHED
                    ),
                    target_lang=target_lang,
                    target_layout=getattr(target, "name", None),
                )
            )
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
            retype_steps = getattr(
                self.retype_service,
                "last_trace_steps",
                (),
            )
            retype_step_sequence = (
                tuple(retype_steps)
                if isinstance(retype_steps, (tuple, list))
                else ()
            )
            execution_steps.extend(retype_step_sequence)
            if not retype_step_sequence:
                execution_steps.append(
                    _trace_step(
                        "execution.retype",
                        (
                            StepState.SUCCEEDED
                            if conversion_ok
                            else StepState.FAILED
                        ),
                        decisive=not conversion_ok,
                        event_count=len(word_events),
                        delete_count=word_len + 1,
                    )
                )

            if conversion_ok:
                time.sleep(self.timing.get("auto_before_space_delay", 0.01))
        except Exception as exc:
            logger.error("Auto-conversion at space failed: %s", exc)
            retype_steps = getattr(
                self.retype_service,
                "last_trace_steps",
                (),
            )
            if isinstance(retype_steps, (tuple, list)):
                for step in tuple(retype_steps):
                    if step not in execution_steps:
                        execution_steps.append(step)
            execution_steps.append(
                _trace_step(
                    "execution.error",
                    StepState.FAILED,
                    decisive=True,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
            )
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
            execution_succeeded=conversion_ok,
            execution_steps=tuple(execution_steps),
            duration_ms=(time.perf_counter() - started) * 1000.0,
        )

    def _evaluate_candidate(
        self,
        word: str,
        current_lang: str,
    ) -> tuple[bool, str, DecisionAttempt]:
        from lswitch.intelligence.auto_detector import AutoDecision

        evaluate = getattr(self.auto_detector, "evaluate", None)
        decision = evaluate(word, current_lang) if callable(evaluate) else None
        if isinstance(decision, AutoDecision):
            return (
                decision.should_convert,
                decision.reason,
                DecisionAttempt(
                    candidate=decision.original,
                    converted_candidate=decision.converted,
                    source_lang=decision.source_lang,
                    target_lang=decision.target_lang,
                    outcome=decision.outcome,
                    steps=decision.steps,
                ),
            )

        should, reason = self.auto_detector.should_convert(word, current_lang)
        from lswitch.intelligence.auto_detector import AutoDetector

        converted, target_lang = AutoDetector._converted_word(
            word.lower(),
            current_lang,
        )
        outcome = (
            DecisionOutcome.CONVERT if should else DecisionOutcome.KEEP
        )
        return (
            bool(should),
            reason,
            DecisionAttempt(
                candidate=word,
                converted_candidate=converted,
                source_lang=current_lang,
                target_lang=target_lang,
                outcome=outcome,
                steps=(
                    _trace_step(
                        "auto.legacy_decision",
                        StepState.MATCHED,
                        decisive=True,
                        reason=reason,
                    ),
                ),
            ),
        )

    def _record_gate(
        self,
        *,
        correlation_id: int,
        original: str,
        outcome: DecisionOutcome,
        rule_id: str,
        state: StepState,
        facts: dict,
        source_lang: str | None = None,
    ) -> None:
        if not self._tracing_enabled():
            return
        self._record_attempt(
            correlation_id=correlation_id,
            attempt=DecisionAttempt(
                candidate=original,
                source_lang=source_lang,
                outcome=outcome,
                steps=(
                    _trace_step(
                        rule_id,
                        state,
                        decisive=True,
                        **facts,
                    ),
                ),
            ),
        )

    def _record_attempt(
        self,
        *,
        correlation_id: int,
        attempt: DecisionAttempt,
        execution: ExecutionOutcome = ExecutionOutcome.NOT_STARTED,
        execution_steps: tuple[DecisionTraceStep, ...] = (),
        duration_ms: float = 0.0,
        conversion_mode: str | None = None,
    ) -> None:
        if not self._tracing_enabled():
            return
        _record_trace_safely(
            self.trace_recorder,
            DecisionTrace(
                correlation_id=correlation_id,
                trigger=TraceTrigger.SPACE_AUTO,
                original=attempt.candidate,
                converted=attempt.converted_candidate,
                source_lang=attempt.source_lang,
                target_lang=attempt.target_lang,
                decision=attempt.outcome,
                execution=execution,
                conversion_mode=conversion_mode,
                attempts=(attempt,),
                execution_steps=execution_steps,
                duration_ms=attempt.duration_ms + duration_ms,
                truncated=attempt.truncated,
            ),
        )

    def _tracing_enabled(self) -> bool:
        return bool(
            self.trace_recorder is not None
            and self.trace_recorder.enabled
        )

    def _buffer_text(self, context: "StateContext") -> str:
        try:
            return self.typed_buffer.decode(context.event_buffer)
        except Exception:
            return ""


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
        trace_recorder=None,
    ):
        self.mid_word_detector = mid_word_detector
        self.typed_buffer = typed_buffer
        self.xkb = xkb
        self.retype_service = retype_service
        self.layout_service = LayoutService(xkb)
        self.timing = timing or {}
        self.debug = debug
        self.trace_recorder = trace_recorder
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
        correlation_id: int = 0,
    ) -> MidWordAutoConversionResult:
        if self.mid_word_detector is None:
            return MidWordAutoConversionResult(switched=False)

        if context.chars_in_buffer == 0:
            return MidWordAutoConversionResult(switched=False)

        try:
            current_layout_info = self.xkb.get_current_layout() if self.xkb else None
        except Exception as exc:
            self._record_mid_attempt(
                correlation_id,
                DecisionAttempt(
                    candidate="",
                    outcome=DecisionOutcome.ERROR,
                    steps=(
                        _trace_step(
                            "execution.current_layout",
                            StepState.FAILED,
                            decisive=True,
                            error_type=type(exc).__name__,
                            error=str(exc),
                        ),
                    ),
                ),
            )
            return MidWordAutoConversionResult(switched=False)

        candidate = self.candidate_provider.candidate_for_context(
            context=context,
            current_layout_info=current_layout_info,
        )
        if not candidate.text:
            self._record_mid_attempt(
                correlation_id,
                DecisionAttempt(
                    candidate="",
                    source_lang=candidate.current_lang,
                    outcome=DecisionOutcome.SKIP,
                    steps=(
                        _trace_step(
                            "candidate.empty",
                            StepState.MATCHED,
                            decisive=True,
                        ),
                    ),
                ),
            )
            return MidWordAutoConversionResult(switched=False, reason="empty candidate")

        evaluation_started = time.perf_counter()
        try:
            decision = self.mid_word_detector.should_switch(
                candidate.text,
                candidate.current_lang,
            )
        except Exception as exc:
            attempt = DecisionAttempt(
                candidate=candidate.text,
                source_lang=candidate.current_lang,
                outcome=DecisionOutcome.ERROR,
                steps=(
                    _trace_step(
                        "midword.detector.error",
                        StepState.FAILED,
                        decisive=True,
                        error_type=type(exc).__name__,
                        error=str(exc),
                    ),
                ),
                duration_ms=(
                    time.perf_counter() - evaluation_started
                ) * 1000.0,
            )
            self._record_mid_attempt(correlation_id, attempt)
            raise

        decision_steps = tuple(getattr(decision, "steps", ()) or ())
        if not decision_steps:
            decision_steps = (
                _trace_step(
                    "midword.legacy_decision",
                    StepState.MATCHED,
                    decisive=True,
                    reason=decision.reason,
                ),
            )
        outcome = getattr(decision, "outcome", None)
        if not isinstance(outcome, DecisionOutcome):
            outcome = (
                DecisionOutcome.CONVERT
                if decision.should_switch
                else DecisionOutcome.KEEP
            )
        attempt = DecisionAttempt(
            candidate=candidate.text,
            converted_candidate=(
                getattr(decision, "converted_prefix", "") or None
            ),
            source_lang=candidate.current_lang,
            target_lang=getattr(decision, "target_lang", None),
            outcome=outcome,
            steps=decision_steps,
            duration_ms=(
                time.perf_counter() - evaluation_started
            ) * 1000.0,
        )
        self._record_mid_attempt(correlation_id, attempt)
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
        execution_started = time.perf_counter()
        execution_steps: list[DecisionTraceStep] = []
        try:
            target = self.layout_service.find_available_layout_for_lang(
                decision.target_lang
            )
            execution_steps.append(
                _trace_step(
                    "execution.target_layout",
                    (
                        StepState.SUCCEEDED
                        if target is not None
                        else StepState.NOT_MATCHED
                    ),
                    target_lang=decision.target_lang,
                    target_layout=getattr(target, "name", None),
                )
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
            retype_steps = getattr(
                self.retype_service,
                "last_trace_steps",
                (),
            )
            retype_step_sequence = (
                tuple(retype_steps)
                if isinstance(retype_steps, (tuple, list))
                else ()
            )
            execution_steps.extend(retype_step_sequence)
            if not retype_step_sequence:
                execution_steps.append(
                    _trace_step(
                        "execution.retype",
                        (
                            StepState.SUCCEEDED
                            if conversion_ok
                            else StepState.FAILED
                        ),
                        decisive=not conversion_ok,
                        event_count=len(candidate.events),
                    )
                )
        except Exception as exc:
            execution_steps.append(
                _trace_step(
                    "execution.error",
                    StepState.FAILED,
                    decisive=True,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
            )
            self._finalize_mid_trace(
                correlation_id,
                attempt,
                execution=ExecutionOutcome.FAILED,
                execution_steps=tuple(execution_steps),
                duration_ms=(
                    time.perf_counter() - execution_started
                ) * 1000.0,
            )
            raise
        if not conversion_ok:
            execution_duration_ms = (
                time.perf_counter() - execution_started
            ) * 1000.0
            self._finalize_mid_trace(
                correlation_id,
                attempt,
                execution=ExecutionOutcome.FAILED,
                execution_steps=tuple(execution_steps),
                duration_ms=execution_duration_ms,
            )
            return MidWordAutoConversionResult(
                switched=False,
                reason="retype failed",
                execution_succeeded=False,
                execution_steps=tuple(execution_steps),
                duration_ms=execution_duration_ms,
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
        execution_duration_ms = (
            time.perf_counter() - execution_started
        ) * 1000.0
        self._finalize_mid_trace(
            correlation_id,
            attempt,
            execution=ExecutionOutcome.SUCCEEDED,
            execution_steps=tuple(execution_steps),
            duration_ms=execution_duration_ms,
        )
        return MidWordAutoConversionResult(
            switched=True,
            marker=marker,
            marker_changed=True,
            reason=decision.reason,
            execution_succeeded=True,
            execution_steps=tuple(execution_steps),
            duration_ms=execution_duration_ms,
        )

    def _record_mid_attempt(
        self,
        correlation_id: int,
        attempt: DecisionAttempt,
    ) -> None:
        if not self._tracing_enabled():
            return
        try:
            self.trace_recorder.upsert_attempt(
                correlation_id,
                TraceTrigger.MID_WORD,
                attempt,
            )
        except Exception:
            logger.exception("Could not record mid-word decision trace")

    def _finalize_mid_trace(
        self,
        correlation_id: int,
        attempt: DecisionAttempt,
        *,
        execution: ExecutionOutcome,
        execution_steps: tuple[DecisionTraceStep, ...],
        duration_ms: float,
    ) -> None:
        if not self._tracing_enabled():
            return
        try:
            self.trace_recorder.finalize_session(
                correlation_id,
                TraceTrigger.MID_WORD,
                decision=attempt.outcome,
                execution=execution,
                converted=attempt.converted_candidate,
                conversion_mode="retype",
                execution_steps=execution_steps,
                duration_ms=duration_ms,
            )
        except Exception:
            logger.exception("Could not finalize mid-word decision trace")

    def _tracing_enabled(self) -> bool:
        return bool(
            self.trace_recorder is not None
            and self.trace_recorder.enabled
        )
