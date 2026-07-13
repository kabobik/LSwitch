"""Tests for runtime component factories."""

from __future__ import annotations

import sys
import types
import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import lswitch.runtime as runtime_module
import lswitch.runtime_conversion as runtime_conversion_module
from lswitch.core.event_bus import EventBus
from lswitch.core.auto_conversion_session import AutoConversionSessionState
from lswitch.core.event_manager import EventManager
from lswitch.core.events import Event, EventType, KeyEventData
from lswitch.core.conversion_engine import ConversionEngine
from lswitch.core.input_router import (
    InputConversionPort,
    InputEventRouter,
    InputSelectionPort,
)
from lswitch.core.learning_service import LearningService
from lswitch.core.selection_tracker import SelectionFreshnessTracker
from lswitch.core.state_manager import StateManager
from lswitch.core.typed_buffer import TypedBufferService
from lswitch.intelligence.system_dictionary_loader import SystemDictionaryStatus
from lswitch.runtime import (
    AppliedRuntimeConfig,
    ConversionRuntimeFacade,
    ConversionRuntimeComponents,
    InputDeviceRuntimeComponents,
    InputRouterCallbacks,
    MidWordDetectionRuntime,
    PidLock,
    PlatformRuntimeComponents,
    QtRuntimeBootstrap,
    RuntimeConfigSnapshot,
    RuntimeLoggingController,
    RuntimeCoreComponents,
    SelectionPollerThread,
    SpaceAutoConversionState,
    StartedRuntimeResources,
    apply_runtime_config_update,
    apply_platform_runtime_config,
    apply_runtime_timing_config,
    apply_space_auto_conversion_result,
    apply_user_dictionary_config,
    auto_conversion_enabled,
    mid_word_auto_conversion_enabled,
    create_conversion_runtime,
    create_core_components,
    create_input_device_runtime,
    create_input_router,
    create_input_router_callbacks,
    create_mid_word_detection_runtime,
    create_mid_word_auto_conversion_use_case,
    create_manual_conversion_controller,
    create_platform_runtime_components,
    create_qt_runtime_bootstrap,
    create_space_auto_conversion_use_case,
    create_synced_manual_conversion_controller,
    create_synced_space_auto_conversion_use_case,
    create_tray_indicator,
    decode_buffer_events,
    enable_user_dictionary_if_needed,
    execute_manual_conversion_with_session,
    extract_last_word_events,
    handle_poller_selection_changed,
    inject_deferred_space,
    install_reload_signal_handler,
    perform_space_auto_conversion_at_boundary,
    read_mouse_release_selection,
    read_runtime_config_snapshot,
    run_evdev_event_loop,
    run_qt_app_runtime,
    run_qt_runtime_loop,
    selection_baseline_tracking_enabled,
    is_process_alive,
    kill_existing_instance,
    pid_lock_path,
    read_existing_pid,
    start_runtime_resources,
    stop_runtime_resources,
    synced_learning_service,
    sync_user_dictionary_components,
    set_selection_valid_with_logging,
    try_space_auto_conversion_at_boundary,
    try_mid_word_auto_conversion,
    update_passive_selection_baseline_on_click,
    update_selection_baseline,
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


def test_conversion_runtime_facade_requests_manual_conversion(monkeypatch):
    controller = object()
    execute = MagicMock()
    create_controller = MagicMock(return_value=controller)
    monkeypatch.setattr(
        runtime_conversion_module,
        "create_synced_manual_conversion_controller",
        create_controller,
    )
    monkeypatch.setattr(
        runtime_conversion_module,
        "execute_manual_conversion_with_session",
        execute,
    )
    session = object()
    config = MagicMock()
    config.get.return_value = 5
    dependencies = {
        "auto_detector": object(),
        "mid_word_detector": object(),
        "conversion_engine": object(),
        "virtual_kb": object(),
        "xkb": object(),
        "selection": object(),
        "platform": object(),
        "user_dict": object(),
        "timing": {"manual": 0.1},
    }
    facade = ConversionRuntimeFacade(
        state_manager=StateManager(),
        selection_tracker=SelectionFreshnessTracker(),
        typed_buffer=TypedBufferService(),
        auto_conversion_session=session,
        config=config,
        learning_service=LearningService(None),
        get_auto_detector=lambda: dependencies["auto_detector"],
        get_mid_word_detector=lambda: dependencies["mid_word_detector"],
        get_conversion_engine=lambda: dependencies["conversion_engine"],
        get_virtual_kb=lambda: dependencies["virtual_kb"],
        get_xkb=lambda: dependencies["xkb"],
        get_selection=lambda: dependencies["selection"],
        get_platform=lambda: dependencies["platform"],
        get_user_dict=lambda: dependencies["user_dict"],
        get_timing=lambda: dependencies["timing"],
        debug=True,
        manual_weight_step=4,
    )

    facade.request_manual_conversion()

    create_controller.assert_called_once()
    kwargs = create_controller.call_args.kwargs
    assert kwargs["conversion_engine"] is dependencies["conversion_engine"]
    assert kwargs["virtual_kb"] is dependencies["virtual_kb"]
    assert kwargs["xkb"] is dependencies["xkb"]
    assert kwargs["selection"] is dependencies["selection"]
    assert kwargs["user_dict"] is dependencies["user_dict"]
    assert kwargs["timing"] is dependencies["timing"]
    assert kwargs["debug"] is True
    assert kwargs["manual_weight_step"] == 4
    assert kwargs["decode_events"] == facade.decode_buffer
    assert kwargs["extract_last_word"] == facade.extract_last_word
    assert kwargs["update_selection_baseline"] == facade.update_selection_baseline
    execute.assert_called_once_with(controller=controller, session=session)


def test_conversion_runtime_facade_tries_space_auto_conversion(monkeypatch):
    use_case = object()
    run_boundary = MagicMock(return_value=True)
    monkeypatch.setattr(
        runtime_conversion_module,
        "try_space_auto_conversion_at_boundary",
        run_boundary,
    )
    config = MagicMock()
    config.get.side_effect = lambda key, default=None: {
        "auto_switch_threshold": 3,
        "user_dict_auto_confirm": True,
    }.get(key, default)
    session = object()
    state_manager = StateManager()
    facade = ConversionRuntimeFacade(
        state_manager=state_manager,
        selection_tracker=SelectionFreshnessTracker(),
        typed_buffer=TypedBufferService(),
        auto_conversion_session=session,
        config=config,
        learning_service=LearningService(None),
        get_auto_detector=lambda: object(),
        get_mid_word_detector=lambda: object(),
        get_conversion_engine=lambda: object(),
        get_virtual_kb=lambda: object(),
        get_xkb=lambda: object(),
        get_selection=lambda: object(),
        get_platform=lambda: object(),
        get_user_dict=lambda: object(),
        get_timing=lambda: {},
        debug=False,
        manual_weight_step=2,
    )
    monkeypatch.setattr(
        facade,
        "create_space_auto_conversion_use_case",
        MagicMock(return_value=use_case),
    )

    assert facade.try_space_auto_conversion() is True
    run_boundary.assert_called_once_with(
        use_case=use_case,
        session=session,
        context=state_manager.context,
        threshold=3,
        auto_confirm_enabled=True,
    )


def test_conversion_runtime_facade_tries_mid_word_auto_conversion(monkeypatch):
    use_case = object()
    run_mid_word = MagicMock(return_value=True)
    monkeypatch.setattr(
        runtime_conversion_module,
        "try_mid_word_auto_conversion",
        run_mid_word,
    )
    session = object()
    state_manager = StateManager()
    facade = ConversionRuntimeFacade(
        state_manager=state_manager,
        selection_tracker=SelectionFreshnessTracker(),
        typed_buffer=TypedBufferService(),
        auto_conversion_session=session,
        config=MagicMock(),
        learning_service=LearningService(None),
        get_auto_detector=lambda: object(),
        get_mid_word_detector=lambda: object(),
        get_conversion_engine=lambda: object(),
        get_virtual_kb=lambda: object(),
        get_xkb=lambda: object(),
        get_selection=lambda: object(),
        get_platform=lambda: object(),
        get_user_dict=lambda: object(),
        get_timing=lambda: {},
        debug=False,
        manual_weight_step=2,
    )
    monkeypatch.setattr(
        facade,
        "create_mid_word_auto_conversion_use_case",
        MagicMock(return_value=use_case),
    )

    assert facade.try_mid_word_auto_conversion() is True
    run_mid_word.assert_called_once_with(
        use_case=use_case,
        session=session,
        context=state_manager.context,
    )


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
        "lswitch.runtime_lifecycle.os.kill",
        lambda pid, sig: calls.append((pid, sig)),
    )

    assert is_process_alive(123) is True
    assert calls == [(123, 0)]


def test_is_process_alive_returns_false_on_os_error(monkeypatch):
    def fail(pid, sig):
        raise OSError("missing")

    monkeypatch.setattr("lswitch.runtime_lifecycle.os.kill", fail)

    assert is_process_alive(123) is False


def test_kill_existing_instance_returns_true_when_process_exits(monkeypatch):
    kill_calls = []
    alive_results = iter([True, False])
    monkeypatch.setattr(
        "lswitch.runtime_lifecycle.os.kill",
        lambda pid, sig: kill_calls.append((pid, sig)),
    )
    monkeypatch.setattr(
        "lswitch.runtime_lifecycle.is_process_alive",
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
        callbacks=InputRouterCallbacks(
            conversion=InputConversionPort(
                decode_buffer=lambda: "",
                auto_conversion_enabled=lambda: False,
                try_auto_conversion_at_space=lambda: False,
                mid_word_auto_conversion_enabled=lambda: False,
                try_mid_word_auto_conversion=lambda: False,
                get_pending_auto_space=lambda: True,
                set_pending_auto_space=set_pending_auto_space,
                clear_last_retype_events=clear_last_retype_events,
                clear_last_auto_marker=lambda: None,
                inject_deferred_space=lambda: None,
                request_conversion=lambda: None,
            ),
            selection=InputSelectionPort(
                prime_baseline_on_click=lambda: None,
                read_mouse_release_selection=lambda: None,
            ),
        ),
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


def _conversion_runtime(
    *,
    session,
    decode_buffer=None,
    try_space_auto_conversion=None,
    try_mid_word_auto_conversion=None,
    request_manual_conversion=None,
    mid_word_detector=None,
):
    return types.SimpleNamespace(
        auto_conversion_session=session,
        decode_buffer=decode_buffer or (lambda: ""),
        try_space_auto_conversion=try_space_auto_conversion or (lambda: False),
        try_mid_word_auto_conversion=try_mid_word_auto_conversion or (lambda: False),
        get_mid_word_detector=lambda: mid_word_detector,
        request_manual_conversion=request_manual_conversion or (lambda: None),
    )


def test_create_input_router_callbacks_wires_session_callbacks():
    session = types.SimpleNamespace(
        pending_space=True,
        set_pending_space=MagicMock(),
        clear_sticky_events=MagicMock(),
        clear_marker=MagicMock(),
    )

    callbacks = create_input_router_callbacks(
        conversion_runtime=_conversion_runtime(
            session=session,
            decode_buffer=lambda: "buffer",
        ),
        selection_tracker=MagicMock(),
        config=MagicMock(),
        get_auto_detector=lambda: None,
        get_virtual_kb=lambda: None,
        get_selection=lambda: None,
        get_platform=lambda: None,
        log=MagicMock(),
    )

    assert isinstance(callbacks, InputRouterCallbacks)
    assert isinstance(callbacks.conversion, InputConversionPort)
    assert callbacks.conversion.decode_buffer() == "buffer"
    assert callbacks.conversion.get_pending_auto_space() is True
    callbacks.conversion.set_pending_auto_space(False)
    callbacks.conversion.clear_last_retype_events()
    callbacks.conversion.clear_last_auto_marker()

    session.set_pending_space.assert_called_once_with(False)
    session.clear_sticky_events.assert_called_once()
    session.clear_marker.assert_called_once()


def test_create_input_router_callbacks_late_binds_auto_conversion_enabled():
    config = MagicMock()
    config.get.return_value = True
    detector = object()

    callbacks = create_input_router_callbacks(
        conversion_runtime=_conversion_runtime(
            session=types.SimpleNamespace(
                pending_space=False,
                set_pending_space=lambda value: None,
                clear_sticky_events=lambda: None,
                clear_marker=lambda: None,
            ),
        ),
        selection_tracker=MagicMock(),
        config=config,
        get_auto_detector=lambda: detector,
        get_virtual_kb=lambda: None,
        get_selection=lambda: None,
        get_platform=lambda: None,
        log=MagicMock(),
    )

    assert callbacks.conversion.auto_conversion_enabled() is True
    config.get.assert_called_once_with("auto_switch")


def test_create_input_router_callbacks_late_binds_mid_word_conversion_enabled():
    config = MagicMock()
    config.get.return_value = True
    detector = object()
    try_mid_word = MagicMock(return_value=True)

    callbacks = create_input_router_callbacks(
        conversion_runtime=_conversion_runtime(
            session=types.SimpleNamespace(
                pending_space=False,
                set_pending_space=lambda value: None,
                clear_sticky_events=lambda: None,
                clear_marker=lambda: None,
            ),
            mid_word_detector=detector,
            try_mid_word_auto_conversion=try_mid_word,
        ),
        selection_tracker=MagicMock(),
        config=config,
        get_auto_detector=lambda: None,
        get_virtual_kb=lambda: None,
        get_selection=lambda: None,
        get_platform=lambda: None,
        log=MagicMock(),
    )

    assert callbacks.conversion.mid_word_auto_conversion_enabled() is True
    assert callbacks.conversion.try_mid_word_auto_conversion() is True
    config.get.assert_called_once_with("auto_switch_mid_word")
    try_mid_word.assert_called_once()


def test_create_input_router_callbacks_late_binds_selection_dependencies():
    tracker = MagicMock()
    log = MagicMock()
    platform = types.SimpleNamespace(selection_mouse_release_tracking_enabled=True)

    class PassiveSelection:
        def get_passive_selection(self):
            return types.SimpleNamespace(text="fresh", owner_id=7)

    current = {
        "selection": PassiveSelection(),
        "platform": platform,
    }

    callbacks = create_input_router_callbacks(
        conversion_runtime=_conversion_runtime(
            session=types.SimpleNamespace(
                pending_space=False,
                set_pending_space=lambda value: None,
                clear_sticky_events=lambda: None,
                clear_marker=lambda: None,
            ),
        ),
        selection_tracker=tracker,
        config=MagicMock(),
        get_auto_detector=lambda: None,
        get_virtual_kb=lambda: None,
        get_selection=lambda: current["selection"],
        get_platform=lambda: current["platform"],
        log=log,
    )

    tracker.on_click_passive_selection.return_value = "fresh"
    callbacks.selection.prime_baseline_on_click()
    info = callbacks.selection.read_mouse_release_selection()

    tracker.on_click_passive_selection.assert_called_once_with("fresh", 7)
    assert info.text == "fresh"
    assert info.owner_id == 7


def test_create_input_router_callbacks_late_binds_virtual_keyboard_for_deferred_space():
    virtual_kb = MagicMock()

    callbacks = create_input_router_callbacks(
        conversion_runtime=_conversion_runtime(
            session=types.SimpleNamespace(
                pending_space=False,
                set_pending_space=lambda value: None,
                clear_sticky_events=lambda: None,
                clear_marker=lambda: None,
            ),
        ),
        selection_tracker=MagicMock(),
        config=MagicMock(),
        get_auto_detector=lambda: None,
        get_virtual_kb=lambda: virtual_kb,
        get_selection=lambda: None,
        get_platform=lambda: None,
        log=MagicMock(),
    )

    callbacks.conversion.inject_deferred_space()

    from lswitch.core.event_manager import KEY_SPACE

    virtual_kb.tap_key.assert_called_once_with(KEY_SPACE)


def test_inject_deferred_space_ignores_missing_virtual_keyboard():
    inject_deferred_space(None)


def test_auto_conversion_enabled_requires_detector_and_config_flag():
    config = MagicMock()
    config.get.return_value = True

    assert auto_conversion_enabled(config=config, auto_detector=object()) is True
    assert auto_conversion_enabled(config=config, auto_detector=None) is False

    config.get.return_value = False
    assert auto_conversion_enabled(config=config, auto_detector=object()) is False


def test_mid_word_auto_conversion_enabled_requires_detector_and_config_flag():
    config = MagicMock()
    config.get.return_value = True

    assert (
        mid_word_auto_conversion_enabled(
            config=config,
            mid_word_detector=object(),
        )
        is True
    )
    assert (
        mid_word_auto_conversion_enabled(
            config=config,
            mid_word_detector=None,
        )
        is False
    )

    config.get.return_value = False
    assert (
        mid_word_auto_conversion_enabled(
            config=config,
            mid_word_detector=object(),
        )
        is False
    )


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


def test_synced_learning_service_updates_and_returns_learning_service():
    user_dict = object()
    learning_service = MagicMock()

    result = synced_learning_service(
        user_dict=user_dict,
        user_dict_min_weight=5,
        learning_service=learning_service,
        debug=True,
        manual_weight_step=4,
    )

    assert result is learning_service
    assert learning_service.user_dict is user_dict
    assert learning_service.debug is True
    assert learning_service.manual_weight_step == 4


def test_read_runtime_config_snapshot_reads_timing_tables():
    timing = {"retype": 0.1}
    x11_selection_timing = {"poll_interval": 0.2}
    wayland_timing = {"wl_clipboard_timeout": 1.5}
    wayland_selection_timing = {"copy_wait_timeout": 0.7}
    values = {
        "timing": timing,
        "x11_selection_timing": x11_selection_timing,
        "wayland_timing": wayland_timing,
        "wayland_selection_timing": wayland_selection_timing,
    }
    config = MagicMock()
    config.get.side_effect = lambda key, default=None: values.get(key, default)

    snapshot = read_runtime_config_snapshot(config=config)

    assert isinstance(snapshot, RuntimeConfigSnapshot)
    assert snapshot.timing is timing
    assert snapshot.x11_selection_timing is x11_selection_timing
    assert snapshot.wayland_timing is wayland_timing
    assert snapshot.wayland_selection_timing is wayland_selection_timing


def test_apply_runtime_timing_config_updates_state_and_conversion_engine():
    config = MagicMock()
    timing = {
        "key_press_delay": 0.011,
        "key_repeat_delay": 0.012,
        "retype_before_replay_delay": 0.013,
        "direct_type_after_layout_switch_delay": 0.014,
        "undo_before_replay_delay": 0.015,
        "auto_before_replay_delay": 0.016,
        "auto_before_space_delay": 0.017,
    }
    x11_selection_timing = {"poll_interval": 0.2}
    wayland_timing = {"wl_clipboard_timeout": 1.5}
    wayland_selection_timing = {"copy_wait_timeout": 0.7}
    values = {
        "timing": timing,
        "x11_selection_timing": x11_selection_timing,
        "wayland_timing": wayland_timing,
        "wayland_selection_timing": wayland_selection_timing,
        "double_click_timeout": 0.45,
    }
    config.get.side_effect = lambda key, default=None: values.get(key, default)
    state_manager = MagicMock()
    state_manager.double_click_timeout = 0.3
    conversion_engine = MagicMock()

    snapshot = apply_runtime_timing_config(
        config=config,
        state_manager=state_manager,
        conversion_engine=conversion_engine,
    )

    assert isinstance(snapshot, RuntimeConfigSnapshot)
    assert snapshot.timing is timing
    assert snapshot.x11_selection_timing is x11_selection_timing
    assert snapshot.wayland_timing is wayland_timing
    assert snapshot.wayland_selection_timing is wayland_selection_timing
    assert state_manager.double_click_timeout == 0.45
    assert conversion_engine.timing is timing
    assert conversion_engine.timing["retype_before_replay_delay"] == 0.013
    assert (
        conversion_engine.timing["direct_type_after_layout_switch_delay"]
        == 0.014
    )
    assert conversion_engine.timing["undo_before_replay_delay"] == 0.015
    assert conversion_engine.timing["auto_before_replay_delay"] == 0.016
    assert conversion_engine.timing["auto_before_space_delay"] == 0.017


def test_apply_runtime_timing_config_tolerates_missing_conversion_engine():
    config = MagicMock()
    config.get.side_effect = lambda key, default=None: default
    state_manager = MagicMock()
    state_manager.double_click_timeout = 0.3

    snapshot = apply_runtime_timing_config(
        config=config,
        state_manager=state_manager,
        conversion_engine=None,
    )

    assert snapshot.timing == {}
    assert snapshot.x11_selection_timing == {}
    assert snapshot.wayland_timing == {}
    assert snapshot.wayland_selection_timing == {}
    assert state_manager.double_click_timeout == 0.3


def test_runtime_logging_controller_switches_info_debug_and_preserves_trace():
    root = MagicMock()
    controller = RuntimeLoggingController(root_logger=root)

    assert controller.reconfigure(True) is True
    root.setLevel.assert_called_with(logging.DEBUG)
    assert controller.reconfigure(False) is False
    root.setLevel.assert_called_with(logging.INFO)

    trace_root = MagicMock()
    trace_controller = RuntimeLoggingController(
        trace_override=True,
        root_logger=trace_root,
    )
    assert trace_controller.reconfigure(False) is True
    trace_root.setLevel.assert_called_once_with(5)


def test_apply_platform_runtime_config_updates_x11_adapter_and_poller():
    class Selection:
        def __init__(self):
            self.timing = None
            self._debug = False

        def reconfigure_timing(self, timing):
            self.timing = timing

    class Poller:
        def __init__(self):
            self.interval = None

        def set_poll_interval(self, value):
            self.interval = value

    selection = Selection()
    poller = Poller()
    snapshot = RuntimeConfigSnapshot(
        timing={},
        x11_selection_timing={
            "poll_interval": 0.17,
            "paste_delay": 0.18,
            "restore_delay": 0.19,
            "expand_selection_delay": 0.20,
        },
        wayland_timing={},
        wayland_selection_timing={},
    )

    changed = apply_platform_runtime_config(
        config=MagicMock(),
        snapshot=snapshot,
        selection=selection,
        selection_poller=poller,
        debug=True,
    )

    assert changed is False
    assert selection.timing["paste_delay"] == 0.18
    assert selection.timing["restore_delay"] == 0.19
    assert selection.timing["expand_selection_delay"] == 0.20
    assert selection._debug is True
    assert poller.interval == 0.17


def test_apply_platform_runtime_config_updates_wayland_and_resets_freshness():
    class TimingTarget:
        def __init__(self):
            self.timing = None
            self.debug = False

        def reconfigure_timing(self, timing):
            self.timing = timing

    class Selection:
        def __init__(self):
            self.strategy = "auto"
            self.timing = None
            self.debug = False

        def reconfigure(self, *, strategy, timing, debug):
            changed = strategy != self.strategy
            self.strategy = strategy
            self.timing = timing
            self.debug = debug
            return changed

    config = MagicMock()
    config.get.return_value = "primary_selection"
    virtual_kb = TimingTarget()
    system = TimingTarget()
    selection = Selection()
    tracker = SelectionFreshnessTracker(
        valid=True,
        repeat_valid=True,
        prev_text="stale",
        prev_owner_id=7,
        baseline_initialized=True,
    )
    common = {
        "key_press_delay": 0.011,
        "key_repeat_delay": 0.012,
        "retype_before_replay_delay": 0.013,
        "direct_type_after_layout_switch_delay": 0.014,
        "undo_before_replay_delay": 0.015,
        "auto_before_replay_delay": 0.016,
        "auto_before_space_delay": 0.017,
    }
    wayland = {"wl_clipboard_timeout": 1.7}
    wayland_selection = {
        "copy_wait_timeout": 0.21,
        "copy_poll_interval": 0.022,
        "copy_retry_delay": 0.023,
        "paste_delay": 0.024,
        "restore_delay": 0.025,
        "expand_selection_delay": 0.026,
    }
    snapshot = RuntimeConfigSnapshot(
        timing=common,
        x11_selection_timing={},
        wayland_timing=wayland,
        wayland_selection_timing=wayland_selection,
    )

    changed = apply_platform_runtime_config(
        config=config,
        snapshot=snapshot,
        virtual_kb=virtual_kb,
        selection=selection,
        system=system,
        selection_tracker=tracker,
        debug=True,
    )

    assert changed is True
    assert virtual_kb.timing["key_press_delay"] == 0.011
    assert virtual_kb.timing["key_repeat_delay"] == 0.012
    assert system.timing["wl_clipboard_timeout"] == 1.7
    assert selection.strategy == "primary_selection"
    assert selection.timing == wayland_selection
    assert selection.debug is True
    assert tracker.valid is False
    assert tracker.repeat_valid is False
    assert tracker.prev_text == ""
    assert tracker.prev_owner_id == 0
    assert tracker.baseline_initialized is False


def test_apply_user_dictionary_config_enables_dictionary():
    config = MagicMock()
    config.get.return_value = True
    user_dict = object()
    enable_user_dictionary = MagicMock(return_value=user_dict)
    log = MagicMock()

    result = apply_user_dictionary_config(
        config=config,
        user_dict=None,
        enable_user_dictionary=enable_user_dictionary,
        log=log,
    )

    assert result is user_dict
    enable_user_dictionary.assert_called_once_with()
    log.error.assert_not_called()


def test_apply_user_dictionary_config_propagates_enable_failure():
    config = MagicMock()
    config.get.return_value = True
    enable_user_dictionary = MagicMock(side_effect=RuntimeError("boom"))
    log = MagicMock()

    with pytest.raises(RuntimeError, match="boom"):
        apply_user_dictionary_config(
            config=config,
            user_dict=object(),
            enable_user_dictionary=enable_user_dictionary,
            log=log,
        )

    log.error.assert_not_called()


def test_apply_user_dictionary_config_disables_existing_dictionary():
    config = MagicMock()
    config.get.return_value = False
    enable_user_dictionary = MagicMock()
    log = MagicMock()

    result = apply_user_dictionary_config(
        config=config,
        user_dict=object(),
        enable_user_dictionary=enable_user_dictionary,
        log=log,
    )

    assert result is None
    enable_user_dictionary.assert_not_called()
    log.info.assert_called_once_with("User dictionary disabled")


def test_enable_user_dictionary_if_needed_returns_existing_dictionary():
    user_dict = object()

    result = enable_user_dictionary_if_needed(user_dict=user_dict, log=MagicMock())

    assert result is user_dict


def test_enable_user_dictionary_if_needed_creates_and_logs_dictionary(monkeypatch):
    class FakeUserDictionary:
        path = "/tmp/user.json"

    user_dictionary_module = types.ModuleType("lswitch.intelligence.user_dictionary")
    user_dictionary_module.UserDictionary = FakeUserDictionary
    monkeypatch.setitem(
        sys.modules,
        "lswitch.intelligence.user_dictionary",
        user_dictionary_module,
    )
    log = MagicMock()

    result = enable_user_dictionary_if_needed(user_dict=None, log=log)

    assert isinstance(result, FakeUserDictionary)
    log.info.assert_called_once_with("User dictionary enabled: %s", "/tmp/user.json")


def test_apply_runtime_config_update_applies_timing_user_dict_and_syncs_services():
    timing = {"delay": 0.1}
    values = {
        "timing": timing,
        "x11_selection_timing": {},
        "wayland_timing": {},
        "wayland_selection_timing": {},
        "double_click_timeout": 0.4,
        "user_dict_enabled": True,
        "user_dict_min_weight": 6,
    }
    config = MagicMock()
    config.get.side_effect = lambda key, default=None: values.get(key, default)
    state_manager = MagicMock()
    state_manager.double_click_timeout = 0.3
    conversion_engine = MagicMock()
    auto_detector = MagicMock()
    learning_service = MagicMock()
    user_dict = object()
    enable_user_dictionary = MagicMock(return_value=user_dict)

    applied = apply_runtime_config_update(
        config=config,
        state_manager=state_manager,
        conversion_engine=conversion_engine,
        user_dict=None,
        enable_user_dictionary=enable_user_dictionary,
        auto_detector=auto_detector,
        learning_service=learning_service,
        debug=True,
        manual_weight_step=4,
        log=MagicMock(),
    )

    assert isinstance(applied, AppliedRuntimeConfig)
    assert applied.timing.timing is timing
    assert applied.user_dict is user_dict
    assert state_manager.double_click_timeout == 0.4
    assert conversion_engine.timing is timing
    assert auto_detector.user_dict is user_dict
    assert auto_detector.user_dict_min_weight == 6
    assert conversion_engine.user_dict is user_dict
    assert learning_service.user_dict is user_dict
    assert learning_service.debug is True
    assert learning_service.manual_weight_step == 4


def test_create_space_auto_conversion_use_case_wires_retype_service(monkeypatch):
    created = {}

    class FakeRetypeService:
        def __init__(self, virtual_kb, xkb, debug):
            self.virtual_kb = virtual_kb
            self.xkb = xkb
            self.debug = debug
            created["retype_service"] = self

    class FakeSpaceAutoConversionUseCase:
        def __init__(
            self,
            *,
            auto_detector,
            typed_buffer,
            xkb,
            retype_service,
            learning_service,
            timing,
            debug,
        ):
            self.auto_detector = auto_detector
            self.typed_buffer = typed_buffer
            self.xkb = xkb
            self.retype_service = retype_service
            self.learning_service = learning_service
            self.timing = timing
            self.debug = debug

    conversion_module = types.ModuleType("lswitch.core.conversion_use_cases")
    conversion_module.SpaceAutoConversionUseCase = FakeSpaceAutoConversionUseCase
    retype_module = types.ModuleType("lswitch.core.retype_service")
    retype_module.RetypeService = FakeRetypeService
    monkeypatch.setitem(
        sys.modules,
        "lswitch.core.conversion_use_cases",
        conversion_module,
    )
    monkeypatch.setitem(sys.modules, "lswitch.core.retype_service", retype_module)
    auto_detector = object()
    typed_buffer = object()
    xkb = object()
    virtual_kb = object()
    learning_service = object()
    timing = {"auto_before_space_delay": 0.01}

    use_case = create_space_auto_conversion_use_case(
        auto_detector=auto_detector,
        typed_buffer=typed_buffer,
        xkb=xkb,
        virtual_kb=virtual_kb,
        learning_service=learning_service,
        timing=timing,
        debug=True,
    )

    assert isinstance(use_case, FakeSpaceAutoConversionUseCase)
    assert use_case.auto_detector is auto_detector
    assert use_case.typed_buffer is typed_buffer
    assert use_case.xkb is xkb
    assert use_case.learning_service is learning_service
    assert use_case.timing is timing
    assert use_case.debug is True
    assert use_case.retype_service is created["retype_service"]
    assert use_case.retype_service.virtual_kb is virtual_kb
    assert use_case.retype_service.xkb is xkb
    assert use_case.retype_service.debug is True


def test_create_synced_space_auto_conversion_use_case_syncs_learning_service(
    monkeypatch,
):
    created = {}

    class FakeRetypeService:
        def __init__(self, virtual_kb, xkb, debug):
            self.virtual_kb = virtual_kb
            self.xkb = xkb
            self.debug = debug

    class FakeSpaceAutoConversionUseCase:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            created["use_case"] = self

    conversion_module = types.ModuleType("lswitch.core.conversion_use_cases")
    conversion_module.SpaceAutoConversionUseCase = FakeSpaceAutoConversionUseCase
    retype_module = types.ModuleType("lswitch.core.retype_service")
    retype_module.RetypeService = FakeRetypeService
    monkeypatch.setitem(
        sys.modules,
        "lswitch.core.conversion_use_cases",
        conversion_module,
    )
    monkeypatch.setitem(sys.modules, "lswitch.core.retype_service", retype_module)
    user_dict = object()
    learning_service = MagicMock()

    use_case = create_synced_space_auto_conversion_use_case(
        auto_detector=object(),
        typed_buffer=object(),
        xkb=object(),
        virtual_kb=object(),
        user_dict=user_dict,
        user_dict_min_weight=7,
        learning_service=learning_service,
        timing={},
        debug=True,
        manual_weight_step=6,
    )

    assert use_case is created["use_case"]
    assert use_case.kwargs["learning_service"] is learning_service
    assert learning_service.user_dict is user_dict
    assert learning_service.debug is True
    assert learning_service.manual_weight_step == 6


def test_create_mid_word_auto_conversion_use_case_wires_retype_service(monkeypatch):
    created = {}

    class FakeRetypeService:
        def __init__(self, virtual_kb, xkb, debug):
            self.virtual_kb = virtual_kb
            self.xkb = xkb
            self.debug = debug
            created["retype_service"] = self

    class FakeMidWordAutoConversionUseCase:
        def __init__(
            self,
            *,
            mid_word_detector,
            typed_buffer,
            xkb,
            retype_service,
            timing,
            debug,
        ):
            self.mid_word_detector = mid_word_detector
            self.typed_buffer = typed_buffer
            self.xkb = xkb
            self.retype_service = retype_service
            self.timing = timing
            self.debug = debug

    conversion_module = types.ModuleType("lswitch.core.conversion_use_cases")
    conversion_module.MidWordAutoConversionUseCase = FakeMidWordAutoConversionUseCase
    retype_module = types.ModuleType("lswitch.core.retype_service")
    retype_module.RetypeService = FakeRetypeService
    monkeypatch.setitem(
        sys.modules,
        "lswitch.core.conversion_use_cases",
        conversion_module,
    )
    monkeypatch.setitem(sys.modules, "lswitch.core.retype_service", retype_module)
    detector = object()
    typed_buffer = object()
    xkb = object()
    virtual_kb = object()
    timing = {"mid_word_before_replay_delay": 0.01}

    use_case = create_mid_word_auto_conversion_use_case(
        mid_word_detector=detector,
        typed_buffer=typed_buffer,
        xkb=xkb,
        virtual_kb=virtual_kb,
        timing=timing,
        debug=True,
    )

    assert isinstance(use_case, FakeMidWordAutoConversionUseCase)
    assert use_case.mid_word_detector is detector
    assert use_case.typed_buffer is typed_buffer
    assert use_case.xkb is xkb
    assert use_case.timing is timing
    assert use_case.debug is True
    assert use_case.retype_service is created["retype_service"]
    assert use_case.retype_service.virtual_kb is virtual_kb
    assert use_case.retype_service.xkb is xkb
    assert use_case.retype_service.debug is True


def test_try_mid_word_auto_conversion_applies_marker_to_session():
    marker = object()
    result = types.SimpleNamespace(
        switched=True,
        marker=marker,
        marker_changed=True,
    )
    use_case = MagicMock()
    use_case.execute.return_value = result
    session = AutoConversionSessionState()
    context = object()

    assert (
        try_mid_word_auto_conversion(
            use_case=use_case,
            session=session,
            context=context,
        )
        is True
    )
    use_case.execute.assert_called_once_with(context=context)
    assert session.last_marker is marker


def test_create_manual_conversion_controller_wires_dependencies(monkeypatch):
    created = {}

    class FakeManualConversionController:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            created["controller"] = self

    controller_module = types.ModuleType("lswitch.core.manual_conversion_controller")
    controller_module.ManualConversionController = FakeManualConversionController
    monkeypatch.setitem(
        sys.modules,
        "lswitch.core.manual_conversion_controller",
        controller_module,
    )
    dependencies = {
        "state_manager": object(),
        "selection_tracker": object(),
        "typed_buffer": object(),
        "learning_service": object(),
        "conversion_engine": object(),
        "virtual_kb": object(),
        "xkb": object(),
        "selection": object(),
        "timing": {"manual": 0.1},
        "debug": True,
        "decode_events": object(),
        "extract_last_word": object(),
        "update_selection_baseline": object(),
    }

    controller = create_manual_conversion_controller(**dependencies)

    assert controller is created["controller"]
    assert controller.kwargs == dependencies


def test_create_synced_manual_conversion_controller_syncs_learning_service(
    monkeypatch,
):
    created = {}

    class FakeManualConversionController:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            created["controller"] = self

    controller_module = types.ModuleType("lswitch.core.manual_conversion_controller")
    controller_module.ManualConversionController = FakeManualConversionController
    monkeypatch.setitem(
        sys.modules,
        "lswitch.core.manual_conversion_controller",
        controller_module,
    )
    user_dict = object()
    learning_service = MagicMock()

    controller = create_synced_manual_conversion_controller(
        state_manager=object(),
        selection_tracker=object(),
        typed_buffer=object(),
        user_dict=user_dict,
        user_dict_min_weight=8,
        learning_service=learning_service,
        conversion_engine=object(),
        virtual_kb=object(),
        xkb=object(),
        selection=object(),
        timing={},
        debug=True,
        manual_weight_step=5,
        decode_events=object(),
        extract_last_word=object(),
        update_selection_baseline=object(),
    )

    assert controller is created["controller"]
    assert controller.kwargs["learning_service"] is learning_service
    assert learning_service.user_dict is user_dict
    assert learning_service.debug is True
    assert learning_service.manual_weight_step == 5


def test_execute_manual_conversion_with_session_passes_and_applies_state():
    marker = object()
    sticky_events = [object()]
    result = types.SimpleNamespace(
        last_auto_marker=None,
        sticky_events=[],
    )
    controller = MagicMock()
    controller.execute.return_value = result
    session = types.SimpleNamespace(
        last_marker=marker,
        sticky_events=sticky_events,
        apply_manual_result=MagicMock(),
    )

    execute_manual_conversion_with_session(
        controller=controller,
        session=session,
    )

    controller.execute.assert_called_once_with(
        last_auto_marker=marker,
        sticky_events=sticky_events,
    )
    session.apply_manual_result.assert_called_once_with(result)


def test_decode_buffer_events_uses_context_buffer_by_default():
    events = [object()]
    typed_buffer = MagicMock()
    typed_buffer.decode.return_value = "hello"
    context = types.SimpleNamespace(event_buffer=events)

    assert decode_buffer_events(typed_buffer=typed_buffer, context=context) == "hello"
    typed_buffer.decode.assert_called_once_with(events)


def test_decode_buffer_events_uses_explicit_events():
    context_events = [object()]
    explicit_events = [object()]
    typed_buffer = MagicMock()
    typed_buffer.decode.return_value = "word"
    context = types.SimpleNamespace(event_buffer=context_events)

    text = decode_buffer_events(
        typed_buffer=typed_buffer,
        context=context,
        events=explicit_events,
    )

    assert text == "word"
    typed_buffer.decode.assert_called_once_with(explicit_events)


def test_extract_last_word_events_returns_token_text_and_events():
    events = [object()]
    token = types.SimpleNamespace(text="hello", events=events)
    typed_buffer = MagicMock()
    typed_buffer.last_word.return_value = token
    context = object()
    current_layout = object()
    xkb = object()

    text, word_events = extract_last_word_events(
        typed_buffer=typed_buffer,
        context=context,
        current_layout=current_layout,
        xkb=xkb,
    )

    assert text == "hello"
    assert word_events is events
    typed_buffer.last_word.assert_called_once_with(
        context,
        current_layout=current_layout,
        xkb=xkb,
    )


def test_apply_space_auto_conversion_result_updates_marker_and_pending_space():
    marker = object()
    result = types.SimpleNamespace(
        marker_changed=True,
        marker=marker,
        pending_space=True,
    )

    state = apply_space_auto_conversion_result(
        result=result,
        last_auto_marker=object(),
        pending_auto_space=False,
    )

    assert isinstance(state, SpaceAutoConversionState)
    assert state.last_auto_marker is marker
    assert state.pending_auto_space is True


def test_apply_space_auto_conversion_result_preserves_state_when_result_is_noop():
    marker = object()
    result = types.SimpleNamespace(
        marker_changed=False,
        marker=object(),
        pending_space=False,
    )

    state = apply_space_auto_conversion_result(
        result=result,
        last_auto_marker=marker,
        pending_auto_space=True,
    )

    assert state.last_auto_marker is marker
    assert state.pending_auto_space is True


def test_try_space_auto_conversion_at_boundary_executes_and_applies_session_state():
    marker = object()
    new_marker = object()
    context = object()
    session = types.SimpleNamespace(
        last_marker=marker,
        pending_space=False,
        apply_space_state=MagicMock(),
    )
    result = types.SimpleNamespace(
        marker_changed=True,
        marker=new_marker,
        pending_space=True,
        space_consumed=True,
    )
    use_case = MagicMock()
    use_case.execute.return_value = result

    consumed = try_space_auto_conversion_at_boundary(
        use_case=use_case,
        session=session,
        context=context,
        threshold=3,
        auto_confirm_enabled=True,
    )

    assert consumed is True
    use_case.execute.assert_called_once_with(
        context=context,
        threshold=3,
        last_auto_marker=marker,
        auto_confirm_enabled=True,
    )
    state = session.apply_space_state.call_args.args[0]
    assert state.last_auto_marker is new_marker
    assert state.pending_auto_space is True


def test_perform_space_auto_conversion_at_boundary_executes_and_applies_session_state():
    marker = object()
    new_marker = object()
    context = object()
    events = [object()]
    session = types.SimpleNamespace(
        last_marker=marker,
        pending_space=False,
        apply_space_state=MagicMock(),
    )
    result = types.SimpleNamespace(
        marker_changed=True,
        marker=new_marker,
        pending_space=True,
        space_consumed=True,
    )
    use_case = MagicMock()
    use_case.perform_conversion.return_value = result

    perform_space_auto_conversion_at_boundary(
        use_case=use_case,
        session=session,
        context=context,
        word_len=6,
        word_events=events,
        direction="en_to_ru",
        original_word="ghbdtn",
        original_lang="en",
    )

    use_case.perform_conversion.assert_called_once_with(
        context=context,
        word_len=6,
        word_events=events,
        direction="en_to_ru",
        original_word="ghbdtn",
        original_lang="en",
    )
    state = session.apply_space_state.call_args.args[0]
    assert state.last_auto_marker is new_marker
    assert state.pending_auto_space is True


def test_read_mouse_release_selection_returns_none_without_selection():
    assert read_mouse_release_selection(selection=None, platform=object()) is None


def test_read_mouse_release_selection_respects_platform_tracking_flag():
    selection = MagicMock()
    platform = types.SimpleNamespace(selection_mouse_release_tracking_enabled=False)

    assert read_mouse_release_selection(selection=selection, platform=platform) is None
    selection.get_selection.assert_not_called()


def test_read_mouse_release_selection_uses_passive_reader_when_available():
    info = object()

    class PassiveSelection:
        def __init__(self):
            self.passive_calls = 0
            self.active_calls = 0

        def get_passive_selection(self):
            self.passive_calls += 1
            return info

        def get_selection(self):
            self.active_calls += 1
            return object()

    selection = PassiveSelection()

    assert read_mouse_release_selection(selection=selection, platform=object()) is info
    assert selection.passive_calls == 1
    assert selection.active_calls == 0


def test_read_mouse_release_selection_falls_back_to_active_selection():
    info = object()
    selection = MagicMock()
    selection.get_selection.return_value = info

    assert read_mouse_release_selection(selection=selection, platform=object()) is info
    selection.get_selection.assert_called_once_with()


def test_selection_baseline_tracking_enabled_defaults_to_true_without_platform():
    assert selection_baseline_tracking_enabled(platform=None) is True


def test_selection_baseline_tracking_enabled_defaults_to_true_without_flags():
    assert selection_baseline_tracking_enabled(platform=object()) is True


def test_selection_baseline_tracking_enabled_uses_polling_or_mouse_release_flags():
    assert selection_baseline_tracking_enabled(
        platform=types.SimpleNamespace(
            selection_polling_enabled=False,
            selection_mouse_release_tracking_enabled=False,
        )
    ) is False
    assert selection_baseline_tracking_enabled(
        platform=types.SimpleNamespace(
            selection_polling_enabled=True,
            selection_mouse_release_tracking_enabled=False,
        )
    ) is True
    assert selection_baseline_tracking_enabled(
        platform=types.SimpleNamespace(
            selection_polling_enabled=False,
            selection_mouse_release_tracking_enabled=True,
        )
    ) is True


def test_update_selection_baseline_updates_from_active_selection():
    tracker = MagicMock()
    selection = MagicMock()
    selection.get_selection.return_value = types.SimpleNamespace(
        text="word",
        owner_id=5,
    )

    update_selection_baseline(
        selection_tracker=tracker,
        selection=selection,
        platform=object(),
    )

    tracker.update_baseline.assert_called_once_with("word", 5)


def test_update_selection_baseline_uses_passive_reader_when_available():
    tracker = MagicMock()

    class PassiveSelection:
        def __init__(self):
            self.passive_calls = 0
            self.active_calls = 0

        def get_passive_selection(self):
            self.passive_calls += 1
            return types.SimpleNamespace(text="passive", owner_id=9)

        def get_selection(self):
            self.active_calls += 1
            return types.SimpleNamespace(text="active", owner_id=1)

    selection = PassiveSelection()

    update_selection_baseline(
        selection_tracker=tracker,
        selection=selection,
        platform=object(),
    )

    tracker.update_baseline.assert_called_once_with("passive", 9)
    assert selection.passive_calls == 1
    assert selection.active_calls == 0


def test_update_selection_baseline_skips_when_tracking_is_disabled():
    tracker = MagicMock()
    selection = MagicMock()
    platform = types.SimpleNamespace(
        selection_polling_enabled=False,
        selection_mouse_release_tracking_enabled=False,
    )

    update_selection_baseline(
        selection_tracker=tracker,
        selection=selection,
        platform=platform,
    )

    tracker.update_baseline.assert_not_called()
    selection.get_selection.assert_not_called()


def test_update_selection_baseline_tolerates_read_errors():
    tracker = MagicMock()
    selection = MagicMock()
    selection.get_selection.side_effect = RuntimeError("selection unavailable")

    update_selection_baseline(
        selection_tracker=tracker,
        selection=selection,
        platform=object(),
    )

    tracker.update_baseline.assert_not_called()


def test_handle_poller_selection_changed_marks_tracker_and_logs():
    tracker = MagicMock()
    log = MagicMock()

    handle_poller_selection_changed(
        selection_tracker=tracker,
        text="x" * 60,
        owner_id=42,
        log=log,
    )

    tracker.on_poller_changed.assert_called_once_with()
    log.debug.assert_called_once_with(
        "Poller: selection changed, fresh=True — text=%r owner=0x%x",
        "x" * 50,
        42,
    )


def test_set_selection_valid_with_logging_updates_tracker_and_debug_logs_change():
    tracker = types.SimpleNamespace(valid=False, set_valid=MagicMock())
    tracker.set_valid.side_effect = lambda value: setattr(tracker, "valid", value)
    log = MagicMock()
    log.isEnabledFor.return_value = False

    set_selection_valid_with_logging(
        selection_tracker=tracker,
        value=True,
        log=log,
    )

    tracker.set_valid.assert_called_once_with(True)
    log.debug.assert_called_once_with("fresh=%s → %s", False, True)
    log.trace.assert_not_called()


def test_set_selection_valid_with_logging_traces_assignment_when_enabled():
    tracker = types.SimpleNamespace(valid=False, set_valid=MagicMock())
    tracker.set_valid.side_effect = lambda value: setattr(tracker, "valid", value)
    log = MagicMock()
    log.isEnabledFor.return_value = True

    set_selection_valid_with_logging(
        selection_tracker=tracker,
        value=False,
        log=log,
    )

    tracker.set_valid.assert_called_once_with(False)
    log.debug.assert_not_called()
    log.trace.assert_called_once()


def test_update_passive_selection_baseline_on_click_updates_tracker_and_logs_fresh():
    tracker = MagicMock()
    tracker.on_click_passive_selection.return_value = "fresh"
    log = MagicMock()

    class PassiveSelection:
        def get_passive_selection(self):
            return types.SimpleNamespace(text="fresh selection", owner_id=42)

    update_passive_selection_baseline_on_click(
        selection_tracker=tracker,
        selection=PassiveSelection(),
        platform=types.SimpleNamespace(selection_mouse_release_tracking_enabled=True),
        log=log,
    )

    tracker.on_click_passive_selection.assert_called_once_with("fresh selection", 42)
    log.debug.assert_called_once()


def test_update_passive_selection_baseline_on_click_skips_when_platform_disables_tracking():
    tracker = MagicMock()

    update_passive_selection_baseline_on_click(
        selection_tracker=tracker,
        selection=MagicMock(),
        platform=types.SimpleNamespace(selection_mouse_release_tracking_enabled=False),
        log=MagicMock(),
    )

    tracker.on_click_passive_selection.assert_not_called()


def test_update_passive_selection_baseline_on_click_skips_without_passive_reader():
    tracker = MagicMock()

    update_passive_selection_baseline_on_click(
        selection_tracker=tracker,
        selection=MagicMock(),
        platform=types.SimpleNamespace(selection_mouse_release_tracking_enabled=True),
        log=MagicMock(),
    )

    tracker.on_click_passive_selection.assert_not_called()


def test_update_passive_selection_baseline_on_click_tolerates_read_errors():
    tracker = MagicMock()

    class PassiveSelection:
        def get_passive_selection(self):
            raise RuntimeError("selection unavailable")

    update_passive_selection_baseline_on_click(
        selection_tracker=tracker,
        selection=PassiveSelection(),
        platform=types.SimpleNamespace(selection_mouse_release_tracking_enabled=True),
        log=MagicMock(),
    )

    tracker.on_click_passive_selection.assert_not_called()


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
    assert components.prefix_dictionary.in_lang("en", "hello") is True
    assert components.mid_word_detector.prefix_dictionary is components.prefix_dictionary
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
    assert len(components.system_dictionaries) == 2
    assert all(
        status.enabled is False
        for status in components.system_dictionaries
    )


def test_create_mid_word_detection_runtime_uses_configured_prefix_len():
    dictionary = MagicMock()
    dictionary.words_for_lang.side_effect = lambda lang: {
        "en": {"hello"},
        "ru": {"привет"},
    }.get(lang, set())

    runtime = create_mid_word_detection_runtime(
        dictionary=dictionary,
        mid_word_min_prefix_len=5,
        system_dict_enabled=False,
    )

    assert isinstance(runtime, MidWordDetectionRuntime)
    assert runtime.prefix_dictionary.has_prefix("en", "hell") is False
    assert runtime.prefix_dictionary.has_prefix("en", "hello") is True
    assert runtime.mid_word_detector.min_prefix_len == 5
    assert runtime.mid_word_detector.prefix_dictionary is runtime.prefix_dictionary


def test_disabled_mid_word_runtime_does_not_load_system_dictionaries(monkeypatch):
    dictionary = MagicMock()
    dictionary.words_for_lang.side_effect = lambda lang: {
        "en": {"hello"},
        "ru": {"привет"},
    }.get(lang, set())
    loader = MagicMock()
    loader.get_status.side_effect = lambda lang, enabled: SystemDictionaryStatus(
        lang=lang,
        enabled=enabled,
    )
    monkeypatch.setattr(
        "lswitch.intelligence.system_dictionary_loader.SystemDictionaryLoader",
        MagicMock(return_value=loader),
    )

    runtime = create_mid_word_detection_runtime(
        dictionary=dictionary,
        auto_switch_mid_word=False,
        system_dict_enabled=True,
    )

    loader.load.assert_not_called()
    assert runtime.prefix_dictionary.in_lang("en", "hello") is True
    assert [status.enabled for status in runtime.system_dictionaries] == [
        False,
        False,
    ]


def test_enabled_mid_word_runtime_loads_system_dictionaries_and_user_protection(
    monkeypatch,
):
    dictionary = MagicMock()
    dictionary.words_for_lang.side_effect = lambda lang: {
        "en": {"hello"},
        "ru": {"привет"},
    }.get(lang, set())
    loader = MagicMock()
    loader.load.side_effect = lambda lang: types.SimpleNamespace(
        words={"world"} if lang == "en" else {"пример"},
    )
    loader.get_status.side_effect = lambda lang, enabled: SystemDictionaryStatus(
        lang=lang,
        enabled=enabled,
        path=(
            Path("/usr/share/hunspell/en_US.dic")
            if lang == "en"
            else Path("/usr/share/hunspell/ru_RU.dic")
        ),
        word_count=1,
    )
    loader_factory = MagicMock(return_value=loader)
    monkeypatch.setattr(
        "lswitch.intelligence.system_dictionary_loader.SystemDictionaryLoader",
        loader_factory,
    )
    user_dict = object()

    runtime = create_mid_word_detection_runtime(
        dictionary=dictionary,
        auto_switch_mid_word=True,
        system_dict_enabled=True,
        user_dict=user_dict,
        user_dict_min_weight=5,
    )

    assert [call.args for call in loader.load.call_args_list] == [("en",), ("ru",)]
    assert runtime.prefix_dictionary.in_lang("en", "world") is True
    assert runtime.prefix_dictionary.in_lang("ru", "пример") is True
    assert runtime.mid_word_detector.user_dict is user_dict
    assert runtime.mid_word_detector.user_dict_min_weight == 5
    assert [status.lang for status in runtime.system_dictionaries] == ["en", "ru"]
    assert all(status.loaded for status in runtime.system_dictionaries)


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
        prefix_dictionary=object(),
        mid_word_detector=object(),
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
        auto_switch_mid_word=True,
        mid_word_min_prefix_len=5,
        system_dict_enabled=True,
        system_dict_en_path="/tmp/en_US.dic",
        system_dict_ru_path="/tmp/ru_RU.dic",
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
        auto_switch_mid_word=True,
        mid_word_min_prefix_len=5,
        system_dict_enabled=True,
        system_dict_en_path="/tmp/en_US.dic",
        system_dict_ru_path="/tmp/ru_RU.dic",
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


def test_selection_poller_interval_updates_and_wakes_existing_thread():
    poller = SelectionPollerThread(MagicMock(), poll_interval=0.5)

    poller.set_poll_interval(0.075)

    assert poller.poll_interval == 0.075
    assert poller._poll_interval == 0.075
    assert poller._wake.is_set()


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
        "lswitch.runtime_lifecycle.signal.signal",
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
    monkeypatch.setattr(
        "lswitch.runtime_lifecycle.signal.signal",
        lambda signum, handler: None,
    )
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


def test_install_reload_signal_handler_uses_transactional_controller(monkeypatch):
    registered = {}
    monkeypatch.setattr(
        "lswitch.runtime_lifecycle.signal.signal",
        lambda signum, handler: registered.update({signum: handler}),
    )
    candidate = {"debug": True}
    config = MagicMock()
    config.read_candidate.return_value = candidate
    controller = MagicMock()
    controller.apply.return_value = types.SimpleNamespace(ok=True, error=None)
    log = MagicMock()

    handler = install_reload_signal_handler(
        config=config,
        config_controller=controller,
        debug=True,
        log=log,
    )
    handler(None, None)

    config.read_candidate.assert_called_once_with()
    config.reload.assert_not_called()
    controller.apply.assert_called_once_with(
        candidate,
        source="sighup",
        persist=False,
    )
    log.debug.assert_called_once_with("Config reloaded via SIGHUP")


def test_install_reload_signal_handler_keeps_runtime_on_invalid_file(monkeypatch):
    monkeypatch.setattr(
        "lswitch.runtime_lifecycle.signal.signal",
        lambda signum, handler: None,
    )
    config = MagicMock()
    config.read_candidate.side_effect = ValueError("invalid config")
    controller = MagicMock()
    log = MagicMock()

    handler = install_reload_signal_handler(
        config=config,
        config_controller=controller,
        debug=False,
        log=log,
    )
    handler(None, None)

    controller.apply.assert_not_called()
    log.error.assert_called_once_with(
        "Config reload via SIGHUP failed: %s",
        config.read_candidate.side_effect,
    )


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
        "lswitch.runtime_lifecycle.signal.signal",
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
    monkeypatch.setattr(
        "lswitch.runtime_lifecycle.signal.signal",
        lambda signum, handler: None,
    )

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


def test_run_qt_app_runtime_builds_tray_and_evdev_callbacks(monkeypatch):
    captured = {}
    tray = object()
    qt_app = object()
    event_bus = object()
    config = object()
    owner_app = object()
    xkb = object()
    device_manager = object()
    event_manager = object()
    is_running = MagicMock(return_value=True)

    monkeypatch.setattr(
        "lswitch.runtime_lifecycle.run_qt_runtime_loop",
        lambda **kwargs: captured.update(kwargs),
    )
    create_tray = MagicMock(return_value=tray)
    run_evdev = MagicMock()
    monkeypatch.setattr("lswitch.runtime_lifecycle.create_tray_indicator", create_tray)
    monkeypatch.setattr("lswitch.runtime_lifecycle.run_evdev_event_loop", run_evdev)

    run_qt_app_runtime(
        qt_app=qt_app,
        event_bus=event_bus,
        show_tray=True,
        config=config,
        owner_app=owner_app,
        xkb=xkb,
        is_running=is_running,
        device_manager=device_manager,
        event_manager=event_manager,
        stop_runtime=lambda: None,
    )

    assert captured["qt_app"] is qt_app
    assert captured["event_bus"] is event_bus
    assert captured["show_tray"] is True
    assert captured["create_tray"]() is tray
    create_tray.assert_called_once_with(
        event_bus=event_bus,
        config=config,
        qt_app=qt_app,
        owner_app=owner_app,
        xkb=xkb,
    )
    captured["run_evdev_loop"]()
    run_evdev.assert_called_once_with(
        is_running=is_running,
        device_manager=device_manager,
        event_manager=event_manager,
    )


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
