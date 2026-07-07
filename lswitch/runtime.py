"""Runtime component factories."""

from __future__ import annotations

from dataclasses import dataclass

from lswitch.core.event_bus import EventBus
from lswitch.core.input_router import InputEventRouter
from lswitch.core.learning_service import LearningService
from lswitch.core.selection_tracker import SelectionFreshnessTracker
from lswitch.core.state_manager import StateManager
from lswitch.core.typed_buffer import TypedBufferService


@dataclass(frozen=True)
class RuntimeCoreComponents:
    event_bus: EventBus
    state_manager: StateManager
    typed_buffer: TypedBufferService
    selection_tracker: SelectionFreshnessTracker
    learning_service: LearningService


def create_core_components(
    *,
    double_click_timeout: float,
    debug: bool,
    manual_weight_step: int,
) -> RuntimeCoreComponents:
    """Create core services that do not require platform adapters."""
    return RuntimeCoreComponents(
        event_bus=EventBus(),
        state_manager=StateManager(
            double_click_timeout=double_click_timeout,
            debug=debug,
        ),
        typed_buffer=TypedBufferService(),
        selection_tracker=SelectionFreshnessTracker(),
        learning_service=LearningService(
            None,
            debug=debug,
            manual_weight_step=manual_weight_step,
        ),
    )


def create_input_router(
    *,
    core: RuntimeCoreComponents,
    decode_buffer,
    auto_conversion_enabled,
    try_auto_conversion_at_space,
    get_pending_auto_space,
    set_pending_auto_space,
    clear_last_retype_events,
    clear_last_auto_marker,
    inject_deferred_space,
    request_conversion,
    prime_selection_baseline_on_click,
    read_mouse_release_selection,
) -> InputEventRouter:
    """Create the input router around app/runtime callbacks."""
    return InputEventRouter(
        state_manager=core.state_manager,
        typed_buffer=core.typed_buffer,
        selection_tracker=core.selection_tracker,
        decode_buffer=decode_buffer,
        auto_conversion_enabled=auto_conversion_enabled,
        try_auto_conversion_at_space=try_auto_conversion_at_space,
        get_pending_auto_space=get_pending_auto_space,
        set_pending_auto_space=set_pending_auto_space,
        clear_last_retype_events=clear_last_retype_events,
        clear_last_auto_marker=clear_last_auto_marker,
        inject_deferred_space=inject_deferred_space,
        request_conversion=request_conversion,
        prime_selection_baseline_on_click=prime_selection_baseline_on_click,
        read_mouse_release_selection=read_mouse_release_selection,
    )
