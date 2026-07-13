"""Manual conversion orchestration controller."""

from __future__ import annotations

from dataclasses import dataclass

from lswitch.core.conversion_use_cases import (
    ManualConversionPreparer,
    ManualConversionUseCase,
    PostConversionStateUpdater,
    RecentAutoConversionUseCase,
    UndoAutoConversionUseCase,
)
from lswitch.core.layout_service import LayoutService
from lswitch.core.states import State


@dataclass(frozen=True)
class ManualConversionControllerResult:
    last_auto_marker: object | None
    sticky_events: list


class ManualConversionController:
    """Coordinate manual conversion, recent auto undo, learning, and final state."""

    def __init__(
        self,
        *,
        state_manager,
        selection_tracker,
        typed_buffer,
        learning_service,
        conversion_engine,
        virtual_kb,
        xkb,
        selection,
        timing: dict,
        debug: bool,
        decode_events,
        extract_last_word,
        update_selection_baseline,
        layout_switch_controller=None,
        trace_recorder=None,
    ):
        self.state_manager = state_manager
        self.selection_tracker = selection_tracker
        self.typed_buffer = typed_buffer
        self.learning_service = learning_service
        self.conversion_engine = conversion_engine
        self.virtual_kb = virtual_kb
        self.xkb = xkb
        self.selection = selection
        self.timing = timing
        self.debug = debug
        self.decode_events = decode_events
        self.extract_last_word = extract_last_word
        self.update_selection_baseline = update_selection_baseline
        self.layout_switch_controller = layout_switch_controller
        self.trace_recorder = trace_recorder

    def execute(
        self,
        *,
        last_auto_marker,
        sticky_events: list,
    ) -> ManualConversionControllerResult:
        if self.state_manager.state != State.CONVERTING:
            return ManualConversionControllerResult(
                last_auto_marker=last_auto_marker,
                sticky_events=sticky_events,
            )

        selection_valid_for_convert = self.selection_tracker.effective_valid()
        chars_in_buffer = self.state_manager.context.chars_in_buffer
        had_auto_marker = last_auto_marker is not None

        if last_auto_marker is not None:
            recent_auto = RecentAutoConversionUseCase(
                undo_use_case=UndoAutoConversionUseCase(
                    virtual_kb=self.virtual_kb,
                    xkb=self.xkb,
                    learning_service=self.learning_service,
                    timing=self.timing,
                    debug=self.debug,
                    layout_switch_controller=self.layout_switch_controller,
                    trace_recorder=self.trace_recorder,
                )
            )
            result = recent_auto.execute(
                marker=last_auto_marker,
                chars_in_buffer=chars_in_buffer,
            )
            last_auto_marker = None
            if result.handled:
                self.state_manager.on_conversion_complete()
                return ManualConversionControllerResult(
                    last_auto_marker=None,
                    sticky_events=sticky_events,
                )

        try:
            preparation = ManualConversionPreparer(
                typed_buffer=self.typed_buffer,
                learning_service=self.learning_service,
                layout_service=LayoutService(self.xkb),
                selection=self.selection,
                xkb=self.xkb,
                decode_events=self.decode_events,
            ).prepare(
                context=self.state_manager.context,
                selection_valid_for_convert=selection_valid_for_convert,
                raw_selection_valid=self.selection_tracker.valid,
                raw_selection_repeat_valid=self.selection_tracker.repeat_valid,
                has_auto_marker=had_auto_marker,
                sticky_events=sticky_events,
                extract_last_word=self.extract_last_word,
            )

            manual_conversion = ManualConversionUseCase(
                conversion_engine=self.conversion_engine,
                learning_service=self.learning_service,
                post_conversion_updater=PostConversionStateUpdater(
                    self.selection_tracker
                ),
                trace_recorder=self.trace_recorder,
            )
            result = manual_conversion.execute(
                context=self.state_manager.context,
                selection_valid_for_convert=(
                    preparation.selection_valid_for_convert
                ),
                saved_events=preparation.saved_events,
                saved_count=preparation.saved_count,
                pending_manual_learning=preparation.pending_manual_learning,
                original_text=preparation.original_text,
            )
            sticky_events = result.sticky_events
        finally:
            self.update_selection_baseline()
            self.selection_tracker.set_valid(False)
            self.state_manager.on_conversion_complete()

        return ManualConversionControllerResult(
            last_auto_marker=last_auto_marker,
            sticky_events=sticky_events,
        )
