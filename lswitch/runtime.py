"""Runtime component factories."""

import logging
from collections.abc import Callable
from dataclasses import dataclass

from lswitch.core.conversion_engine import ConversionEngine
from lswitch.core.event_bus import EventBus
from lswitch.core.event_manager import EventManager
from lswitch.core.input_router import InputEventRouter
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
from lswitch.runtime_conversion import ConversionRuntimeFacade
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
    decode_buffer: Callable[[], str]
    auto_conversion_enabled: Callable[[], bool]
    try_auto_conversion_at_space: Callable[[], bool]
    get_pending_auto_space: Callable[[], bool]
    set_pending_auto_space: Callable[[bool], None]
    clear_last_retype_events: Callable[[], None]
    clear_last_auto_marker: Callable[[], None]
    inject_deferred_space: Callable[[], None]
    request_conversion: Callable[[], None]
    prime_selection_baseline_on_click: Callable[[], None]
    read_mouse_release_selection: Callable[[], object | None]


@dataclass(frozen=True)
class ConversionRuntimeComponents:
    dictionary: DictionaryService
    ngrams: NgramAnalyzer
    auto_detector: AutoDetector
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


@dataclass(frozen=True)
class SpaceAutoConversionState:
    last_auto_marker: object | None
    pending_auto_space: bool


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
    decode_buffer,
    try_auto_conversion_at_space,
    auto_conversion_session,
    request_conversion,
    selection_tracker,
    config,
    get_auto_detector,
    get_virtual_kb,
    get_selection,
    get_platform,
    log,
) -> InputRouterCallbacks:
    """Create late-bound callbacks needed by InputEventRouter."""
    return InputRouterCallbacks(
        decode_buffer=decode_buffer,
        auto_conversion_enabled=(
            lambda: auto_conversion_enabled(
                config=config,
                auto_detector=get_auto_detector(),
            )
        ),
        try_auto_conversion_at_space=try_auto_conversion_at_space,
        get_pending_auto_space=lambda: auto_conversion_session.pending_space,
        set_pending_auto_space=auto_conversion_session.set_pending_space,
        clear_last_retype_events=auto_conversion_session.clear_sticky_events,
        clear_last_auto_marker=auto_conversion_session.clear_marker,
        inject_deferred_space=lambda: inject_deferred_space(get_virtual_kb()),
        request_conversion=request_conversion,
        prime_selection_baseline_on_click=(
            lambda: update_passive_selection_baseline_on_click(
                selection_tracker=selection_tracker,
                selection=get_selection(),
                platform=get_platform(),
                log=log,
            )
        ),
        read_mouse_release_selection=(
            lambda: read_mouse_release_selection(
                selection=get_selection(),
                platform=get_platform(),
            )
        ),
    )


def auto_conversion_enabled(*, config, auto_detector) -> bool:
    """Return whether space-triggered auto-conversion is currently available."""
    return bool(auto_detector and config.get("auto_switch"))


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
        decode_buffer=callbacks.decode_buffer,
        auto_conversion_enabled=callbacks.auto_conversion_enabled,
        try_auto_conversion_at_space=callbacks.try_auto_conversion_at_space,
        get_pending_auto_space=callbacks.get_pending_auto_space,
        set_pending_auto_space=callbacks.set_pending_auto_space,
        clear_last_retype_events=callbacks.clear_last_retype_events,
        clear_last_auto_marker=callbacks.clear_last_auto_marker,
        inject_deferred_space=callbacks.inject_deferred_space,
        request_conversion=callbacks.request_conversion,
        prime_selection_baseline_on_click=callbacks.prime_selection_baseline_on_click,
        read_mouse_release_selection=callbacks.read_mouse_release_selection,
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
) -> ConversionRuntimeComponents:
    """Create dictionary, auto-detection, and conversion executor services."""
    dictionary = DictionaryService()
    ngrams = NgramAnalyzer()
    return ConversionRuntimeComponents(
        dictionary=dictionary,
        ngrams=ngrams,
        auto_detector=AutoDetector(
            dictionary=dictionary,
            ngrams=ngrams,
            user_dict=user_dict,
            user_dict_min_weight=user_dict_min_weight,
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
