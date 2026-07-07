"""LSwitchApp — main application class, unifies input runtime and GUI."""

from __future__ import annotations

import logging
import sys

import lswitch.log  # registers TRACE level and logger.trace()
from lswitch.config import ConfigManager
from lswitch.runtime import (
    PidLock,
    SelectionPollerThread,
    apply_runtime_timing_config,
    apply_user_dictionary_config,
    create_core_components,
    create_input_router,
    create_manual_conversion_controller,
    create_platform_runtime_components,
    create_qt_runtime_bootstrap,
    create_space_auto_conversion_use_case,
    create_tray_indicator,
    extract_last_word_events,
    install_reload_signal_handler,
    run_evdev_event_loop,
    run_qt_runtime_loop,
    run_selected_runtime_loop,
    start_runtime_resources,
    stop_runtime_resources,
    sync_user_dictionary_components,
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
        self.timing = self.config.get('timing', {})
        self.x11_selection_timing = self.config.get('x11_selection_timing', {})
        self.wayland_timing = self.config.get('wayland_timing', {})
        self.wayland_selection_timing = self.config.get(
            'wayland_selection_timing',
            {},
        )

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

        self.input_router = create_input_router(
            core=core,
            decode_buffer=self._decode_buffer,
            auto_conversion_enabled=self._auto_conversion_enabled,
            try_auto_conversion_at_space=lambda: self._try_auto_conversion_at_space(),
            get_pending_auto_space=self._get_pending_auto_space,
            set_pending_auto_space=self._set_pending_auto_space,
            clear_last_retype_events=self._clear_last_retype_events,
            clear_last_auto_marker=self._clear_last_auto_marker,
            inject_deferred_space=self._inject_deferred_space,
            request_conversion=lambda: self._do_conversion(),
            prime_selection_baseline_on_click=(
                lambda: self._update_passive_selection_baseline_on_click()
            ),
            read_mouse_release_selection=self._read_mouse_release_selection,
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
        self.auto_detector = None
        self.user_dict = None
        self._last_auto_marker = None
        self._last_retype_events: list = []   # sticky buffer for repeat Shift+Shift
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
        )
        self._platform = platform_runtime.platform
        self.system = self._platform.system
        self.xkb = self._platform.xkb
        self.selection = self._platform.selection
        self.virtual_kb = self._platform.virtual_kb

        conversion_runtime = platform_runtime.conversion
        self.auto_detector = conversion_runtime.auto_detector
        self.conversion_engine = conversion_runtime.conversion_engine
        self._sync_learning_components()

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
            on_config_changed=self._on_config_changed,
        )

    def _enable_user_dictionary(self):
        """Create the user dictionary object when runtime config enables it."""
        if self.user_dict is not None:
            return self.user_dict
        from lswitch.intelligence.user_dictionary import UserDictionary

        self.user_dict = UserDictionary()
        logger.info("User dictionary enabled: %s", self.user_dict.path)
        return self.user_dict

    def _sync_learning_components(self) -> None:
        """Propagate current UserDictionary settings into runtime components."""
        sync_user_dictionary_components(
            user_dict=self.user_dict,
            user_dict_min_weight=self.config.get('user_dict_min_weight', 2),
            auto_detector=self.auto_detector,
            conversion_engine=self.conversion_engine,
            learning_service=self.learning_service,
            debug=self.debug,
            manual_weight_step=self.MANUAL_WEIGHT_STEP,
        )

    def _learning(self):
        """Return LearningService synced with the current app-level user_dict."""
        sync_user_dictionary_components(
            user_dict=self.user_dict,
            user_dict_min_weight=self.config.get('user_dict_min_weight', 2),
            auto_detector=None,
            conversion_engine=None,
            learning_service=self.learning_service,
            debug=self.debug,
            manual_weight_step=self.MANUAL_WEIGHT_STEP,
        )
        return self.learning_service

    def _apply_runtime_config(self) -> None:
        """Apply config values that affect already-created runtime objects."""
        timing_config = apply_runtime_timing_config(
            config=self.config,
            state_manager=self.state_manager,
            conversion_engine=self.conversion_engine,
        )
        self.timing = timing_config.timing
        self.x11_selection_timing = timing_config.x11_selection_timing
        self.wayland_timing = timing_config.wayland_timing
        self.wayland_selection_timing = timing_config.wayland_selection_timing

        self.user_dict = apply_user_dictionary_config(
            config=self.config,
            user_dict=self.user_dict,
            enable_user_dictionary=self._enable_user_dictionary,
            log=logger,
        )
        self._sync_learning_components()

    def _on_config_changed(self, event) -> None:
        self._apply_runtime_config()

    # ------------------------------------------------------------------
    # Event callbacks
    # ------------------------------------------------------------------

    @property
    def _selection_valid(self) -> bool:
        return self.selection_tracker.valid

    @_selection_valid.setter
    def _selection_valid(self, value: bool) -> None:
        old_value = self.selection_tracker.valid
        if value != old_value:
            logger.debug(
                "fresh=%s → %s",
                old_value, value,
            )
            self.selection_tracker.set_valid(value)
        else:
            self.selection_tracker.set_valid(value)
        # Log at TRACE every assignment and its source (guarded to avoid extract_stack overhead)
        if logger.isEnabledFor(5):  # TRACE = 5
            import traceback as _tb
            caller = _tb.extract_stack(limit=3)[-2]
            logger.trace(  # type: ignore[attr-defined]
                "fresh=%s (set by %s:%d)",
                self.selection_tracker.valid, caller.name, caller.lineno,
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

    def _clear_selection_repeat(self) -> None:
        self.selection_tracker.clear_repeat()

    def _auto_conversion_enabled(self) -> bool:
        return bool(self.auto_detector and self.config.get('auto_switch'))

    def _get_pending_auto_space(self) -> bool:
        return bool(getattr(self, '_pending_auto_space', False))

    def _set_pending_auto_space(self, value: bool) -> None:
        self._pending_auto_space = bool(value)

    def _clear_last_retype_events(self) -> None:
        self._last_retype_events = []

    def _clear_last_auto_marker(self) -> None:
        self._last_auto_marker = None

    def _inject_deferred_space(self) -> None:
        from lswitch.core.event_manager import KEY_SPACE

        if self.virtual_kb:
            self.virtual_kb.tap_key(KEY_SPACE)

    def _read_mouse_release_selection(self):
        if self.selection is None:
            return None
        if not getattr(
            self._platform,
            "selection_mouse_release_tracking_enabled",
            True,
        ):
            return None
        reader = self._passive_selection_reader()
        if reader is not None:
            return reader()
        return self.selection.get_selection()

    def _passive_selection_reader(self):
        """Return a no-shortcut selection reader when the adapter provides one."""
        from lswitch.platform.selection_adapter import get_passive_selection_reader

        return get_passive_selection_reader(self.selection)

    def _update_passive_selection_baseline_on_click(self) -> None:
        """Prime baseline on platforms with safe passive selection reads."""
        if self._platform is None:
            return
        if not getattr(
            self._platform,
            "selection_mouse_release_tracking_enabled",
            True,
        ):
            return
        reader = self._passive_selection_reader()
        if reader is None:
            return
        try:
            info = reader()
            result = self.selection_tracker.on_click_passive_selection(
                info.text or "",
                info.owner_id,
            )
            if result == "initial":
                logger.trace(  # type: ignore[attr-defined]
                    "MouseClick: initial passive selection baseline — text=%r",
                    info.text[:50] if info.text else "",
                )
                return
            if result == "fresh":
                logger.debug(
                    "MouseClick: fresh passive selection — text=%r owner=0x%x",
                    info.text[:50] if info.text else "", info.owner_id,
                )
                return
            logger.trace(  # type: ignore[attr-defined]
                "MouseClick: passive selection baseline — text=%r",
                info.text[:50] if info.text else "",
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _decode_buffer(self, events: list | None = None) -> str:
        """Decode event buffer to human-readable string of characters."""
        if events is None:
            events = self.state_manager.context.event_buffer
        return self.typed_buffer.decode(events)

    # ------------------------------------------------------------------
    # Selection validity tracking
    # ------------------------------------------------------------------

    def _on_poller_selection_changed(self, text: str, owner_id: int) -> None:
        """Called by SelectionPollerThread when platform selection changes.

        Sets fresh=True so the next Shift+Shift will use SelectionMode.
        Does NOT update baseline (_prev_sel_text / _prev_sel_owner_id) —
        baseline is maintained by _on_mouse_release and tracked conversions.
        """
        self.selection_tracker.on_poller_changed()
        logger.debug(
            "Poller: selection changed, fresh=True — text=%r owner=0x%x",
            text[:50] if text else "", owner_id,
        )

    def _selection_baseline_tracking_enabled(self) -> bool:
        """Return whether passive selection baseline reads are safe/useful."""
        if self._platform is None:
            return True

        polling = getattr(self._platform, "selection_polling_enabled", None)
        mouse_release = getattr(
            self._platform,
            "selection_mouse_release_tracking_enabled",
            None,
        )
        if polling is None and mouse_release is None:
            return True
        return bool(polling or mouse_release)

    def _update_selection_baseline(self) -> None:
        """Update passive selection baseline when the platform supports it."""
        if self.selection is None or not self._selection_baseline_tracking_enabled():
            return
        try:
            reader = self._passive_selection_reader()
            info = reader() if reader is not None else self.selection.get_selection()
            self.selection_tracker.update_baseline(
                info.text or "",
                info.owner_id,
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Conversion
    # ------------------------------------------------------------------

    def _do_conversion(self):
        """Trigger conversion if state machine is in CONVERTING state.

        User-dict learning logic:
          A) Shift+Shift right after auto-conversion (undo):
             _last_auto_marker is set, event_buffer is empty (reset by auto-conv).
             → add_correction(typed_word, typed_lang)  — keep confidence +2
          B) Pure manual Shift+Shift (no prior auto-conversion):
             _last_auto_marker is None, event_buffer has the typed chars.
             → add_confirmation(typed_word, typed_lang)  — convert confidence +2
             Weight accumulates across sessions; once |weight| >= min_weight
             AutoDetector will handle this word automatically.
        """
        result = create_manual_conversion_controller(
            state_manager=self.state_manager,
            selection_tracker=self.selection_tracker,
            typed_buffer=self.typed_buffer,
            learning_service=self._learning(),
            conversion_engine=self.conversion_engine,
            virtual_kb=self.virtual_kb,
            xkb=self.xkb,
            selection=self.selection,
            timing=self.timing,
            debug=self.debug,
            decode_events=self._decode_buffer,
            extract_last_word=self._extract_last_word_events,
            update_selection_baseline=self._update_selection_baseline,
        ).execute(
            last_auto_marker=self._last_auto_marker,
            sticky_events=self._last_retype_events,
        )
        self._last_auto_marker = result.last_auto_marker
        self._last_retype_events = result.sticky_events

    # ------------------------------------------------------------------
    # Auto-conversion (space-triggered, AutoDetector)
    # ------------------------------------------------------------------

    def _try_auto_conversion_at_space(self) -> bool:
        """Check and perform auto-conversion at Space word boundary.

        Returns True if conversion was performed (Space consumed).
        Returns False if no conversion needed (Space should be added to buffer).

        ``auto_switch_threshold`` — minimum number of chars typed since last
        reset before auto-conversion activates.  Set to 0 (default) to
        convert from the very first word.  Increase to avoid false-positives
        at the start of a field (e.g., 5 = activate after ≥5 chars typed).
        """
        result = self._space_auto_conversion().execute(
            context=self.state_manager.context,
            threshold=self.config.get('auto_switch_threshold', 0),
            last_auto_marker=self._last_auto_marker,
            auto_confirm_enabled=self.config.get('user_dict_auto_confirm', False),
        )

        if result.marker_changed:
            self._last_auto_marker = result.marker
        if result.pending_space:
            self._pending_auto_space = True

        return result.space_consumed

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
        return extract_last_word_events(
            typed_buffer=self.typed_buffer,
            context=self.state_manager.context,
            current_layout=current_layout,
            xkb=self.xkb,
        )

    def _do_auto_conversion_at_space(
        self, word_len: int, word_events: list, direction: str,
        orig_word: str = "", orig_lang: str = "",
    ) -> None:
        """Perform auto-conversion: delete (word + space), retype in target layout, add space.

        The Space key was already delivered to the active application before LSwitch processed
        it (passive monitoring), so we must also delete that extra space character via backspace.
        """
        result = self._space_auto_conversion().perform_conversion(
            context=self.state_manager.context,
            word_len=word_len,
            word_events=word_events,
            direction=direction,
            original_word=orig_word,
            original_lang=orig_lang,
        )
        if result.pending_space:
            self._pending_auto_space = True
        if result.marker_changed:
            self._last_auto_marker = result.marker

    def _space_auto_conversion(self):
        return create_space_auto_conversion_use_case(
            auto_detector=self.auto_detector,
            typed_buffer=self.typed_buffer,
            xkb=self.xkb,
            virtual_kb=self.virtual_kb,
            learning_service=self._learning(),
            timing=self.timing,
            debug=self.debug,
        )

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
            run_qt_loop=self._run_with_qt_loop,
            run_evdev_loop=self._run_evdev_loop,
        )

    def _run_evdev_loop(self):
        """Evdev event loop (blocking, main thread)."""
        try:
            run_evdev_event_loop(
                is_running=lambda: self._running,
                device_manager=self.device_manager,
                event_manager=self.event_manager,
            )
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def _run_with_qt_loop(self, qt_app, show_tray: bool):
        """Run evdev in a worker thread while the main thread runs Qt."""
        def _create_tray():
            return create_tray_indicator(
                event_bus=self.event_bus,
                config=self.config,
                qt_app=qt_app,
                owner_app=self,
                xkb=self.xkb,
            )

        def _run_evdev_loop():
            run_evdev_event_loop(
                is_running=lambda: self._running,
                device_manager=self.device_manager,
                event_manager=self.event_manager,
            )

        run_qt_runtime_loop(
            qt_app=qt_app,
            event_bus=self.event_bus,
            show_tray=show_tray,
            create_tray=_create_tray,
            run_evdev_loop=_run_evdev_loop,
            stop_runtime=self.stop,
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
