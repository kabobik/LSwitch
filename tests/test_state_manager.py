"""Tests for StateManager transitions."""

from __future__ import annotations

import logging
import time

import lswitch.log
from lswitch.core.state_manager import StateManager
from lswitch.core.states import State


def test_initial_state():
    sm = StateManager()
    assert sm.state == State.IDLE


def test_key_press_moves_to_typing():
    sm = StateManager()
    sm.on_key_press(30)  # KEY_A
    assert sm.state == State.TYPING


def test_shift_down_from_typing():
    sm = StateManager()
    sm.on_key_press(30)
    sm.on_shift_down()
    assert sm.state == State.SHIFT_PRESSED


def test_single_shift_returns_to_typing():
    sm = StateManager(double_click_timeout=0.3)
    sm.on_key_press(30)
    sm.on_shift_down()
    time.sleep(0.35)  # exceeds timeout
    is_double = sm.on_shift_up()
    assert not is_double
    assert sm.state == State.TYPING


def test_double_shift_moves_to_converting():
    sm = StateManager(double_click_timeout=0.3)
    sm.on_key_press(30)
    sm.on_shift_down()
    sm.on_shift_up()  # first press
    sm.on_shift_down()
    is_double = sm.on_shift_up()  # second press
    assert is_double
    assert sm.state == State.CONVERTING


def test_navigation_resets_to_idle():
    sm = StateManager()
    sm.on_key_press(30)
    sm.on_navigation()
    assert sm.state == State.IDLE
    assert sm.context.chars_in_buffer == 0


def test_backspace_hold_transition():
    sm = StateManager()
    sm.on_key_press(30)
    sm.on_backspace_hold()
    assert sm.state == State.BACKSPACE_HOLD


def test_conversion_complete_returns_idle():
    sm = StateManager(double_click_timeout=0.3)
    sm.on_key_press(30)
    sm.on_shift_down()
    sm.on_shift_up()
    sm.on_shift_down()
    sm.on_shift_up()
    sm.on_conversion_complete()
    assert sm.state == State.IDLE


def test_regular_transition_logs_at_trace_not_debug(caplog):
    sm = StateManager(debug=True)

    with caplog.at_level(logging.DEBUG, logger="lswitch.core.state_manager"):
        sm.on_key_press(30)

    assert "key_press" not in caplog.text

    caplog.clear()
    sm = StateManager(debug=True)
    with caplog.at_level(lswitch.log.TRACE, logger="lswitch.core.state_manager"):
        sm.on_key_press(30)

    assert "key_press" in caplog.text


def test_double_shift_transition_stays_debug_visible(caplog):
    sm = StateManager(double_click_timeout=0.3, debug=True)

    with caplog.at_level(logging.DEBUG, logger="lswitch.core.state_manager"):
        sm.on_shift_down()
        sm.on_shift_up()
        sm.on_shift_down()
        sm.on_shift_up()

    assert "shift_up_double" in caplog.text
    assert "shift_down" not in caplog.text
    assert "shift_up_single" not in caplog.text
