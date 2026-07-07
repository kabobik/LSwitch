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
    RuntimeCoreComponents,
    SelectionPollerThread,
    create_conversion_runtime,
    create_core_components,
    create_input_device_runtime,
    create_input_router,
    stop_runtime_resources,
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
