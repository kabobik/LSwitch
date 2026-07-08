"""Runtime conversion facade."""

from __future__ import annotations

from dataclasses import dataclass

from lswitch.runtime_config import synced_learning_service
from lswitch.runtime_selection import update_selection_baseline


@dataclass(frozen=True)
class SpaceAutoConversionState:
    last_auto_marker: object | None
    pending_auto_space: bool


def create_space_auto_conversion_use_case(
    *,
    auto_detector,
    typed_buffer,
    xkb,
    virtual_kb,
    learning_service,
    timing: dict,
    debug: bool,
):
    """Create the space-triggered auto-conversion use case."""
    from lswitch.core.conversion_use_cases import SpaceAutoConversionUseCase
    from lswitch.core.retype_service import RetypeService

    return SpaceAutoConversionUseCase(
        auto_detector=auto_detector,
        typed_buffer=typed_buffer,
        xkb=xkb,
        retype_service=RetypeService(
            virtual_kb,
            xkb,
            debug=debug,
        ),
        learning_service=learning_service,
        timing=timing,
        debug=debug,
    )


def create_synced_space_auto_conversion_use_case(
    *,
    auto_detector,
    typed_buffer,
    xkb,
    virtual_kb,
    user_dict,
    user_dict_min_weight,
    learning_service,
    timing: dict,
    debug: bool,
    manual_weight_step: int,
):
    """Create space auto-conversion use case with learning service synced first."""
    return create_space_auto_conversion_use_case(
        auto_detector=auto_detector,
        typed_buffer=typed_buffer,
        xkb=xkb,
        virtual_kb=virtual_kb,
        learning_service=synced_learning_service(
            user_dict=user_dict,
            user_dict_min_weight=user_dict_min_weight,
            learning_service=learning_service,
            debug=debug,
            manual_weight_step=manual_weight_step,
        ),
        timing=timing,
        debug=debug,
    )


def create_manual_conversion_controller(
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
):
    """Create the manual conversion orchestration controller."""
    from lswitch.core.manual_conversion_controller import ManualConversionController

    return ManualConversionController(
        state_manager=state_manager,
        selection_tracker=selection_tracker,
        typed_buffer=typed_buffer,
        learning_service=learning_service,
        conversion_engine=conversion_engine,
        virtual_kb=virtual_kb,
        xkb=xkb,
        selection=selection,
        timing=timing,
        debug=debug,
        decode_events=decode_events,
        extract_last_word=extract_last_word,
        update_selection_baseline=update_selection_baseline,
    )


def create_synced_manual_conversion_controller(
    *,
    state_manager,
    selection_tracker,
    typed_buffer,
    user_dict,
    user_dict_min_weight,
    learning_service,
    conversion_engine,
    virtual_kb,
    xkb,
    selection,
    timing: dict,
    debug: bool,
    manual_weight_step: int,
    decode_events,
    extract_last_word,
    update_selection_baseline,
):
    """Create manual conversion controller with learning service synced first."""
    return create_manual_conversion_controller(
        state_manager=state_manager,
        selection_tracker=selection_tracker,
        typed_buffer=typed_buffer,
        learning_service=synced_learning_service(
            user_dict=user_dict,
            user_dict_min_weight=user_dict_min_weight,
            learning_service=learning_service,
            debug=debug,
            manual_weight_step=manual_weight_step,
        ),
        conversion_engine=conversion_engine,
        virtual_kb=virtual_kb,
        xkb=xkb,
        selection=selection,
        timing=timing,
        debug=debug,
        decode_events=decode_events,
        extract_last_word=extract_last_word,
        update_selection_baseline=update_selection_baseline,
    )


def execute_manual_conversion_with_session(*, controller, session) -> None:
    """Execute manual conversion and apply transient session updates."""
    result = controller.execute(
        last_auto_marker=session.last_marker,
        sticky_events=session.sticky_events,
    )
    session.apply_manual_result(result)


def decode_buffer_events(*, typed_buffer, context, events: list | None = None) -> str:
    """Decode explicit events or the current context event buffer."""
    if events is None:
        events = context.event_buffer
    return typed_buffer.decode(events)


def extract_last_word_events(
    *,
    typed_buffer,
    context,
    current_layout=None,
    xkb=None,
) -> tuple[str, list]:
    """Extract the last typed word text and its source events from a buffer."""
    token = typed_buffer.last_word(
        context,
        current_layout=current_layout,
        xkb=xkb,
    )
    return token.text, token.events


def apply_space_auto_conversion_result(
    *,
    result,
    last_auto_marker,
    pending_auto_space: bool,
) -> SpaceAutoConversionState:
    """Apply a space auto-conversion result to app-level marker state."""
    if result.marker_changed:
        last_auto_marker = result.marker
    if result.pending_space:
        pending_auto_space = True
    return SpaceAutoConversionState(
        last_auto_marker=last_auto_marker,
        pending_auto_space=pending_auto_space,
    )


def try_space_auto_conversion_at_boundary(
    *,
    use_case,
    session,
    context,
    threshold: int,
    auto_confirm_enabled: bool,
) -> bool:
    """Execute space auto-conversion and apply transient session updates."""
    result = use_case.execute(
        context=context,
        threshold=threshold,
        last_auto_marker=session.last_marker,
        auto_confirm_enabled=auto_confirm_enabled,
    )
    state = apply_space_auto_conversion_result(
        result=result,
        last_auto_marker=session.last_marker,
        pending_auto_space=session.pending_space,
    )
    session.apply_space_state(state)
    return result.space_consumed


def perform_space_auto_conversion_at_boundary(
    *,
    use_case,
    session,
    context,
    word_len: int,
    word_events: list,
    direction: str,
    original_word: str = "",
    original_lang: str = "",
) -> None:
    """Perform a known space auto-conversion and apply transient session updates."""
    result = use_case.perform_conversion(
        context=context,
        word_len=word_len,
        word_events=word_events,
        direction=direction,
        original_word=original_word,
        original_lang=original_lang,
    )
    state = apply_space_auto_conversion_result(
        result=result,
        last_auto_marker=session.last_marker,
        pending_auto_space=session.pending_space,
    )
    session.apply_space_state(state)


class ConversionRuntimeFacade:
    """Runtime facade for manual and space-triggered conversion flows."""

    def __init__(
        self,
        *,
        state_manager,
        selection_tracker,
        typed_buffer,
        auto_conversion_session,
        config,
        learning_service,
        get_auto_detector,
        get_conversion_engine,
        get_virtual_kb,
        get_xkb,
        get_selection,
        get_platform,
        get_user_dict,
        get_timing,
        debug: bool,
        manual_weight_step: int,
    ):
        self.state_manager = state_manager
        self.selection_tracker = selection_tracker
        self.typed_buffer = typed_buffer
        self.auto_conversion_session = auto_conversion_session
        self.config = config
        self.learning_service = learning_service
        self.get_auto_detector = get_auto_detector
        self.get_conversion_engine = get_conversion_engine
        self.get_virtual_kb = get_virtual_kb
        self.get_xkb = get_xkb
        self.get_selection = get_selection
        self.get_platform = get_platform
        self.get_user_dict = get_user_dict
        self.get_timing = get_timing
        self.debug = debug
        self.manual_weight_step = manual_weight_step

    def request_manual_conversion(self) -> None:
        """Run manual conversion and apply transient session updates."""
        execute_manual_conversion_with_session(
            controller=create_synced_manual_conversion_controller(
                state_manager=self.state_manager,
                selection_tracker=self.selection_tracker,
                typed_buffer=self.typed_buffer,
                user_dict=self.get_user_dict(),
                user_dict_min_weight=self.config.get("user_dict_min_weight", 2),
                learning_service=self.learning_service,
                conversion_engine=self.get_conversion_engine(),
                virtual_kb=self.get_virtual_kb(),
                xkb=self.get_xkb(),
                selection=self.get_selection(),
                timing=self.get_timing(),
                debug=self.debug,
                manual_weight_step=self.manual_weight_step,
                decode_events=self.decode_buffer,
                extract_last_word=self.extract_last_word,
                update_selection_baseline=self.update_selection_baseline,
            ),
            session=self.auto_conversion_session,
        )

    def try_space_auto_conversion(self) -> bool:
        """Try space-triggered auto conversion at the current word boundary."""
        return try_space_auto_conversion_at_boundary(
            use_case=self.create_space_auto_conversion_use_case(),
            session=self.auto_conversion_session,
            context=self.state_manager.context,
            threshold=self.config.get("auto_switch_threshold", 0),
            auto_confirm_enabled=self.config.get(
                "user_dict_auto_confirm",
                False,
            ),
        )

    def perform_space_auto_conversion(
        self,
        *,
        word_len: int,
        word_events: list,
        direction: str,
        original_word: str = "",
        original_lang: str = "",
    ) -> None:
        """Perform a known space auto-conversion and update session state."""
        perform_space_auto_conversion_at_boundary(
            use_case=self.create_space_auto_conversion_use_case(),
            session=self.auto_conversion_session,
            context=self.state_manager.context,
            word_len=word_len,
            word_events=word_events,
            direction=direction,
            original_word=original_word,
            original_lang=original_lang,
        )

    def decode_buffer(self, events: list | None = None) -> str:
        """Decode explicit events or the current context event buffer."""
        return decode_buffer_events(
            typed_buffer=self.typed_buffer,
            context=self.state_manager.context,
            events=events,
        )

    def extract_last_word(self, current_layout=None) -> tuple[str, list]:
        """Extract the last typed word text and its source events."""
        return extract_last_word_events(
            typed_buffer=self.typed_buffer,
            context=self.state_manager.context,
            current_layout=current_layout,
            xkb=self.get_xkb(),
        )

    def update_selection_baseline(self) -> None:
        """Refresh passive selection baseline through runtime selection helpers."""
        update_selection_baseline(
            selection_tracker=self.selection_tracker,
            selection=self.get_selection(),
            platform=self.get_platform(),
        )

    def create_space_auto_conversion_use_case(self):
        """Create a synced space auto-conversion use case for current adapters."""
        return create_synced_space_auto_conversion_use_case(
            auto_detector=self.get_auto_detector(),
            typed_buffer=self.typed_buffer,
            xkb=self.get_xkb(),
            virtual_kb=self.get_virtual_kb(),
            user_dict=self.get_user_dict(),
            user_dict_min_weight=self.config.get("user_dict_min_weight", 2),
            learning_service=self.learning_service,
            timing=self.get_timing(),
            debug=self.debug,
            manual_weight_step=self.manual_weight_step,
        )
