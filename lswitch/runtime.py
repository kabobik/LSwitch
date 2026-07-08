"""Runtime component factories."""

import logging
from dataclasses import dataclass

from lswitch.core.conversion_engine import ConversionEngine
from lswitch.core.event_bus import EventBus
from lswitch.core.event_manager import EventManager
from lswitch.core.input_router import (
    InputConversionPort,
    InputEventRouter,
    InputSelectionPort,
)
from lswitch.core.learning_service import LearningService
from lswitch.core.selection_tracker import SelectionFreshnessTracker
from lswitch.core.state_manager import StateManager
from lswitch.core.typed_buffer import TypedBufferService
from lswitch.intelligence.auto_detector import AutoDetector
from lswitch.intelligence.dictionary_service import DictionaryService
from lswitch.intelligence.ngram_analyzer import NgramAnalyzer
from lswitch.runtime_config import (
    AppliedRuntimeConfig,
    RuntimeConfigSnapshot,
    apply_runtime_config_update,
    apply_runtime_timing_config,
    apply_user_dictionary_config,
    enable_user_dictionary_if_needed,
    read_runtime_config_snapshot,
    synced_learning_service,
    sync_user_dictionary_components,
)
from lswitch.runtime_conversion import (
    ConversionRuntimeFacade,
    SpaceAutoConversionState,
    apply_space_auto_conversion_result,
    create_mid_word_auto_conversion_use_case,
    create_manual_conversion_controller,
    create_space_auto_conversion_use_case,
    create_synced_manual_conversion_controller,
    create_synced_space_auto_conversion_use_case,
    decode_buffer_events,
    execute_manual_conversion_with_session,
    extract_last_word_events,
    perform_space_auto_conversion_at_boundary,
    try_mid_word_auto_conversion,
    try_space_auto_conversion_at_boundary,
)
from lswitch.runtime_selection import (
    handle_poller_selection_changed,
    read_mouse_release_selection,
    selection_baseline_tracking_enabled,
    set_selection_valid_with_logging,
    update_passive_selection_baseline_on_click,
    update_selection_baseline,
)
from lswitch.runtime_lifecycle import (
    PidLock,
    QtRuntimeBootstrap,
    SelectionPollerThread,
    StartedRuntimeResources,
    create_qt_runtime_bootstrap,
    create_tray_indicator,
    install_reload_signal_handler,
    is_process_alive,
    kill_existing_instance,
    pid_lock_path,
    read_existing_pid,
    run_evdev_event_loop,
    run_evdev_runtime_until_stopped,
    run_qt_app_runtime,
    run_qt_runtime_loop,
    run_selected_runtime_loop,
    start_runtime_resources,
    stop_runtime_resources,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RuntimeCoreComponents:
    event_bus: EventBus
    state_manager: StateManager
    typed_buffer: TypedBufferService
    selection_tracker: SelectionFreshnessTracker
    learning_service: LearningService


@dataclass(frozen=True)
class InputRouterCallbacks:
    conversion: InputConversionPort
    selection: InputSelectionPort


@dataclass(frozen=True)
class ConversionRuntimeComponents:
    dictionary: DictionaryService
    ngrams: NgramAnalyzer
    auto_detector: AutoDetector
    prefix_dictionary: object
    mid_word_detector: object
    conversion_engine: ConversionEngine


@dataclass(frozen=True)
class InputDeviceRuntimeComponents:
    event_manager: EventManager
    device_manager: object
    udev_monitor: object


@dataclass(frozen=True)
class PlatformRuntimeComponents:
    platform: object
    conversion: ConversionRuntimeComponents
    input_devices: InputDeviceRuntimeComponents


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


def create_input_router_callbacks(
    *,
    conversion_runtime,
    selection_tracker,
    config,
    get_auto_detector,
    get_virtual_kb,
    get_selection,
    get_platform,
    log,
) -> InputRouterCallbacks:
    """Create late-bound callbacks needed by InputEventRouter."""
    auto_conversion_session = conversion_runtime.auto_conversion_session
    return InputRouterCallbacks(
        conversion=InputConversionPort(
            decode_buffer=conversion_runtime.decode_buffer,
            auto_conversion_enabled=lambda: auto_conversion_enabled(
                config=config,
                auto_detector=get_auto_detector(),
            ),
            try_auto_conversion_at_space=(
                conversion_runtime.try_space_auto_conversion
            ),
            mid_word_auto_conversion_enabled=lambda: mid_word_auto_conversion_enabled(
                config=config,
                mid_word_detector=conversion_runtime.get_mid_word_detector(),
            ),
            try_mid_word_auto_conversion=(
                conversion_runtime.try_mid_word_auto_conversion
            ),
            get_pending_auto_space=lambda: auto_conversion_session.pending_space,
            set_pending_auto_space=auto_conversion_session.set_pending_space,
            clear_last_retype_events=auto_conversion_session.clear_sticky_events,
            clear_last_auto_marker=auto_conversion_session.clear_marker,
            inject_deferred_space=lambda: inject_deferred_space(get_virtual_kb()),
            request_conversion=conversion_runtime.request_manual_conversion,
        ),
        selection=InputSelectionPort(
            prime_baseline_on_click=lambda: update_passive_selection_baseline_on_click(
                selection_tracker=selection_tracker,
                selection=get_selection(),
                platform=get_platform(),
                log=log,
            ),
            read_mouse_release_selection=lambda: read_mouse_release_selection(
                selection=get_selection(),
                platform=get_platform(),
            ),
        ),
    )


def auto_conversion_enabled(*, config, auto_detector) -> bool:
    """Return whether space-triggered auto-conversion is currently available."""
    return bool(auto_detector and config.get("auto_switch"))


def mid_word_auto_conversion_enabled(*, config, mid_word_detector) -> bool:
    """Return whether mid-word auto-conversion is currently available."""
    return bool(mid_word_detector and config.get("auto_switch_mid_word"))


def inject_deferred_space(virtual_kb) -> None:
    """Inject the deferred Space key after auto-conversion consumes press-time Space."""
    if virtual_kb:
        from lswitch.core.event_manager import KEY_SPACE

        virtual_kb.tap_key(KEY_SPACE)


def create_input_router(
    *,
    core: RuntimeCoreComponents,
    callbacks: InputRouterCallbacks,
) -> InputEventRouter:
    """Create the input router around app/runtime callbacks."""
    return InputEventRouter(
        state_manager=core.state_manager,
        typed_buffer=core.typed_buffer,
        selection_tracker=core.selection_tracker,
        conversion=callbacks.conversion,
        selection=callbacks.selection,
    )


def wire_runtime_event_bus(*, event_bus: EventBus, input_router, on_config_changed) -> None:
    """Subscribe runtime input and config handlers to the event bus."""
    from lswitch.core.events import EventType

    event_bus.subscribe(EventType.KEY_PRESS, input_router.on_key_press)
    event_bus.subscribe(EventType.KEY_RELEASE, input_router.on_key_release)
    event_bus.subscribe(EventType.KEY_REPEAT, input_router.on_key_repeat)
    event_bus.subscribe(EventType.MOUSE_CLICK, input_router.on_mouse_click)
    event_bus.subscribe(EventType.MOUSE_RELEASE, input_router.on_mouse_release)
    event_bus.subscribe(EventType.CONFIG_CHANGED, on_config_changed)


def create_conversion_runtime(
    *,
    xkb,
    selection,
    virtual_kb,
    system,
    user_dict,
    user_dict_min_weight: int,
    debug: bool,
    timing: dict,
    mid_word_min_prefix_len: int = 4,
    system_dict_enabled: bool = False,
    system_dict_en_path: str = "",
    system_dict_ru_path: str = "",
) -> ConversionRuntimeComponents:
    """Create dictionary, auto-detection, and conversion executor services."""
    from lswitch.intelligence.mid_word_detector import MidWordDetector
    from lswitch.intelligence.prefix_dictionary import PrefixDictionary
    from lswitch.intelligence.system_dictionary_loader import SystemDictionaryLoader

    dictionary = DictionaryService()
    ngrams = NgramAnalyzer()
    system_loader = SystemDictionaryLoader(
        explicit_paths={
            "en": system_dict_en_path,
            "ru": system_dict_ru_path,
        },
    )
    prefix_dictionary = PrefixDictionary.from_dictionary_service(
        dictionary,
        min_prefix_len=mid_word_min_prefix_len,
        system_loader=system_loader,
        include_system=system_dict_enabled,
    )
    return ConversionRuntimeComponents(
        dictionary=dictionary,
        ngrams=ngrams,
        auto_detector=AutoDetector(
            dictionary=dictionary,
            ngrams=ngrams,
            user_dict=user_dict,
            user_dict_min_weight=user_dict_min_weight,
        ),
        prefix_dictionary=prefix_dictionary,
        mid_word_detector=MidWordDetector(
            prefix_dictionary,
            min_prefix_len=mid_word_min_prefix_len,
        ),
        conversion_engine=ConversionEngine(
            xkb=xkb,
            selection=selection,
            virtual_kb=virtual_kb,
            dictionary=dictionary,
            system=system,
            user_dict=user_dict,
            debug=debug,
            timing=timing,
        ),
    )


def create_input_device_runtime(
    *,
    event_bus: EventBus,
    virtual_kb,
    debug: bool,
) -> InputDeviceRuntimeComponents:
    """Create raw input event and hot-plug runtime services."""
    from lswitch.input.device_manager import DeviceManager
    from lswitch.input.udev_monitor import UdevMonitor
    from lswitch.input.virtual_keyboard import VirtualKeyboard

    event_manager = EventManager(event_bus, debug=debug)
    device_manager = DeviceManager(debug=debug)
    if virtual_kb:
        device_manager.set_virtual_kb_name(VirtualKeyboard.DEVICE_NAME)
    udev_monitor = UdevMonitor(
        on_added=device_manager._try_add_device,
        on_removed=lambda path: device_manager.remove_device(path),
    )
    return InputDeviceRuntimeComponents(
        event_manager=event_manager,
        device_manager=device_manager,
        udev_monitor=udev_monitor,
    )


def create_platform_runtime_components(
    *,
    debug: bool,
    main_thread,
    wayland_selection_strategy,
    timing: dict,
    x11_selection_timing: dict,
    wayland_timing: dict,
    wayland_selection_timing: dict,
    event_bus: EventBus,
    user_dict,
    user_dict_min_weight: int,
    mid_word_min_prefix_len: int = 4,
    system_dict_enabled: bool = False,
    system_dict_en_path: str = "",
    system_dict_ru_path: str = "",
) -> PlatformRuntimeComponents:
    """Create platform adapters plus dependent conversion and input runtimes."""
    from lswitch.platform.platform_factory import create_platform_adapters

    platform = create_platform_adapters(
        debug=debug,
        main_thread=main_thread,
        wayland_selection_strategy=wayland_selection_strategy,
        timing=timing,
        x11_selection_timing=x11_selection_timing,
        wayland_timing=wayland_timing,
        wayland_selection_timing=wayland_selection_timing,
    )
    conversion = create_conversion_runtime(
        xkb=platform.xkb,
        selection=platform.selection,
        virtual_kb=platform.virtual_kb,
        system=platform.system,
        user_dict=user_dict,
        user_dict_min_weight=user_dict_min_weight,
        debug=debug,
        timing=timing,
        mid_word_min_prefix_len=mid_word_min_prefix_len,
        system_dict_enabled=system_dict_enabled,
        system_dict_en_path=system_dict_en_path,
        system_dict_ru_path=system_dict_ru_path,
    )
    input_devices = create_input_device_runtime(
        event_bus=event_bus,
        virtual_kb=platform.virtual_kb,
        debug=debug,
    )
    return PlatformRuntimeComponents(
        platform=platform,
        conversion=conversion,
        input_devices=input_devices,
    )
