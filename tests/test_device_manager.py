"""Tests for lswitch.input.device_manager — fully mocked evdev."""

from __future__ import annotations

import selectors
import sys
import types
from unittest.mock import MagicMock, PropertyMock, patch, call

import pytest

# ---------------------------------------------------------------------------
# Build a fake evdev module so we never touch real devices
# ---------------------------------------------------------------------------

_fake_evdev = types.ModuleType("evdev")
_fake_ecodes = types.ModuleType("evdev.ecodes")

# Key constants used by DeviceManager
_fake_ecodes.EV_KEY = 1
_fake_ecodes.KEY_A = 30
_fake_ecodes.BTN_LEFT = 0x110
_fake_ecodes.BTN_RIGHT = 0x111

_fake_evdev.ecodes = _fake_ecodes
_fake_evdev.InputDevice = MagicMock  # will be patched per-test
_fake_evdev.list_devices = MagicMock(return_value=[])

# Inject into sys.modules BEFORE importing device_manager
sys.modules.setdefault("evdev", _fake_evdev)
sys.modules.setdefault("evdev.ecodes", _fake_ecodes)

from lswitch.input.device_manager import DeviceManager  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_device(
    name: str = "Test Keyboard",
    path: str = "/dev/input/event0",
    has_ev_key: bool = True,
    has_key_a: bool = True,
    has_btn_left: bool = False,
) -> MagicMock:
    """Create a mock evdev.InputDevice."""
    dev = MagicMock()
    dev.name = name
    dev.path = path
    dev.fd = 42  # selectors needs a fileno-like attribute

    keys: list[int] = []
    if has_key_a:
        keys.append(_fake_ecodes.KEY_A)
    if has_btn_left:
        keys.append(_fake_ecodes.BTN_LEFT)

    caps: dict = {}
    if has_ev_key:
        caps[_fake_ecodes.EV_KEY] = keys

    dev.capabilities.return_value = caps
    dev.read.return_value = []
    dev.close.return_value = None
    # Make fileno() work for DefaultSelector
    dev.fileno.return_value = id(dev) % (2**31)
    return dev


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestScanDevices:
    def test_finds_suitable_device(self):
        dev = _make_device(path="/dev/input/event0")
        with patch.object(_fake_evdev, "list_devices", return_value=["/dev/input/event0"]), \
             patch.object(_fake_evdev, "InputDevice", return_value=dev):
            dm = DeviceManager()
            # Patch selector to avoid real fd registration
            dm.selector = MagicMock()
            count = dm.scan_devices()
            assert count == 1
            assert "/dev/input/event0" in dm.devices

    def test_skips_device_without_ev_key(self):
        dev = _make_device(has_ev_key=False, path="/dev/input/event1")
        with patch.object(_fake_evdev, "list_devices", return_value=["/dev/input/event1"]), \
             patch.object(_fake_evdev, "InputDevice", return_value=dev):
            dm = DeviceManager()
            dm.selector = MagicMock()
            count = dm.scan_devices()
            assert count == 0
            assert dm.device_count == 0

    def test_skips_device_without_key_a_or_btn(self):
        dev = _make_device(has_key_a=False, has_btn_left=False, path="/dev/input/event2")
        with patch.object(_fake_evdev, "list_devices", return_value=["/dev/input/event2"]), \
             patch.object(_fake_evdev, "InputDevice", return_value=dev):
            dm = DeviceManager()
            dm.selector = MagicMock()
            count = dm.scan_devices()
            assert count == 0

    def test_accepts_mouse_device(self):
        dev = _make_device(name="Mouse", has_key_a=False, has_btn_left=True, path="/dev/input/event3")
        with patch.object(_fake_evdev, "list_devices", return_value=["/dev/input/event3"]), \
             patch.object(_fake_evdev, "InputDevice", return_value=dev):
            dm = DeviceManager()
            dm.selector = MagicMock()
            count = dm.scan_devices()
            assert count == 1


class TestIsSuitableDevice:
    def test_filters_virtual_kb_by_name(self):
        dm = DeviceManager()
        dm.set_virtual_kb_name("LSwitch Virtual Keyboard")
        dev = _make_device(name="LSwitch Virtual Keyboard")
        assert dm._is_suitable_device(dev) is False

    def test_filters_via_device_filter(self):
        """device_filter excludes names containing 'virtual', 'lswitch', 'uinput'."""
        dm = DeviceManager()
        dev = _make_device(name="Some Virtual Device")
        assert dm._is_suitable_device(dev) is False

    def test_accepts_real_keyboard(self):
        dm = DeviceManager()
        dev = _make_device(name="AT Translated Set 2 keyboard")
        assert dm._is_suitable_device(dev) is True


class TestRemoveDevice:
    def test_remove_existing_device(self):
        dm = DeviceManager()
        dm.selector = MagicMock()
        dev = _make_device(path="/dev/input/event0")
        dm.devices["/dev/input/event0"] = dev

        result = dm.remove_device("/dev/input/event0")
        assert result is True
        assert "/dev/input/event0" not in dm.devices
        dev.close.assert_called_once()

    def test_remove_nonexistent_device(self):
        dm = DeviceManager()
        result = dm.remove_device("/dev/input/event99")
        assert result is False

    def test_remove_calls_on_device_removed(self):
        callback = MagicMock()
        dm = DeviceManager(on_device_removed=callback)
        dm.selector = MagicMock()
        dev = _make_device(path="/dev/input/event0")
        dm.devices["/dev/input/event0"] = dev

        dm.remove_device("/dev/input/event0")
        callback.assert_called_once_with(dev)


class TestGetEvents:
    def test_yields_events_from_device(self):
        dm = DeviceManager()

        ev1 = MagicMock()
        ev2 = MagicMock()
        dev = _make_device()
        dev.read.return_value = [ev1, ev2]

        key = MagicMock()
        key.fileobj = dev

        dm.selector = MagicMock()
        dm.selector.select.return_value = [(key, selectors.EVENT_READ)]

        events = list(dm.get_events(timeout=0.01))
        assert len(events) == 2
        assert events[0] == (dev, ev1)
        assert events[1] == (dev, ev2)

    def test_handles_read_error_gracefully(self):
        dm = DeviceManager()
        dm.selector = MagicMock()

        dev = _make_device(path="/dev/input/event0")
        dev.read.side_effect = OSError("device disconnected")
        dm.devices["/dev/input/event0"] = dev

        key = MagicMock()
        key.fileobj = dev
        dm.selector.select.return_value = [(key, selectors.EVENT_READ)]

        events = list(dm.get_events(timeout=0.01))
        assert events == []
        # Device should have been removed
        assert "/dev/input/event0" not in dm.devices


class TestCallbacks:
    def test_on_device_added_called(self):
        callback = MagicMock()
        dm = DeviceManager(on_device_added=callback)
        dm.selector = MagicMock()

        dev = _make_device(path="/dev/input/event0")
        with patch.object(_fake_evdev, "InputDevice", return_value=dev):
            dm._try_add_device("/dev/input/event0")

        callback.assert_called_once_with(dev)

    def test_on_device_removed_called(self):
        callback = MagicMock()
        dm = DeviceManager(on_device_removed=callback)
        dm.selector = MagicMock()

        dev = _make_device(path="/dev/input/event0")
        dm.devices["/dev/input/event0"] = dev
        dm.remove_device("/dev/input/event0")

        callback.assert_called_once_with(dev)

    def test_callback_exception_does_not_propagate(self):
        callback = MagicMock(side_effect=RuntimeError("boom"))
        dm = DeviceManager(on_device_added=callback)
        dm.selector = MagicMock()

        dev = _make_device(path="/dev/input/event0")
        with patch.object(_fake_evdev, "InputDevice", return_value=dev):
            result = dm._try_add_device("/dev/input/event0")

        assert result is True  # should succeed despite callback error


class TestClose:
    def test_close_does_not_crash(self):
        dm = DeviceManager()
        dm.selector = MagicMock()
        dm.close()  # should not raise

    def test_close_cleans_up_devices(self):
        dm = DeviceManager()
        dm.selector = MagicMock()
        dev = _make_device(path="/dev/input/event0")
        dm.devices["/dev/input/event0"] = dev

        dm.close()
        assert dm.device_count == 0
        dev.close.assert_called_once()


class TestContextManager:
    def test_context_manager_calls_close(self):
        dm = DeviceManager()
        dm.selector = MagicMock()
        dm.close = MagicMock()

        with dm:
            pass

        dm.close.assert_called_once()

    def test_context_manager_returns_self(self):
        dm = DeviceManager()
        dm.selector = MagicMock()

        with dm as ctx:
            assert ctx is dm

        dm.close()


class TestDeviceCount:
    def test_device_count_property(self):
        dm = DeviceManager()
        assert dm.device_count == 0
        dm.devices["a"] = MagicMock()
        dm.devices["b"] = MagicMock()
        assert dm.device_count == 2
