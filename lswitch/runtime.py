"""Runtime component factories."""

import fcntl
import logging
import os
import signal
import threading
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
class StartedRuntimeResources:
    selection_poller: object | None
    device_count: int


@dataclass(frozen=True)
class QtRuntimeBootstrap:
    qt_app: object | None
    main_thread: object | None


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
