"""LSwitchApp — main application class, unifies input runtime and GUI."""

from __future__ import annotations

import logging
import sys

import lswitch.log  # registers TRACE level and logger.trace()
from lswitch.config import ConfigManager
from lswitch.core.auto_conversion_session import AutoConversionSessionState
from lswitch.runtime import (
    ConversionRuntimeFacade,
    PidLock,
    SelectionPollerThread,
    apply_runtime_config_update,
    create_core_components,
    create_input_router,
    create_input_router_callbacks,
    create_mid_word_detection_runtime,
    create_platform_runtime_components,
    create_qt_runtime_bootstrap,
    enable_user_dictionary_if_needed,
    handle_poller_selection_changed,
    install_reload_signal_handler,
    read_runtime_config_snapshot,
    run_evdev_runtime_until_stopped,
    run_qt_app_runtime,
    run_selected_runtime_loop,
    start_runtime_resources,
    stop_runtime_resources,
    sync_user_dictionary_components,
    set_selection_valid_with_logging,
    wire_runtime_event_bus,
)

logger = logging.getLogger(__name__)


class LSwitchApp:
    """Single-process application combining input daemon and tray GUI.

    Modes:
        headless=True  — no visible GUI/tray
        headless=False — with tray icon (default)

    ``_init_platform()`` is separated from ``__init__`` so that tests
    can inject mocks without touching real platform / evdev resources.
    """

    MANUAL_WEIGHT_STEP = 2

    def __init__(
        self,
        headless: bool = False,
        debug: bool = False,
        config_path: str | None = None,
        replace: bool = False,
    ):
        self.headless = headless
        self.debug = debug
        self._running = False
        self._replace = replace
        self._pid_lock: PidLock | None = None

        # Configuration
        self.config = ConfigManager(config_path=config_path, debug=debug)
        runtime_config = read_runtime_config_snapshot(config=self.config)
        self.timing = runtime_config.timing
        self.x11_selection_timing = runtime_config.x11_selection_timing
        self.wayland_timing = runtime_config.wayland_timing
        self.wayland_selection_timing = runtime_config.wayland_selection_timing

        core = create_core_components(
            double_click_timeout=self.config.get('double_click_timeout', 0.3),
            debug=debug,
            manual_weight_step=self.MANUAL_WEIGHT_STEP,
        )
        self.event_bus = core.event_bus
        self.state_manager = core.state_manager
        self.typed_buffer = core.typed_buffer
        self.selection_tracker = core.selection_tracker
        self.learning_service = core.learning_service
        self.auto_conversion_session = AutoConversionSessionState()
        self.conversion_runtime = ConversionRuntimeFacade(
            state_manager=self.state_manager,
            selection_tracker=self.selection_tracker,
            typed_buffer=self.typed_buffer,
            auto_conversion_session=self.auto_conversion_session,
            config=self.config,
            learning_service=self.learning_service,
            get_auto_detector=lambda: self.auto_detector,
            get_mid_word_detector=lambda: self.mid_word_detector,
            get_conversion_engine=lambda: self.conversion_engine,
            get_virtual_kb=lambda: self.virtual_kb,
            get_xkb=lambda: self.xkb,
            get_selection=lambda: self.selection,
            get_platform=lambda: self._platform,
            get_user_dict=lambda: self.user_dict,
            get_timing=lambda: self.timing,
            debug=self.debug,
            manual_weight_step=self.MANUAL_WEIGHT_STEP,
        )

        self.input_router = create_input_router(
            core=core,
            callbacks=create_input_router_callbacks(
                conversion_runtime=self.conversion_runtime,
                selection_tracker=self.selection_tracker,
                config=self.config,
                get_auto_detector=lambda: self.auto_detector,
                get_virtual_kb=lambda: self.virtual_kb,
                get_selection=lambda: self.selection,
                get_platform=lambda: self._platform,
                log=logger,
            ),
        )

        # Platform adapters — created by _init_platform()
        self.xkb = None
        self.selection = None
        self.system = None
        self.virtual_kb = None
        self.device_manager = None
        self.conversion_engine = None
        self.event_manager = None
        self._udev_monitor = None
        self.dictionary = None
        self.prefix_dictionary = None
        self.auto_detector = None
        self.mid_word_detector = None
        self.user_dict = None
        self._platform = None
        self._selection_poller: SelectionPollerThread | None = None

    # ------------------------------------------------------------------
    # Platform initialisation (lazy — for testability)
    # ------------------------------------------------------------------

    def _init_platform(self, main_thread=None):
        """Initialise platform components.

        Separated from ``__init__`` so that tests can substitute mocks
        without requiring real platform / evdev resources.
        """
        # UserDictionary: self-learning word weights
        if self.config.get('user_dict_enabled'):
            self._enable_user_dictionary()

        platform_runtime = create_platform_runtime_components(
            debug=self.debug,
            main_thread=main_thread,
            wayland_selection_strategy=self.config.get(
                'wayland_selection_strategy',
                'auto',
            ),
            timing=self.timing,
            x11_selection_timing=self.x11_selection_timing,
            wayland_timing=self.wayland_timing,
            wayland_selection_timing=self.wayland_selection_timing,
            event_bus=self.event_bus,
            user_dict=self.user_dict,
            user_dict_min_weight=self.config.get('user_dict_min_weight', 2),
            mid_word_min_prefix_len=self.config.get('mid_word_min_prefix_len', 4),
            system_dict_enabled=self.config.get('system_dict_enabled', True),
            system_dict_en_path=self.config.get('system_dict_en_path', ''),
            system_dict_ru_path=self.config.get('system_dict_ru_path', ''),
        )
        self._platform = platform_runtime.platform
        self.system = self._platform.system
        self.xkb = self._platform.xkb
        self.selection = self._platform.selection
        self.virtual_kb = self._platform.virtual_kb

        conversion_runtime = platform_runtime.conversion
        self.dictionary = conversion_runtime.dictionary
        self.prefix_dictionary = conversion_runtime.prefix_dictionary
        self.auto_detector = conversion_runtime.auto_detector
        self.mid_word_detector = conversion_runtime.mid_word_detector
        self.conversion_engine = conversion_runtime.conversion_engine
        sync_user_dictionary_components(
            user_dict=self.user_dict,
            user_dict_min_weight=self.config.get('user_dict_min_weight', 2),
            auto_detector=self.auto_detector,
            conversion_engine=self.conversion_engine,
            learning_service=self.learning_service,
            debug=self.debug,
            manual_weight_step=self.MANUAL_WEIGHT_STEP,
        )

        input_runtime = platform_runtime.input_devices
        self.event_manager = input_runtime.event_manager
        self.device_manager = input_runtime.device_manager
        self._udev_monitor = input_runtime.udev_monitor

    # ------------------------------------------------------------------
    # Event bus wiring
    # ------------------------------------------------------------------

    def _wire_event_bus(self):
        """Subscribe event handlers to the EventBus."""
        wire_runtime_event_bus(
            event_bus=self.event_bus,
            input_router=self.input_router,
            on_config_changed=lambda event: self._apply_runtime_config(),
        )

    def _enable_user_dictionary(self):
        """Create the user dictionary object when runtime config enables it."""
        self.user_dict = enable_user_dictionary_if_needed(
            user_dict=self.user_dict,
            log=logger,
        )
        return self.user_dict

    def _apply_runtime_config(self) -> None:
        """Apply config values that affect already-created runtime objects."""
        applied = apply_runtime_config_update(
            config=self.config,
            state_manager=self.state_manager,
            conversion_engine=self.conversion_engine,
            user_dict=self.user_dict,
            enable_user_dictionary=self._enable_user_dictionary,
            auto_detector=self.auto_detector,
            learning_service=self.learning_service,
            debug=self.debug,
            manual_weight_step=self.MANUAL_WEIGHT_STEP,
            log=logger,
        )
        timing_config = applied.timing
        self.timing = timing_config.timing
        self.x11_selection_timing = timing_config.x11_selection_timing
        self.wayland_timing = timing_config.wayland_timing
        self.wayland_selection_timing = timing_config.wayland_selection_timing
        self.user_dict = applied.user_dict
        self._apply_mid_word_runtime_config()

    def _apply_mid_word_runtime_config(self) -> None:
        """Rebuild mid-word detection runtime after relevant config changes."""
        if self.dictionary is None:
            return
        mid_word_runtime = create_mid_word_detection_runtime(
            dictionary=self.dictionary,
            mid_word_min_prefix_len=self.config.get('mid_word_min_prefix_len', 4),
            system_dict_enabled=self.config.get('system_dict_enabled', True),
            system_dict_en_path=self.config.get('system_dict_en_path', ''),
            system_dict_ru_path=self.config.get('system_dict_ru_path', ''),
        )
        self.prefix_dictionary = mid_word_runtime.prefix_dictionary
        self.mid_word_detector = mid_word_runtime.mid_word_detector

    # ------------------------------------------------------------------
    # Event callbacks
    # ------------------------------------------------------------------

    @property
    def _selection_valid(self) -> bool:
        return self.selection_tracker.valid

    @_selection_valid.setter
    def _selection_valid(self, value: bool) -> None:
        set_selection_valid_with_logging(
            selection_tracker=self.selection_tracker,
            value=value,
            log=logger,
        )

    @property
    def _selection_generation(self) -> int:
        return self.selection_tracker.generation

    @_selection_generation.setter
    def _selection_generation(self, value: int) -> None:
        self.selection_tracker.generation = int(value)

    @property
    def _selection_repeat_valid(self) -> bool:
        return self.selection_tracker.repeat_valid

    @_selection_repeat_valid.setter
    def _selection_repeat_valid(self, value: bool) -> None:
        self.selection_tracker.repeat_valid = bool(value)

    @property
    def _selection_repeat_generation(self) -> int:
        return self.selection_tracker.repeat_generation

    @_selection_repeat_generation.setter
    def _selection_repeat_generation(self, value: int) -> None:
        self.selection_tracker.repeat_generation = int(value)

    @property
    def _prev_sel_text(self) -> str:
        return self.selection_tracker.prev_text

    @_prev_sel_text.setter
    def _prev_sel_text(self, value: str) -> None:
        self.selection_tracker.prev_text = value or ""

    @property
    def _prev_sel_owner_id(self) -> int:
        return self.selection_tracker.prev_owner_id

    @_prev_sel_owner_id.setter
    def _prev_sel_owner_id(self, value: int) -> None:
        self.selection_tracker.prev_owner_id = int(value)

    @property
    def _selection_baseline_initialized(self) -> bool:
        return self.selection_tracker.baseline_initialized

    @_selection_baseline_initialized.setter
    def _selection_baseline_initialized(self, value: bool) -> None:
        self.selection_tracker.baseline_initialized = bool(value)

    @property
    def _last_auto_marker(self):
        return self.auto_conversion_session.last_marker

    @_last_auto_marker.setter
    def _last_auto_marker(self, value) -> None:
        self.auto_conversion_session.last_marker = value

    @property
    def _last_retype_events(self) -> list:
        return self.auto_conversion_session.sticky_events

    @_last_retype_events.setter
    def _last_retype_events(self, value: list) -> None:
        self.auto_conversion_session.sticky_events = list(value or [])

    @property
    def _pending_auto_space(self) -> bool:
        return self.auto_conversion_session.pending_space

    @_pending_auto_space.setter
    def _pending_auto_space(self, value: bool) -> None:
        self.auto_conversion_session.set_pending_space(value)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _decode_buffer(self, events: list | None = None) -> str:
        """Decode event buffer to human-readable string of characters."""
        return self.conversion_runtime.decode_buffer(events)

    # ------------------------------------------------------------------
    # Selection validity tracking
    # ------------------------------------------------------------------

    def _on_poller_selection_changed(self, text: str, owner_id: int) -> None:
        """Called by SelectionPollerThread when platform selection changes.

        Sets fresh=True so the next Shift+Shift will use SelectionMode.
        Does NOT update baseline (_prev_sel_text / _prev_sel_owner_id) —
        baseline is maintained by _on_mouse_release and tracked conversions.
        """
        handle_poller_selection_changed(
            selection_tracker=self.selection_tracker,
            text=text,
            owner_id=owner_id,
            log=logger,
        )

    # ------------------------------------------------------------------
    # Conversion
    # ------------------------------------------------------------------

    def _do_conversion(self):
        """Compatibility wrapper for manual conversion requests."""
        self.conversion_runtime.request_manual_conversion()

    # ------------------------------------------------------------------
    # Auto-conversion (space-triggered, AutoDetector)
    # ------------------------------------------------------------------

    def _try_auto_conversion_at_space(self) -> bool:
        """Compatibility wrapper for space-triggered auto-conversion."""
        return self.conversion_runtime.try_space_auto_conversion()

    def _extract_last_word_events(self, current_layout=None) -> "tuple[str, list]":
        """Extract events for the last typed word from event_buffer.

        Scans backwards until a space or non-alpha character is found.
        Returns (word_str, word_events_in_order).

        When ``current_layout`` (a LayoutInfo) is provided and ``self.xkb`` is
        available, characters are resolved via the real XKB mapping so that
        Cyrillic letters on a RU layout are returned as Cyrillic (not as their
        EN physical-key equivalents, where б→, and ю→. are non-alpha and would
        truncate the word prematurely).
        """
        return self.conversion_runtime.extract_last_word(current_layout)

    def _do_auto_conversion_at_space(
        self, word_len: int, word_events: list, direction: str,
        orig_word: str = "", orig_lang: str = "",
    ) -> None:
        """Perform auto-conversion: delete (word + space), retype in target layout, add space.

        The Space key was already delivered to the active application before LSwitch processed
        it (passive monitoring), so we must also delete that extra space character via backspace.
        """
        self.conversion_runtime.perform_space_auto_conversion(
            word_len=word_len,
            word_events=word_events,
            direction=direction,
            original_word=orig_word,
            original_lang=orig_lang,
        )

    def _space_auto_conversion(self):
        return self.conversion_runtime.create_space_auto_conversion_use_case()

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self):
        """Blocking main event loop."""
        from lswitch.platform.platform_factory import create_runtime_plan

        runtime_plan = create_runtime_plan(headless=self.headless)

        # Защита от двойного запуска
        self._pid_lock = PidLock(replace=self._replace)
        self._pid_lock.acquire()

        try:
            qt_bootstrap = create_qt_runtime_bootstrap(
                runtime_plan=runtime_plan,
                argv=sys.argv,
            )
            self._init_platform(main_thread=qt_bootstrap.main_thread)
            self._wire_event_bus()
        except Exception:
            self.stop()
            raise

        started_runtime = start_runtime_resources(
            selection=self.selection,
            platform=self._platform,
            x11_selection_timing=self.x11_selection_timing,
            on_selection_changed=self._on_poller_selection_changed,
            device_manager=self.device_manager,
            udev_monitor=self._udev_monitor,
        )
        self._selection_poller = started_runtime.selection_poller

        self._running = True

        logger.info(
            "LSwitch 2.0 запущен (headless=%s, %d устройств)",
            self.headless,
            started_runtime.device_count,
        )

        install_reload_signal_handler(
            config=self.config,
            apply_runtime_config=self._apply_runtime_config,
            debug=self.debug,
            log=logger,
        )

        run_selected_runtime_loop(
            runtime_plan=runtime_plan,
            headless=self.headless,
            qt_app=qt_bootstrap.qt_app,
            argv=sys.argv,
            run_qt_loop=(
                lambda qt_app, show_tray: run_qt_app_runtime(
                    qt_app=qt_app,
                    event_bus=self.event_bus,
                    show_tray=show_tray,
                    config=self.config,
                    owner_app=self,
                    xkb=self.xkb,
                    is_running=lambda: self._running,
                    device_manager=self.device_manager,
                    event_manager=self.event_manager,
                    stop_runtime=self.stop,
                )
            ),
            run_evdev_loop=(
                lambda: run_evdev_runtime_until_stopped(
                    is_running=lambda: self._running,
                    device_manager=self.device_manager,
                    event_manager=self.event_manager,
                    stop_runtime=self.stop,
                )
            ),
        )

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def stop(self):
        """Graceful shutdown — safe to call multiple times."""
        self._running = False
        self._pid_lock = stop_runtime_resources(
            selection_poller=self._selection_poller,
            udev_monitor=self._udev_monitor,
            device_manager=self.device_manager,
            virtual_kb=self.virtual_kb,
            xkb=self.xkb,
            pid_lock=self._pid_lock,
        )
