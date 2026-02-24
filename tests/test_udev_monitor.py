"""Tests for lswitch.input.udev_monitor — fully mocked pyudev."""

from __future__ import annotations

import sys
import types
import threading
import time
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# ---------------------------------------------------------------------------
# Build a fake pyudev module
# ---------------------------------------------------------------------------

_fake_pyudev = types.ModuleType("pyudev")


class _FakeContext:
    pass


class _FakeMonitor:
    def __init__(self):
        self._devices: list = []

    @classmethod
    def from_netlink(cls, context):
        return cls()

    def filter_by(self, subsystem: str = ""):
        pass

    def start(self):
        pass

    def poll(self, timeout: float = 1):
        return None


_fake_pyudev.Context = _FakeContext
_fake_pyudev.Monitor = _FakeMonitor

sys.modules.setdefault("pyudev", _fake_pyudev)

from lswitch.input.udev_monitor import UdevMonitor  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_udev_device(action: str, device_node: str | None) -> MagicMock:
    dev = MagicMock()
    dev.action = action
    dev.device_node = device_node
    return dev


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestUdevMonitorStart:
    def test_start_creates_daemon_thread(self):
        mon = UdevMonitor()
        # Patch _run so it exits immediately
        mon._run = MagicMock()
        result = mon.start()
        assert result is True
        assert mon._thread is not None
        assert mon._thread.daemon is True
        mon.stop()

    def test_start_sets_running(self):
        mon = UdevMonitor()
        mon._run = MagicMock()
        mon.start()
        assert mon._running is True
        mon.stop()

    def test_start_idempotent(self):
        mon = UdevMonitor()
        # Use an Event to keep the thread alive
        hold = threading.Event()
        mon._run = lambda: hold.wait(timeout=5)
        mon.start()
        thread1 = mon._thread
        mon.start()  # second call — same thread (still alive)
        assert mon._thread is thread1
        hold.set()
        mon.stop()


class TestUdevMonitorStop:
    def test_stop_clears_running(self):
        mon = UdevMonitor()
        mon._running = True
        mon._thread = MagicMock()
        mon.stop()
        assert mon._running is False

    def test_stop_when_not_started(self):
        mon = UdevMonitor()
        mon.stop()  # should not raise


class TestUdevMonitorCallbacks:
    def test_on_added_called(self):
        """Simulate an 'add' event through the _run loop."""
        added_paths: list[str] = []
        mon = UdevMonitor(on_added=lambda p: added_paths.append(p))

        # Create a mock monitor that yields one device then stops
        add_dev = _make_udev_device("add", "/dev/input/event5")
        call_count = 0

        def fake_poll(timeout=1):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return add_dev
            # Signal stop after first event
            mon._running = False
            return None

        mock_monitor = MagicMock()
        mock_monitor.poll = fake_poll

        with patch.object(_fake_pyudev, "Context", return_value=MagicMock()), \
             patch.object(_fake_pyudev.Monitor, "from_netlink", return_value=mock_monitor), \
             patch("lswitch.input.udev_monitor.time") as mock_time:
            mock_time.sleep = MagicMock()  # skip real sleep
            mon._running = True
            mon._run()

        assert added_paths == ["/dev/input/event5"]

    def test_on_removed_called(self):
        removed_paths: list[str] = []
        mon = UdevMonitor(on_removed=lambda p: removed_paths.append(p))

        rm_dev = _make_udev_device("remove", "/dev/input/event3")
        call_count = 0

        def fake_poll(timeout=1):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return rm_dev
            mon._running = False
            return None

        mock_monitor = MagicMock()
        mock_monitor.poll = fake_poll

        with patch.object(_fake_pyudev, "Context", return_value=MagicMock()), \
             patch.object(_fake_pyudev.Monitor, "from_netlink", return_value=mock_monitor):
            mon._running = True
            mon._run()

        assert removed_paths == ["/dev/input/event3"]

    def test_ignores_non_event_paths(self):
        """Non /dev/input/eventX paths should be ignored."""
        added_paths: list[str] = []
        mon = UdevMonitor(on_added=lambda p: added_paths.append(p))

        dev = _make_udev_device("add", "/dev/input/mouse0")
        call_count = 0

        def fake_poll(timeout=1):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return dev
            mon._running = False
            return None

        mock_monitor = MagicMock()
        mock_monitor.poll = fake_poll

        with patch.object(_fake_pyudev, "Context", return_value=MagicMock()), \
             patch.object(_fake_pyudev.Monitor, "from_netlink", return_value=mock_monitor), \
             patch("lswitch.input.udev_monitor.time") as mock_time:
            mock_time.sleep = MagicMock()
            mon._running = True
            mon._run()

        assert added_paths == []

    def test_ignores_none_device_node(self):
        added_paths: list[str] = []
        mon = UdevMonitor(on_added=lambda p: added_paths.append(p))

        dev = _make_udev_device("add", None)
        call_count = 0

        def fake_poll(timeout=1):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return dev
            mon._running = False
            return None

        mock_monitor = MagicMock()
        mock_monitor.poll = fake_poll

        with patch.object(_fake_pyudev, "Context", return_value=MagicMock()), \
             patch.object(_fake_pyudev.Monitor, "from_netlink", return_value=mock_monitor):
            mon._running = True
            mon._run()

        assert added_paths == []

    def test_callback_exception_does_not_crash(self):
        def bad_callback(path: str):
            raise RuntimeError("boom")

        mon = UdevMonitor(on_added=bad_callback)

        add_dev = _make_udev_device("add", "/dev/input/event1")
        call_count = 0

        def fake_poll(timeout=1):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return add_dev
            mon._running = False
            return None

        mock_monitor = MagicMock()
        mock_monitor.poll = fake_poll

        with patch.object(_fake_pyudev, "Context", return_value=MagicMock()), \
             patch.object(_fake_pyudev.Monitor, "from_netlink", return_value=mock_monitor), \
             patch("lswitch.input.udev_monitor.time") as mock_time:
            mock_time.sleep = MagicMock()
            mon._running = True
            mon._run()  # should not raise
