"""Runtime component factories."""

import fcntl
import logging
import os
import signal
import threading
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
from lswitch.runtime_conversion import ConversionRuntimeFacade

logger = logging.getLogger(__name__)


def pid_lock_path() -> str:
    """Return path for PID lock file: /run/user/<uid>/lswitch.pid."""
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    return os.path.join(runtime_dir, "lswitch.pid")


def read_existing_pid() -> int | None:
    """Read PID from lock file. Returns None if file doesn't exist or is invalid."""
    path = pid_lock_path()
    try:
        with open(path) as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return None


def is_process_alive(pid: int) -> bool:
    """Check if a process with given PID is alive."""
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def kill_existing_instance(pid: int) -> bool:
    """Send SIGTERM to existing instance and wait for it to exit."""
    import time

    logger.info("Останавливаю предыдущий экземпляр (PID %d)...", pid)
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return True

    for _ in range(50):
        if not is_process_alive(pid):
            return True
        time.sleep(0.1)

    logger.warning("PID %d не завершился за 5 сек, отправляю SIGKILL", pid)
    try:
        os.kill(pid, signal.SIGKILL)
        time.sleep(0.2)
    except OSError:
        pass
    return not is_process_alive(pid)


class PidLock:
    """Exclusive PID lock using fcntl.flock."""

    def __init__(self, replace: bool = False):
        self._path = pid_lock_path()
        self._fd: int | None = None
        self._replace = replace

    def acquire(self) -> None:
        """Acquire the lock or raise SystemExit if another instance is running."""
        if self._replace:
            existing_pid = read_existing_pid()
            if existing_pid and is_process_alive(existing_pid) and existing_pid != os.getpid():
                if not kill_existing_instance(existing_pid):
                    raise SystemExit(
                        f"Не удалось остановить предыдущий экземпляр (PID {existing_pid}). "
                        f"Остановите его вручную: kill {existing_pid}"
                    )

        self._fd = os.open(self._path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(self._fd)
            self._fd = None
            existing_pid = read_existing_pid()
            msg = (
                f"LSwitch уже запущен (PID {existing_pid}). "
                f"Для замены: lswitch --replace\n"
                f"Для остановки: kill {existing_pid}"
            )
            raise SystemExit(msg)

        os.ftruncate(self._fd, 0)
        os.lseek(self._fd, 0, os.SEEK_SET)
        os.write(self._fd, f"{os.getpid()}\n".encode())

    def release(self) -> None:
        """Release the lock and remove the PID file."""
        if self._fd is not None:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
                os.close(self._fd)
                os.unlink(self._path)
            except OSError:
                pass
            self._fd = None


class SelectionPollerThread(threading.Thread):
    """Background daemon thread polling platform selection changes."""

    def __init__(
        self,
        selection_adapter,
        on_selection_changed=None,
        poll_interval: float = 0.5,
    ):
        super().__init__(daemon=True, name="selection-poller")
        self._selection = selection_adapter
        self._running = True
        self._prev_text: str = ""
        self._prev_owner_id: int = 0
        self._on_selection_changed = on_selection_changed
        self._poll_interval = poll_interval

    def run(self):
        import time

        while self._running:
            try:
                info = self._selection.get_selection()
                text_changed = info.text != self._prev_text
                owner_changed = info.owner_id != self._prev_owner_id
                if text_changed or owner_changed:
                    self._prev_text = info.text
                    self._prev_owner_id = info.owner_id
                    logger.debug(
                        "Selection changed: text=%r owner=0x%x",
                        info.text[:80] if info.text else "",
                        info.owner_id,
                    )
                    if self._on_selection_changed:
                        self._on_selection_changed(info.text, info.owner_id)
            except Exception as exc:
                logger.trace("selection-poller error: %s", exc)  # type: ignore[attr-defined]
            time.sleep(self._poll_interval)

    def stop(self):
        self._running = False


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
class StartedRuntimeResources:
    selection_poller: object | None
    device_count: int


@dataclass(frozen=True)
class QtRuntimeBootstrap:
    qt_app: object | None
    main_thread: object | None


@dataclass(frozen=True)
class RuntimeConfigSnapshot:
    timing: dict
    x11_selection_timing: dict
    wayland_timing: dict
    wayland_selection_timing: dict


@dataclass(frozen=True)
class AppliedRuntimeConfig:
    timing: RuntimeConfigSnapshot
    user_dict: object | None


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


def create_qt_runtime_bootstrap(*, runtime_plan, argv) -> QtRuntimeBootstrap:
    """Create early Qt runtime objects required before platform initialization."""
    if not runtime_plan.requires_qt_before_platform:
        return QtRuntimeBootstrap(qt_app=None, main_thread=None)

    from lswitch.ui.qt_bridge import QtMainThreadInvoker, ensure_qt_application

    qt_app = ensure_qt_application(argv)
    return QtRuntimeBootstrap(
        qt_app=qt_app,
        main_thread=QtMainThreadInvoker(qt_app),
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


def sync_user_dictionary_components(
    *,
    user_dict,
    user_dict_min_weight,
    auto_detector,
    conversion_engine,
    learning_service,
    debug: bool,
    manual_weight_step: int,
) -> None:
    """Propagate user dictionary settings into mutable runtime components."""
    try:
        min_weight = int(user_dict_min_weight)
    except (TypeError, ValueError):
        min_weight = 2

    if auto_detector is not None:
        auto_detector.user_dict = user_dict
        auto_detector.user_dict_min_weight = min_weight
    if conversion_engine is not None:
        conversion_engine.user_dict = user_dict
    if learning_service is not None:
        learning_service.user_dict = user_dict
        learning_service.debug = debug
        learning_service.manual_weight_step = manual_weight_step


def synced_learning_service(
    *,
    user_dict,
    user_dict_min_weight,
    learning_service,
    debug: bool,
    manual_weight_step: int,
):
    """Sync and return the learning service for short-lived use case wiring."""
    sync_user_dictionary_components(
        user_dict=user_dict,
        user_dict_min_weight=user_dict_min_weight,
        auto_detector=None,
        conversion_engine=None,
        learning_service=learning_service,
        debug=debug,
        manual_weight_step=manual_weight_step,
    )
    return learning_service


def read_runtime_config_snapshot(*, config) -> RuntimeConfigSnapshot:
    """Read runtime timing-related config tables without mutating services."""
    return RuntimeConfigSnapshot(
        timing=config.get("timing", {}),
        x11_selection_timing=config.get("x11_selection_timing", {}),
        wayland_timing=config.get("wayland_timing", {}),
        wayland_selection_timing=config.get("wayland_selection_timing", {}),
    )


def apply_runtime_timing_config(
    *,
    config,
    state_manager,
    conversion_engine,
) -> RuntimeConfigSnapshot:
    """Apply runtime timing config and return the current timing tables."""
    snapshot = read_runtime_config_snapshot(config=config)

    state_manager.double_click_timeout = config.get(
        "double_click_timeout",
        state_manager.double_click_timeout,
    )
    if conversion_engine is not None:
        conversion_engine.timing = snapshot.timing

    return snapshot


def apply_user_dictionary_config(
    *,
    config,
    user_dict,
    enable_user_dictionary,
    log,
):
    """Apply runtime user dictionary enable/disable config."""
    if config.get("user_dict_enabled"):
        try:
            return enable_user_dictionary()
        except Exception as exc:
            log.error("User dictionary initialization failed: %s", exc)
            return None

    if user_dict is not None:
        log.info("User dictionary disabled")
    return None


def enable_user_dictionary_if_needed(*, user_dict, log):
    """Return existing or newly-created runtime user dictionary."""
    if user_dict is not None:
        return user_dict

    from lswitch.intelligence.user_dictionary import UserDictionary

    user_dict = UserDictionary()
    log.info("User dictionary enabled: %s", user_dict.path)
    return user_dict


def apply_runtime_config_update(
    *,
    config,
    state_manager,
    conversion_engine,
    user_dict,
    enable_user_dictionary,
    auto_detector,
    learning_service,
    debug: bool,
    manual_weight_step: int,
    log,
) -> AppliedRuntimeConfig:
    """Apply runtime config changes and sync mutable services."""
    timing = apply_runtime_timing_config(
        config=config,
        state_manager=state_manager,
        conversion_engine=conversion_engine,
    )
    user_dict = apply_user_dictionary_config(
        config=config,
        user_dict=user_dict,
        enable_user_dictionary=enable_user_dictionary,
        log=log,
    )
    sync_user_dictionary_components(
        user_dict=user_dict,
        user_dict_min_weight=config.get("user_dict_min_weight", 2),
        auto_detector=auto_detector,
        conversion_engine=conversion_engine,
        learning_service=learning_service,
        debug=debug,
        manual_weight_step=manual_weight_step,
    )
    return AppliedRuntimeConfig(
        timing=timing,
        user_dict=user_dict,
    )


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


def read_mouse_release_selection(*, selection, platform):
    """Read selection after mouse release when platform tracking allows it."""
    if selection is None:
        return None
    if not getattr(
        platform,
        "selection_mouse_release_tracking_enabled",
        True,
    ):
        return None

    from lswitch.platform.selection_adapter import get_passive_selection_reader

    reader = get_passive_selection_reader(selection)
    if reader is not None:
        return reader()
    return selection.get_selection()


def selection_baseline_tracking_enabled(*, platform) -> bool:
    """Return whether passive selection baseline reads are safe/useful."""
    if platform is None:
        return True

    polling = getattr(platform, "selection_polling_enabled", None)
    mouse_release = getattr(
        platform,
        "selection_mouse_release_tracking_enabled",
        None,
    )
    if polling is None and mouse_release is None:
        return True
    return bool(polling or mouse_release)


def update_selection_baseline(*, selection_tracker, selection, platform) -> None:
    """Update passive selection baseline when platform tracking allows it."""
    if selection is None or not selection_baseline_tracking_enabled(platform=platform):
        return

    try:
        from lswitch.platform.selection_adapter import get_passive_selection_reader

        reader = get_passive_selection_reader(selection)
        info = reader() if reader is not None else selection.get_selection()
        selection_tracker.update_baseline(
            info.text or "",
            info.owner_id,
        )
    except Exception:
        pass


def handle_poller_selection_changed(
    *,
    selection_tracker,
    text: str,
    owner_id: int,
    log,
) -> None:
    """Mark selection as fresh after the platform poller reports a change."""
    selection_tracker.on_poller_changed()
    log.debug(
        "Poller: selection changed, fresh=True — text=%r owner=0x%x",
        text[:50] if text else "",
        owner_id,
    )


def set_selection_valid_with_logging(*, selection_tracker, value: bool, log) -> None:
    """Set selection freshness and preserve legacy debug/trace logging."""
    old_value = selection_tracker.valid
    if value != old_value:
        log.debug(
            "fresh=%s → %s",
            old_value,
            value,
        )
    selection_tracker.set_valid(value)

    if log.isEnabledFor(5):  # TRACE = 5
        import traceback as _tb

        caller = _tb.extract_stack(limit=3)[-2]
        log.trace(  # type: ignore[attr-defined]
            "fresh=%s (set by %s:%d)",
            selection_tracker.valid,
            caller.name,
            caller.lineno,
        )


def update_passive_selection_baseline_on_click(
    *,
    selection_tracker,
    selection,
    platform,
    log,
) -> None:
    """Prime baseline on platforms with safe passive selection reads."""
    if platform is None:
        return
    if not getattr(
        platform,
        "selection_mouse_release_tracking_enabled",
        True,
    ):
        return

    from lswitch.platform.selection_adapter import get_passive_selection_reader

    reader = get_passive_selection_reader(selection)
    if reader is None:
        return
    try:
        info = reader()
        result = selection_tracker.on_click_passive_selection(
            info.text or "",
            info.owner_id,
        )
        if result == "initial":
            log.trace(  # type: ignore[attr-defined]
                "MouseClick: initial passive selection baseline — text=%r",
                info.text[:50] if info.text else "",
            )
            return
        if result == "fresh":
            log.debug(
                "MouseClick: fresh passive selection — text=%r owner=0x%x",
                info.text[:50] if info.text else "",
                info.owner_id,
            )
            return
        log.trace(  # type: ignore[attr-defined]
            "MouseClick: passive selection baseline — text=%r",
            info.text[:50] if info.text else "",
        )
    except Exception:
        pass


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


def run_evdev_event_loop(
    *,
    is_running,
    device_manager,
    event_manager,
    timeout: float = 0.1,
) -> None:
    """Run the blocking evdev polling loop until the runtime is stopped."""
    while is_running():
        for device, event in device_manager.get_events(timeout=timeout):
            event_manager.handle_raw_event(event, device.name)


def run_evdev_runtime_until_stopped(
    *,
    is_running,
    device_manager,
    event_manager,
    stop_runtime,
) -> None:
    """Run evdev loop and always stop runtime when it exits."""
    try:
        run_evdev_event_loop(
            is_running=is_running,
            device_manager=device_manager,
            event_manager=event_manager,
        )
    except KeyboardInterrupt:
        pass
    finally:
        stop_runtime()


def create_tray_indicator(
    *,
    event_bus,
    config,
    qt_app,
    owner_app,
    xkb,
):
    """Create and show the Qt tray indicator for the running application."""
    from lswitch.ui.context_menu import ContextMenu
    from lswitch.ui.tray_icon import TrayIcon

    tray = TrayIcon(event_bus=event_bus, config=config, app=qt_app)

    menu_obj = ContextMenu(config=config, event_bus=event_bus, app=owner_app)
    menu = menu_obj.build()
    tray.set_context_menu(menu)

    try:
        current = xkb.get_current_layout() if xkb else None
        tray.set_layout(current.name if current else "")
    except Exception:
        pass

    tray.show()
    return tray


def start_runtime_resources(
    *,
    selection,
    platform,
    x11_selection_timing: dict,
    on_selection_changed,
    device_manager,
    udev_monitor,
    poller_factory=SelectionPollerThread,
) -> StartedRuntimeResources:
    """Start runtime background resources after platform initialization."""
    selection_poller = None
    if selection and getattr(platform, "selection_polling_enabled", False):
        selection_poller = poller_factory(
            selection,
            on_selection_changed=on_selection_changed,
            poll_interval=x11_selection_timing.get("poll_interval", 0.5),
        )
        selection_poller.start()

    device_count = device_manager.scan_devices()

    if udev_monitor:
        udev_monitor.start()

    return StartedRuntimeResources(
        selection_poller=selection_poller,
        device_count=device_count,
    )


def install_reload_signal_handler(
    *,
    config,
    apply_runtime_config,
    debug: bool,
    log,
):
    """Install SIGHUP handler for runtime config reloads."""
    def _reload_handler(signum, frame):
        if config.reload():
            apply_runtime_config()
        if debug:
            log.debug("Config reloaded via SIGHUP")

    signal.signal(signal.SIGHUP, _reload_handler)
    return _reload_handler


def run_qt_runtime_loop(
    *,
    qt_app,
    event_bus,
    show_tray: bool,
    create_tray,
    run_evdev_loop,
    stop_runtime,
    worker_name: str = "evdev-loop",
    join_timeout: float = 2.0,
) -> None:
    """Run Qt event loop while processing evdev events in a worker thread."""
    from lswitch.core.events import EventType
    from PyQt6.QtCore import QTimer

    qt_app.setQuitOnLastWindowClosed(False)

    tray = create_tray() if show_tray else None

    def _on_quit(event):
        qt_app.quit()

    event_bus.subscribe(EventType.APP_QUIT, _on_quit)

    def _evdev_thread():
        try:
            run_evdev_loop()
        except Exception as exc:
            logger.error("Evdev thread error: %s", exc)
        finally:
            qt_app.quit()

    thread = threading.Thread(target=_evdev_thread, daemon=True, name=worker_name)
    thread.start()

    try:
        def sigint_handler(signum, frame):
            logger.info("Получен SIGINT (Ctrl+C). Завершение...")
            qt_app.quit()

        signal.signal(signal.SIGINT, sigint_handler)

        # Keep Python signal handling responsive while Qt owns the main loop.
        timer = QTimer()
        timer.timeout.connect(lambda: None)
        timer.start(500)

        qt_app.exec()
    finally:
        if tray is not None:
            tray.cleanup()
        stop_runtime()
        thread.join(timeout=join_timeout)


def run_qt_app_runtime(
    *,
    qt_app,
    event_bus,
    show_tray: bool,
    config,
    owner_app,
    xkb,
    is_running,
    device_manager,
    event_manager,
    stop_runtime,
) -> None:
    """Run full Qt runtime using app-owned adapters and lifecycle callbacks."""
    run_qt_runtime_loop(
        qt_app=qt_app,
        event_bus=event_bus,
        show_tray=show_tray,
        create_tray=(
            lambda: create_tray_indicator(
                event_bus=event_bus,
                config=config,
                qt_app=qt_app,
                owner_app=owner_app,
                xkb=xkb,
            )
        ),
        run_evdev_loop=(
            lambda: run_evdev_event_loop(
                is_running=is_running,
                device_manager=device_manager,
                event_manager=event_manager,
            )
        ),
        stop_runtime=stop_runtime,
    )


def run_selected_runtime_loop(
    *,
    runtime_plan,
    headless: bool,
    qt_app,
    argv,
    run_qt_loop,
    run_evdev_loop,
    ensure_qt_application=None,
) -> None:
    """Run the event loop selected by the current platform runtime plan."""
    if runtime_plan.uses_qt_event_loop:
        if qt_app is None:
            if ensure_qt_application is None:
                from lswitch.ui.qt_bridge import ensure_qt_application
            qt_app = ensure_qt_application(argv)
        run_qt_loop(qt_app, show_tray=runtime_plan.show_tray)
    elif headless:
        run_evdev_loop()
    else:
        if ensure_qt_application is None:
            from lswitch.ui.qt_bridge import ensure_qt_application
        run_qt_loop(ensure_qt_application(argv), show_tray=True)


def stop_runtime_resources(
    *,
    selection_poller,
    udev_monitor,
    device_manager,
    virtual_kb,
    xkb,
    pid_lock,
):
    """Stop runtime-owned resources and return the remaining PID lock state."""
    if selection_poller:
        selection_poller.stop()
    if udev_monitor:
        try:
            udev_monitor.stop()
        except Exception:
            pass
    if device_manager:
        try:
            device_manager.close()
        except Exception:
            pass
    if virtual_kb:
        try:
            virtual_kb.close()
        except Exception:
            pass
    if xkb and hasattr(xkb, "close"):
        try:
            xkb.close()
        except Exception:
            pass
    if pid_lock:
        pid_lock.release()
        return None
    return pid_lock
