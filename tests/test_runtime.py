"""Tests for runtime component factories."""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

from lswitch.core.event_bus import EventBus
from lswitch.core.event_manager import EventManager
from lswitch.core.events import Event, EventType, KeyEventData
from lswitch.core.conversion_engine import ConversionEngine
from lswitch.core.input_router import InputEventRouter
from lswitch.core.learning_service import LearningService
from lswitch.core.selection_tracker import SelectionFreshnessTracker
from lswitch.core.state_manager import StateManager
from lswitch.core.typed_buffer import TypedBufferService
from lswitch.runtime import (
    ConversionRuntimeComponents,
    InputDeviceRuntimeComponents,
    PidLock,
    PlatformRuntimeComponents,
    QtRuntimeBootstrap,
    RuntimeCoreComponents,
    SelectionPollerThread,
    StartedRuntimeResources,
    create_conversion_runtime,
    create_core_components,
    create_input_device_runtime,
    create_input_router,
    create_platform_runtime_components,
    create_qt_runtime_bootstrap,
    create_tray_indicator,
    install_reload_signal_handler,
    run_evdev_event_loop,
    run_qt_runtime_loop,
    run_selected_runtime_loop,
    is_process_alive,
    kill_existing_instance,
    pid_lock_path,
    read_existing_pid,
    start_runtime_resources,
    stop_runtime_resources,
    sync_user_dictionary_components,
    wire_runtime_event_bus,
)


def test_create_core_components_builds_core_runtime_services():
    components = create_core_components(
        double_click_timeout=0.75,
        debug=True,
        manual_weight_step=3,
    )

    assert isinstance(components, RuntimeCoreComponents)
    assert isinstance(components.event_bus, EventBus)
    assert isinstance(components.state_manager, StateManager)
    assert isinstance(components.typed_buffer, TypedBufferService)
    assert isinstance(components.selection_tracker, SelectionFreshnessTracker)
    assert isinstance(components.learning_service, LearningService)
    assert components.state_manager.double_click_timeout == 0.75
    assert components.learning_service.debug is True
    assert components.learning_service.manual_weight_step == 3
    assert components.learning_service.user_dict is None


def test_pid_lock_path_uses_xdg_runtime_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))

    assert pid_lock_path() == str(tmp_path / "lswitch.pid")


def test_read_existing_pid_handles_missing_invalid_and_valid_values(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    path = tmp_path / "lswitch.pid"

    assert read_existing_pid() is None

    path.write_text("not-a-pid")
    assert read_existing_pid() is None

    path.write_text("123\n")
    assert read_existing_pid() == 123


def test_is_process_alive_uses_signal_zero(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "lswitch.runtime.os.kill",
        lambda pid, sig: calls.append((pid, sig)),
    )

    assert is_process_alive(123) is True
    assert calls == [(123, 0)]


def test_is_process_alive_returns_false_on_os_error(monkeypatch):
    def fail(pid, sig):
        raise OSError("missing")

    monkeypatch.setattr("lswitch.runtime.os.kill", fail)

    assert is_process_alive(123) is False


def test_kill_existing_instance_returns_true_when_process_exits(monkeypatch):
    kill_calls = []
    alive_results = iter([True, False])
    monkeypatch.setattr(
        "lswitch.runtime.os.kill",
        lambda pid, sig: kill_calls.append((pid, sig)),
    )
    monkeypatch.setattr(
        "lswitch.runtime.is_process_alive",
        lambda pid: next(alive_results),
    )
    monkeypatch.setattr("time.sleep", lambda seconds: None)

    assert kill_existing_instance(123) is True
    assert kill_calls == [(123, __import__("signal").SIGTERM)]


def test_pid_lock_acquire_writes_pid_and_release_removes_file(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))

    lock = PidLock()
    lock.acquire()

    path = tmp_path / "lswitch.pid"
    assert path.read_text() == f"{__import__('os').getpid()}\n"

    lock.release()

    assert not path.exists()
    assert lock._fd is None


def test_pid_lock_acquire_raises_when_lock_is_held(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    first_lock = PidLock()
    first_lock.acquire()

    try:
        second_lock = PidLock()
        try:
            second_lock.acquire()
        except SystemExit as exc:
            assert "LSwitch уже запущен" in str(exc)
        else:
            raise AssertionError("expected lock contention to raise SystemExit")
    finally:
        first_lock.release()


def test_create_qt_runtime_bootstrap_is_noop_when_qt_is_not_required():
    result = create_qt_runtime_bootstrap(
        runtime_plan=types.SimpleNamespace(requires_qt_before_platform=False),
        argv=["lswitch"],
    )

    assert isinstance(result, QtRuntimeBootstrap)
    assert result.qt_app is None
    assert result.main_thread is None


def test_create_qt_runtime_bootstrap_creates_qt_app_and_main_thread(monkeypatch):
    qt_app = object()
    created = {}

    class FakeQtMainThreadInvoker:
        def __init__(self, app):
            self.app = app
            created["main_thread"] = self

    qt_bridge_module = types.ModuleType("lswitch.ui.qt_bridge")
    qt_bridge_module.ensure_qt_application = MagicMock(return_value=qt_app)
    qt_bridge_module.QtMainThreadInvoker = FakeQtMainThreadInvoker
    monkeypatch.setitem(sys.modules, "lswitch.ui.qt_bridge", qt_bridge_module)

    argv = ["lswitch", "--gui"]

    result = create_qt_runtime_bootstrap(
        runtime_plan=types.SimpleNamespace(requires_qt_before_platform=True),
        argv=argv,
    )

    assert result.qt_app is qt_app
    assert result.main_thread is created["main_thread"]
    assert result.main_thread.app is qt_app
    qt_bridge_module.ensure_qt_application.assert_called_once_with(argv)


def test_create_input_router_wires_core_components_and_callbacks():
    core = create_core_components(
        double_click_timeout=0.3,
        debug=False,
        manual_weight_step=2,
    )
    set_pending_auto_space = MagicMock()
    clear_last_retype_events = MagicMock()

    router = create_input_router(
        core=core,
        decode_buffer=lambda: "",
        auto_conversion_enabled=lambda: False,
        try_auto_conversion_at_space=lambda: False,
        get_pending_auto_space=lambda: True,
        set_pending_auto_space=set_pending_auto_space,
        clear_last_retype_events=clear_last_retype_events,
        clear_last_auto_marker=lambda: None,
        inject_deferred_space=lambda: None,
        request_conversion=lambda: None,
        prime_selection_baseline_on_click=lambda: None,
        read_mouse_release_selection=lambda: None,
    )

    assert isinstance(router, InputEventRouter)
    event = Event(
        EventType.KEY_PRESS,
        KeyEventData(code=30, value=1, device_name="test"),
        0.0,
    )
    router.on_key_press(event)

    assert core.state_manager.context.chars_in_buffer == 1
    assert core.typed_buffer.decode(core.state_manager.context.event_buffer) == "a"
    set_pending_auto_space.assert_called_once_with(False)
    clear_last_retype_events.assert_called_once()


def test_wire_runtime_event_bus_subscribes_input_router_and_config_handlers():
    event_bus = EventBus()
    input_router = MagicMock()
    on_config_changed = MagicMock()

    wire_runtime_event_bus(
        event_bus=event_bus,
        input_router=input_router,
        on_config_changed=on_config_changed,
    )

    assert input_router.on_key_press in event_bus._handlers[EventType.KEY_PRESS]
    assert input_router.on_key_release in event_bus._handlers[EventType.KEY_RELEASE]
    assert input_router.on_key_repeat in event_bus._handlers[EventType.KEY_REPEAT]
    assert input_router.on_mouse_click in event_bus._handlers[EventType.MOUSE_CLICK]
    assert input_router.on_mouse_release in event_bus._handlers[EventType.MOUSE_RELEASE]
    assert on_config_changed in event_bus._handlers[EventType.CONFIG_CHANGED]


def test_sync_user_dictionary_components_updates_mutable_runtime_services():
    user_dict = object()
    auto_detector = MagicMock()
    conversion_engine = MagicMock()
    learning_service = MagicMock()

    sync_user_dictionary_components(
        user_dict=user_dict,
        user_dict_min_weight="5",
        auto_detector=auto_detector,
        conversion_engine=conversion_engine,
        learning_service=learning_service,
        debug=True,
        manual_weight_step=3,
    )

    assert auto_detector.user_dict is user_dict
    assert auto_detector.user_dict_min_weight == 5
    assert conversion_engine.user_dict is user_dict
    assert learning_service.user_dict is user_dict
    assert learning_service.debug is True
    assert learning_service.manual_weight_step == 3


def test_sync_user_dictionary_components_falls_back_to_default_min_weight():
    auto_detector = MagicMock()

    sync_user_dictionary_components(
        user_dict=None,
        user_dict_min_weight="bad",
        auto_detector=auto_detector,
        conversion_engine=None,
        learning_service=None,
        debug=False,
        manual_weight_step=2,
    )

    assert auto_detector.user_dict is None
    assert auto_detector.user_dict_min_weight == 2


def test_create_conversion_runtime_wires_detector_and_engine():
    user_dict = MagicMock()
    xkb = MagicMock()
    selection = MagicMock()
    virtual_kb = MagicMock()
    system = MagicMock()
    timing = {"retype_before_replay_delay": 0.01}

    components = create_conversion_runtime(
        xkb=xkb,
        selection=selection,
        virtual_kb=virtual_kb,
        system=system,
        user_dict=user_dict,
        user_dict_min_weight=4,
        debug=True,
        timing=timing,
    )

    assert isinstance(components, ConversionRuntimeComponents)
    assert isinstance(components.conversion_engine, ConversionEngine)
    assert components.auto_detector.dictionary is components.dictionary
    assert components.auto_detector.ngrams is components.ngrams
    assert components.auto_detector.user_dict is user_dict
    assert components.auto_detector.user_dict_min_weight == 4
    assert components.conversion_engine.dictionary is components.dictionary
    assert components.conversion_engine.xkb is xkb
    assert components.conversion_engine.selection is selection
    assert components.conversion_engine.virtual_kb is virtual_kb
    assert components.conversion_engine.system is system
    assert components.conversion_engine.user_dict is user_dict
    assert components.conversion_engine.debug is True
    assert components.conversion_engine.timing is timing


def test_create_input_device_runtime_wires_device_services():
    fake_evdev = types.ModuleType("evdev")
    fake_ecodes = types.ModuleType("evdev.ecodes")
    fake_ecodes.EV_KEY = 1
    fake_ecodes.KEY_A = 30
    fake_ecodes.BTN_LEFT = 0x110
    fake_ecodes.BTN_RIGHT = 0x111
    fake_evdev.ecodes = fake_ecodes
    fake_evdev.InputDevice = MagicMock
    fake_evdev.list_devices = MagicMock(return_value=[])
    sys.modules.setdefault("evdev", fake_evdev)
    sys.modules.setdefault("evdev.ecodes", fake_ecodes)

    fake_pyudev = types.ModuleType("pyudev")
    fake_pyudev.Context = MagicMock
    fake_pyudev.Monitor = MagicMock()
    sys.modules.setdefault("pyudev", fake_pyudev)

    from lswitch.input.device_manager import DeviceManager
    from lswitch.input.udev_monitor import UdevMonitor
    from lswitch.input.virtual_keyboard import VirtualKeyboard

    event_bus = EventBus()
    virtual_kb = object()

    components = create_input_device_runtime(
        event_bus=event_bus,
        virtual_kb=virtual_kb,
        debug=True,
    )

    assert isinstance(components, InputDeviceRuntimeComponents)
    assert isinstance(components.event_manager, EventManager)
    assert isinstance(components.device_manager, DeviceManager)
    assert isinstance(components.udev_monitor, UdevMonitor)
    assert components.event_manager.bus is event_bus
    assert components.event_manager.debug is True
    assert components.device_manager.debug is True
    assert components.device_manager._virtual_kb_name == VirtualKeyboard.DEVICE_NAME
    assert components.udev_monitor.on_added.__self__ is components.device_manager
    assert (
        components.udev_monitor.on_added.__func__
        is components.device_manager._try_add_device.__func__
    )


def test_create_input_device_runtime_leaves_virtual_keyboard_name_unset_without_keyboard():
    components = create_input_device_runtime(
        event_bus=EventBus(),
        virtual_kb=None,
        debug=False,
    )

    assert components.device_manager._virtual_kb_name is None


def test_create_platform_runtime_components_wires_platform_conversion_and_input(monkeypatch):
    platform = types.SimpleNamespace(
        system=object(),
        xkb=object(),
        selection=object(),
        virtual_kb=object(),
    )
    conversion = ConversionRuntimeComponents(
        dictionary=object(),
        ngrams=object(),
        auto_detector=object(),
        conversion_engine=object(),
    )
    input_devices = InputDeviceRuntimeComponents(
        event_manager=object(),
        device_manager=object(),
        udev_monitor=object(),
    )
    create_platform_adapters = MagicMock(return_value=platform)
    create_conversion = MagicMock(return_value=conversion)
    create_input = MagicMock(return_value=input_devices)
    monkeypatch.setattr(
        "lswitch.platform.platform_factory.create_platform_adapters",
        create_platform_adapters,
    )
    monkeypatch.setattr("lswitch.runtime.create_conversion_runtime", create_conversion)
    monkeypatch.setattr("lswitch.runtime.create_input_device_runtime", create_input)
    event_bus = EventBus()
    user_dict = object()
    timing = {"a": 1}
    x11_selection_timing = {"b": 2}
    wayland_timing = {"c": 3}
    wayland_selection_timing = {"d": 4}
    main_thread = object()

    components = create_platform_runtime_components(
        debug=True,
        main_thread=main_thread,
        wayland_selection_strategy="primary",
        timing=timing,
        x11_selection_timing=x11_selection_timing,
        wayland_timing=wayland_timing,
        wayland_selection_timing=wayland_selection_timing,
        event_bus=event_bus,
        user_dict=user_dict,
        user_dict_min_weight=7,
    )

    assert isinstance(components, PlatformRuntimeComponents)
    assert components.platform is platform
    assert components.conversion is conversion
    assert components.input_devices is input_devices
    create_platform_adapters.assert_called_once_with(
        debug=True,
        main_thread=main_thread,
        wayland_selection_strategy="primary",
        timing=timing,
        x11_selection_timing=x11_selection_timing,
        wayland_timing=wayland_timing,
        wayland_selection_timing=wayland_selection_timing,
    )
    create_conversion.assert_called_once_with(
        xkb=platform.xkb,
        selection=platform.selection,
        virtual_kb=platform.virtual_kb,
        system=platform.system,
        user_dict=user_dict,
        user_dict_min_weight=7,
        debug=True,
        timing=timing,
    )
    create_input.assert_called_once_with(
        event_bus=event_bus,
        virtual_kb=platform.virtual_kb,
        debug=True,
    )


def test_selection_poller_thread_initializes_and_stops():
    selection = MagicMock()
    callback = MagicMock()

    poller = SelectionPollerThread(
        selection,
        on_selection_changed=callback,
        poll_interval=0.25,
    )

    assert poller.daemon is True
    assert poller.name == "selection-poller"
    assert poller._selection is selection
    assert poller._on_selection_changed is callback
    assert poller._poll_interval == 0.25
    assert poller._running is True

    poller.stop()

    assert poller._running is False


def test_start_runtime_resources_starts_poller_scans_devices_and_starts_udev():
    created_pollers = []

    class FakePoller:
        def __init__(self, selection, on_selection_changed, poll_interval):
            self.selection = selection
            self.on_selection_changed = on_selection_changed
            self.poll_interval = poll_interval
            self.started = False
            created_pollers.append(self)

        def start(self):
            self.started = True

    device_manager = MagicMock()
    device_manager.scan_devices.return_value = 3
    udev_monitor = MagicMock()
    callback = MagicMock()
    selection = object()

    result = start_runtime_resources(
        selection=selection,
        platform=types.SimpleNamespace(selection_polling_enabled=True),
        x11_selection_timing={"poll_interval": 0.25},
        on_selection_changed=callback,
        device_manager=device_manager,
        udev_monitor=udev_monitor,
        poller_factory=FakePoller,
    )

    assert isinstance(result, StartedRuntimeResources)
    assert result.selection_poller is created_pollers[0]
    assert result.device_count == 3
    assert created_pollers[0].selection is selection
    assert created_pollers[0].on_selection_changed is callback
    assert created_pollers[0].poll_interval == 0.25
    assert created_pollers[0].started is True
    device_manager.scan_devices.assert_called_once_with()
    udev_monitor.start.assert_called_once_with()


def test_start_runtime_resources_skips_poller_and_udev_when_disabled_or_missing():
    device_manager = MagicMock()
    device_manager.scan_devices.return_value = 0
    poller_factory = MagicMock()

    result = start_runtime_resources(
        selection=object(),
        platform=types.SimpleNamespace(selection_polling_enabled=False),
        x11_selection_timing={},
        on_selection_changed=MagicMock(),
        device_manager=device_manager,
        udev_monitor=None,
        poller_factory=poller_factory,
    )

    assert result.selection_poller is None
    assert result.device_count == 0
    poller_factory.assert_not_called()
    device_manager.scan_devices.assert_called_once_with()


def test_install_reload_signal_handler_applies_runtime_config_when_reload_succeeds(monkeypatch):
    registered = {}
    monkeypatch.setattr(
        "lswitch.runtime.signal.signal",
        lambda signum, handler: registered.update({signum: handler}),
    )
    config = MagicMock()
    config.reload.return_value = True
    apply_runtime_config = MagicMock()
    log = MagicMock()

    handler = install_reload_signal_handler(
        config=config,
        apply_runtime_config=apply_runtime_config,
        debug=True,
        log=log,
    )

    assert registered[__import__("signal").SIGHUP] is handler

    handler(None, None)

    config.reload.assert_called_once_with()
    apply_runtime_config.assert_called_once_with()
    log.debug.assert_called_once_with("Config reloaded via SIGHUP")


def test_install_reload_signal_handler_skips_apply_when_reload_is_unchanged(monkeypatch):
    monkeypatch.setattr("lswitch.runtime.signal.signal", lambda signum, handler: None)
    config = MagicMock()
    config.reload.return_value = False
    apply_runtime_config = MagicMock()
    log = MagicMock()

    handler = install_reload_signal_handler(
        config=config,
        apply_runtime_config=apply_runtime_config,
        debug=False,
        log=log,
    )

    handler(None, None)

    config.reload.assert_called_once_with()
    apply_runtime_config.assert_not_called()
    log.debug.assert_not_called()


def test_run_evdev_event_loop_dispatches_events_until_stopped():
    device = types.SimpleNamespace(name="keyboard")
    event = object()
    state = {"running": True}
    event_manager = MagicMock()

    class DeviceManager:
        def get_events(self, timeout):
            assert timeout == 0.25
            state["running"] = False
            return [(device, event)]

    run_evdev_event_loop(
        is_running=lambda: state["running"],
        device_manager=DeviceManager(),
        event_manager=event_manager,
        timeout=0.25,
    )

    event_manager.handle_raw_event.assert_called_once_with(event, "keyboard")


def test_run_evdev_event_loop_propagates_polling_errors():
    class DeviceManager:
        def get_events(self, timeout):
            raise RuntimeError("poll failed")

    try:
        run_evdev_event_loop(
            is_running=lambda: True,
            device_manager=DeviceManager(),
            event_manager=MagicMock(),
        )
    except RuntimeError as exc:
        assert str(exc) == "poll failed"
    else:
        raise AssertionError("expected polling error")


def test_create_tray_indicator_builds_context_menu_sets_layout_and_shows(monkeypatch):
    created = {}
    menu = object()

    class FakeTrayIcon:
        def __init__(self, *, event_bus, config, app):
            self.event_bus = event_bus
            self.config = config
            self.app = app
            self.context_menu = None
            self.layout_name = None
            self.shown = False
            created["tray"] = self

        def set_context_menu(self, value):
            self.context_menu = value

        def set_layout(self, value):
            self.layout_name = value

        def show(self):
            self.shown = True

    class FakeContextMenu:
        def __init__(self, *, config, event_bus, app):
            self.config = config
            self.event_bus = event_bus
            self.app = app
            created["menu_builder"] = self

        def build(self):
            return menu

    tray_module = types.ModuleType("lswitch.ui.tray_icon")
    tray_module.TrayIcon = FakeTrayIcon
    menu_module = types.ModuleType("lswitch.ui.context_menu")
    menu_module.ContextMenu = FakeContextMenu
    monkeypatch.setitem(sys.modules, "lswitch.ui.tray_icon", tray_module)
    monkeypatch.setitem(sys.modules, "lswitch.ui.context_menu", menu_module)

    event_bus = object()
    config = object()
    qt_app = object()
    owner_app = object()
    xkb = MagicMock()
    xkb.get_current_layout.return_value = types.SimpleNamespace(name="ru")

    tray = create_tray_indicator(
        event_bus=event_bus,
        config=config,
        qt_app=qt_app,
        owner_app=owner_app,
        xkb=xkb,
    )

    assert tray is created["tray"]
    assert tray.event_bus is event_bus
    assert tray.config is config
    assert tray.app is qt_app
    assert tray.context_menu is menu
    assert tray.layout_name == "ru"
    assert tray.shown is True
    assert created["menu_builder"].config is config
    assert created["menu_builder"].event_bus is event_bus
    assert created["menu_builder"].app is owner_app


def test_create_tray_indicator_tolerates_layout_lookup_errors(monkeypatch):
    class FakeTrayIcon:
        def __init__(self, **kwargs):
            self.layout_name = None
            self.shown = False

        def set_context_menu(self, value):
            pass

        def set_layout(self, value):
            self.layout_name = value

        def show(self):
            self.shown = True

    class FakeContextMenu:
        def __init__(self, **kwargs):
            pass

        def build(self):
            return object()

    tray_module = types.ModuleType("lswitch.ui.tray_icon")
    tray_module.TrayIcon = FakeTrayIcon
    menu_module = types.ModuleType("lswitch.ui.context_menu")
    menu_module.ContextMenu = FakeContextMenu
    monkeypatch.setitem(sys.modules, "lswitch.ui.tray_icon", tray_module)
    monkeypatch.setitem(sys.modules, "lswitch.ui.context_menu", menu_module)

    xkb = MagicMock()
    xkb.get_current_layout.side_effect = RuntimeError("layout unavailable")

    tray = create_tray_indicator(
        event_bus=object(),
        config=object(),
        qt_app=object(),
        owner_app=object(),
        xkb=xkb,
    )

    assert tray.layout_name is None
    assert tray.shown is True


def test_run_qt_runtime_loop_wires_worker_signal_timer_cleanup_and_stop(monkeypatch):
    created_timers = []

    class FakeSignal:
        def __init__(self):
            self.callback = None

        def connect(self, callback):
            self.callback = callback

    class FakeQTimer:
        def __init__(self):
            self.timeout = FakeSignal()
            self.started_with = None
            created_timers.append(self)

        def start(self, interval):
            self.started_with = interval

    qtcore_module = types.ModuleType("PyQt6.QtCore")
    qtcore_module.QTimer = FakeQTimer
    pyqt_module = types.ModuleType("PyQt6")
    pyqt_module.QtCore = qtcore_module
    monkeypatch.setitem(sys.modules, "PyQt6", pyqt_module)
    monkeypatch.setitem(sys.modules, "PyQt6.QtCore", qtcore_module)

    signal_calls = []
    monkeypatch.setattr(
        "lswitch.runtime.signal.signal",
        lambda signum, handler: signal_calls.append((signum, handler)),
    )

    class FakeQtApp:
        def __init__(self):
            self.quit_on_last_window_closed = None
            self.quit_calls = 0
            self.exec_calls = 0

        def setQuitOnLastWindowClosed(self, value):
            self.quit_on_last_window_closed = value

        def quit(self):
            self.quit_calls += 1

        def exec(self):
            self.exec_calls += 1

    class FakeEventBus:
        def __init__(self):
            self.subscriptions = []

        def subscribe(self, event_type, callback):
            self.subscriptions.append((event_type, callback))

    class FakeTray:
        def __init__(self):
            self.cleaned = False

        def cleanup(self):
            self.cleaned = True

    qt_app = FakeQtApp()
    event_bus = FakeEventBus()
    tray = FakeTray()
    calls = []

    run_qt_runtime_loop(
        qt_app=qt_app,
        event_bus=event_bus,
        show_tray=True,
        create_tray=lambda: tray,
        run_evdev_loop=lambda: calls.append("evdev"),
        stop_runtime=lambda: calls.append("stop"),
        join_timeout=1.0,
    )

    assert qt_app.quit_on_last_window_closed is False
    assert qt_app.exec_calls == 1
    assert qt_app.quit_calls == 1
    assert event_bus.subscriptions[0][0] is EventType.APP_QUIT
    assert signal_calls[0][0] == __import__("signal").SIGINT
    assert created_timers[0].timeout.callback is not None
    assert created_timers[0].started_with == 500
    assert tray.cleaned is True
    assert calls == ["evdev", "stop"]


def test_run_qt_runtime_loop_skips_tray_when_disabled(monkeypatch):
    class FakeQTimer:
        class Timeout:
            def connect(self, callback):
                pass

        def __init__(self):
            self.timeout = self.Timeout()

        def start(self, interval):
            pass

    qtcore_module = types.ModuleType("PyQt6.QtCore")
    qtcore_module.QTimer = FakeQTimer
    pyqt_module = types.ModuleType("PyQt6")
    pyqt_module.QtCore = qtcore_module
    monkeypatch.setitem(sys.modules, "PyQt6", pyqt_module)
    monkeypatch.setitem(sys.modules, "PyQt6.QtCore", qtcore_module)
    monkeypatch.setattr("lswitch.runtime.signal.signal", lambda signum, handler: None)

    qt_app = MagicMock()
    event_bus = MagicMock()
    create_tray = MagicMock()

    run_qt_runtime_loop(
        qt_app=qt_app,
        event_bus=event_bus,
        show_tray=False,
        create_tray=create_tray,
        run_evdev_loop=lambda: None,
        stop_runtime=lambda: None,
    )

    create_tray.assert_not_called()
    qt_app.setQuitOnLastWindowClosed.assert_called_once_with(False)
    qt_app.exec.assert_called_once_with()


def test_run_selected_runtime_loop_uses_existing_qt_app_for_qt_plan():
    qt_app = object()
    run_qt_loop = MagicMock()
    run_evdev_loop = MagicMock()
    ensure_qt_application = MagicMock()

    run_selected_runtime_loop(
        runtime_plan=types.SimpleNamespace(
            uses_qt_event_loop=True,
            show_tray=False,
        ),
        headless=False,
        qt_app=qt_app,
        argv=["lswitch"],
        run_qt_loop=run_qt_loop,
        run_evdev_loop=run_evdev_loop,
        ensure_qt_application=ensure_qt_application,
    )

    run_qt_loop.assert_called_once_with(qt_app, show_tray=False)
    run_evdev_loop.assert_not_called()
    ensure_qt_application.assert_not_called()


def test_run_selected_runtime_loop_runs_headless_evdev_loop():
    run_qt_loop = MagicMock()
    run_evdev_loop = MagicMock()
    ensure_qt_application = MagicMock()

    run_selected_runtime_loop(
        runtime_plan=types.SimpleNamespace(
            uses_qt_event_loop=False,
            show_tray=False,
        ),
        headless=True,
        qt_app=None,
        argv=["lswitch", "--headless"],
        run_qt_loop=run_qt_loop,
        run_evdev_loop=run_evdev_loop,
        ensure_qt_application=ensure_qt_application,
    )

    run_evdev_loop.assert_called_once_with()
    run_qt_loop.assert_not_called()
    ensure_qt_application.assert_not_called()


def test_run_selected_runtime_loop_creates_qt_app_for_gui_fallback():
    qt_app = object()
    run_qt_loop = MagicMock()
    run_evdev_loop = MagicMock()
    ensure_qt_application = MagicMock(return_value=qt_app)
    argv = ["lswitch"]

    run_selected_runtime_loop(
        runtime_plan=types.SimpleNamespace(
            uses_qt_event_loop=False,
            show_tray=False,
        ),
        headless=False,
        qt_app=None,
        argv=argv,
        run_qt_loop=run_qt_loop,
        run_evdev_loop=run_evdev_loop,
        ensure_qt_application=ensure_qt_application,
    )

    ensure_qt_application.assert_called_once_with(argv)
    run_qt_loop.assert_called_once_with(qt_app, show_tray=True)
    run_evdev_loop.assert_not_called()


def test_run_selected_runtime_loop_creates_qt_app_when_qt_plan_has_no_bootstrap_app():
    qt_app = object()
    run_qt_loop = MagicMock()
    ensure_qt_application = MagicMock(return_value=qt_app)
    argv = ["lswitch"]

    run_selected_runtime_loop(
        runtime_plan=types.SimpleNamespace(
            uses_qt_event_loop=True,
            show_tray=True,
        ),
        headless=True,
        qt_app=None,
        argv=argv,
        run_qt_loop=run_qt_loop,
        run_evdev_loop=MagicMock(),
        ensure_qt_application=ensure_qt_application,
    )

    ensure_qt_application.assert_called_once_with(argv)
    run_qt_loop.assert_called_once_with(qt_app, show_tray=True)


def test_stop_runtime_resources_stops_owned_resources_and_releases_pid_lock():
    selection_poller = MagicMock()
    udev_monitor = MagicMock()
    device_manager = MagicMock()
    virtual_kb = MagicMock()
    xkb = MagicMock()
    pid_lock = MagicMock()

    next_pid_lock = stop_runtime_resources(
        selection_poller=selection_poller,
        udev_monitor=udev_monitor,
        device_manager=device_manager,
        virtual_kb=virtual_kb,
        xkb=xkb,
        pid_lock=pid_lock,
    )

    assert next_pid_lock is None
    selection_poller.stop.assert_called_once_with()
    udev_monitor.stop.assert_called_once_with()
    device_manager.close.assert_called_once_with()
    virtual_kb.close.assert_called_once_with()
    xkb.close.assert_called_once_with()
    pid_lock.release.assert_called_once_with()


def test_stop_runtime_resources_preserves_shutdown_error_tolerance():
    selection_poller = MagicMock()
    udev_monitor = MagicMock()
    device_manager = MagicMock()
    virtual_kb = MagicMock()
    xkb = MagicMock()
    pid_lock = MagicMock()
    udev_monitor.stop.side_effect = RuntimeError("udev")
    device_manager.close.side_effect = RuntimeError("devices")
    virtual_kb.close.side_effect = RuntimeError("keyboard")
    xkb.close.side_effect = RuntimeError("xkb")

    next_pid_lock = stop_runtime_resources(
        selection_poller=selection_poller,
        udev_monitor=udev_monitor,
        device_manager=device_manager,
        virtual_kb=virtual_kb,
        xkb=xkb,
        pid_lock=pid_lock,
    )

    assert next_pid_lock is None
    selection_poller.stop.assert_called_once_with()
    udev_monitor.stop.assert_called_once_with()
    device_manager.close.assert_called_once_with()
    virtual_kb.close.assert_called_once_with()
    xkb.close.assert_called_once_with()
    pid_lock.release.assert_called_once_with()


def test_stop_runtime_resources_handles_missing_optional_resources():
    xkb_without_close = object()

    next_pid_lock = stop_runtime_resources(
        selection_poller=None,
        udev_monitor=None,
        device_manager=None,
        virtual_kb=None,
        xkb=xkb_without_close,
        pid_lock=None,
    )

    assert next_pid_lock is None
