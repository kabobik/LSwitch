"""Tests for lswitch.input.virtual_keyboard — fully mocked evdev.UInput."""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch, call

import pytest

# ---------------------------------------------------------------------------
# Ensure a fake evdev module is available for import
# ---------------------------------------------------------------------------

if "evdev" not in sys.modules:
    _fake_evdev = types.ModuleType("evdev")
    _fake_ecodes = types.ModuleType("evdev.ecodes")
    _fake_ecodes.EV_KEY = 1
    _fake_evdev.ecodes = _fake_ecodes
    _fake_evdev.UInput = MagicMock
    sys.modules["evdev"] = _fake_evdev
    sys.modules["evdev.ecodes"] = _fake_ecodes

# Always get the actual module from sys.modules so patches target the right object
_evdev_mod = sys.modules["evdev"]
if not hasattr(_evdev_mod, "ecodes"):
    _evdev_mod.ecodes = types.ModuleType("evdev.ecodes")
    _evdev_mod.ecodes.EV_KEY = 1
if not hasattr(_evdev_mod.ecodes, "EV_KEY"):
    _evdev_mod.ecodes.EV_KEY = 1
if not hasattr(_evdev_mod, "UInput"):
    _evdev_mod.UInput = MagicMock

from lswitch.input.virtual_keyboard import VirtualKeyboard  # noqa: E402


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDeviceName:
    def test_device_name_constant(self):
        assert VirtualKeyboard.DEVICE_NAME == "LSwitch Virtual Keyboard"


class TestTapKey:
    def test_tap_key_press_release(self):
        """tap_key should generate value=1 (press), then value=0 (release)."""
        mock_uinput = MagicMock()
        with patch.object(_evdev_mod, "UInput", return_value=mock_uinput):
            vk = VirtualKeyboard()
            assert vk._uinput is mock_uinput

            vk.tap_key(30)  # KEY_A

            # Expect: write(EV_KEY, 30, 1), syn(), write(EV_KEY, 30, 0), syn()
            expected = [
                call.write(1, 30, 1),
                call.syn(),
                call.write(1, 30, 0),
                call.syn(),
            ]
            assert mock_uinput.method_calls == expected

    def test_tap_key_n_times(self):
        """tap_key with n_times=3 should do 3 pairs of press+release."""
        mock_uinput = MagicMock()
        with patch.object(_evdev_mod, "UInput", return_value=mock_uinput):
            vk = VirtualKeyboard()

            vk.tap_key(30, n_times=3)

            press_release = [
                call.write(1, 30, 1),
                call.syn(),
                call.write(1, 30, 0),
                call.syn(),
            ]
            assert mock_uinput.method_calls == press_release * 3


class TestReplayEvents:
    def test_replay_events(self):
        """replay_events should write each event's code and value."""
        mock_uinput = MagicMock()
        with patch.object(_evdev_mod, "UInput", return_value=mock_uinput):
            vk = VirtualKeyboard()

            ev1 = MagicMock(code=30, value=1)
            ev2 = MagicMock(code=30, value=0)
            vk.replay_events([ev1, ev2])

            expected = [
                call.write(1, 30, 1),
                call.syn(),
                call.write(1, 30, 0),
                call.syn(),
            ]
            assert mock_uinput.method_calls == expected

    def test_replay_events_empty_list(self):
        """Empty event list should not crash."""
        mock_uinput = MagicMock()
        with patch.object(_evdev_mod, "UInput", return_value=mock_uinput):
            vk = VirtualKeyboard()

            mock_uinput.reset_mock()
            vk.replay_events([])
            # No writes should have been made
            assert mock_uinput.write.call_count == 0

    def test_replay_events_auto_release_for_press_only(self):
        """Press-only event (value=1) without a matching release in the list
        must get a synthetic release (value=0) appended automatically.
        This prevents the kernel from generating infinite auto-repeat events."""
        mock_uinput = MagicMock()
        with patch.object(_evdev_mod, "UInput", return_value=mock_uinput):
            vk = VirtualKeyboard()

            ev = MagicMock(code=49, value=1)  # 'n' pressed, never released
            vk.replay_events([ev])

            # Expect: write(EV_KEY, 49, 1), syn, write(EV_KEY, 49, 0), syn
            expected = [
                call.write(1, 49, 1),
                call.syn(),
                call.write(1, 49, 0),
                call.syn(),
            ]
            assert mock_uinput.method_calls == expected

    def test_replay_events_no_extra_release_when_paired(self):
        """If the event list already contains the release, no extra release
        should be added (prevents double-release / XKB-toggle bug)."""
        mock_uinput = MagicMock()
        with patch.object(_evdev_mod, "UInput", return_value=mock_uinput):
            vk = VirtualKeyboard()

            ev_press = MagicMock(code=42, value=1)   # LShift press
            ev_release = MagicMock(code=42, value=0)  # LShift release (paired)
            vk.replay_events([ev_press, ev_release])

            # Exactly 4 calls: press + syn + release + syn (no extra)
            assert mock_uinput.write.call_count == 2
            assert mock_uinput.method_calls == [
                call.write(1, 42, 1),
                call.syn(),
                call.write(1, 42, 0),
                call.syn(),
            ]

    def test_replay_events_multiple_keys_auto_release(self):
        """Multiple press-only events each get their own synthetic release."""
        mock_uinput = MagicMock()
        with patch.object(_evdev_mod, "UInput", return_value=mock_uinput):
            vk = VirtualKeyboard()

            events = [
                MagicMock(code=30, value=1),  # 'a' press, no release
                MagicMock(code=48, value=1),  # 'b' press, no release
            ]
            vk.replay_events(events)

            writes = [(c.args[1], c.args[2]) for c in mock_uinput.write.call_args_list]
            # Both should be pressed then released
            assert (30, 1) in writes
            assert (30, 0) in writes
            assert (48, 1) in writes
            assert (48, 0) in writes


class TestWriteWithNoUInput:
    def test_write_does_not_crash_when_uinput_is_none(self):
        """If UInput creation failed, _write should silently return."""
        with patch.object(_evdev_mod, "UInput", side_effect=Exception("no access")):
            vk = VirtualKeyboard()
            assert vk._uinput is None

        # Should not raise
        vk.tap_key(30)
        vk.replay_events([MagicMock(code=30, value=1)])


class TestClose:
    def test_close_calls_uinput_close(self):
        mock_uinput = MagicMock()
        with patch.object(_evdev_mod, "UInput", return_value=mock_uinput):
            vk = VirtualKeyboard()

        vk.close()
        mock_uinput.close.assert_called_once()
        assert vk._uinput is None

    def test_close_when_already_none(self):
        """close() when _uinput is None should not crash."""
        with patch.object(_evdev_mod, "UInput", side_effect=Exception("no access")):
            vk = VirtualKeyboard()

        vk.close()  # should not raise

    def test_close_idempotent(self):
        mock_uinput = MagicMock()
        with patch.object(_evdev_mod, "UInput", return_value=mock_uinput):
            vk = VirtualKeyboard()

        vk.close()
        vk.close()  # second call should not crash
        mock_uinput.close.assert_called_once()
