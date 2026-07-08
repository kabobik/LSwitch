"""Runtime conversion facade."""

from __future__ import annotations


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
        from lswitch import runtime as runtime_helpers

        runtime_helpers.execute_manual_conversion_with_session(
            controller=runtime_helpers.create_synced_manual_conversion_controller(
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
        from lswitch import runtime as runtime_helpers

        return runtime_helpers.try_space_auto_conversion_at_boundary(
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
        from lswitch import runtime as runtime_helpers

        runtime_helpers.perform_space_auto_conversion_at_boundary(
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
        from lswitch import runtime as runtime_helpers

        return runtime_helpers.decode_buffer_events(
            typed_buffer=self.typed_buffer,
            context=self.state_manager.context,
            events=events,
        )

    def extract_last_word(self, current_layout=None) -> tuple[str, list]:
        """Extract the last typed word text and its source events."""
        from lswitch import runtime as runtime_helpers

        return runtime_helpers.extract_last_word_events(
            typed_buffer=self.typed_buffer,
            context=self.state_manager.context,
            current_layout=current_layout,
            xkb=self.get_xkb(),
        )

    def update_selection_baseline(self) -> None:
        """Refresh passive selection baseline through runtime selection helpers."""
        from lswitch import runtime as runtime_helpers

        runtime_helpers.update_selection_baseline(
            selection_tracker=self.selection_tracker,
            selection=self.get_selection(),
            platform=self.get_platform(),
        )

    def create_space_auto_conversion_use_case(self):
        """Create a synced space auto-conversion use case for current adapters."""
        from lswitch import runtime as runtime_helpers

        return runtime_helpers.create_synced_space_auto_conversion_use_case(
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
