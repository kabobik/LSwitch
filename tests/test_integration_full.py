"""Full integration tests — E2E pipelines across all layers.

These tests exercise the interaction between LSwitchApp, EventBus,
StateManager, ConversionEngine, EventManager and platform adapters
WITHOUT importing PyQt5 or requiring real X11/evdev.
"""

from __future__ import annotations

import time
import os
import tempfile
from dataclasses import dataclass
from unittest import mock

import pytest

from lswitch.app import LSwitchApp
from lswitch.config import ConfigManager, DEFAULT_CONFIG
from lswitch.core.event_bus import EventBus
from lswitch.core.events import Event, EventType, KeyEventData
from lswitch.core.state_manager import StateManager
from lswitch.core.states import State, StateContext
from lswitch.core.conversion_engine import ConversionEngine
from lswitch.core.event_manager import (
    EventManager, SHIFT_KEYS, KEY_BACKSPACE, NAVIGATION_KEYS, EV_KEY,
)
from lswitch.core.text_converter import convert_text

# Re-use mock adapters from conftest
from tests.conftest import MockXKBAdapter, MockSelectionAdapter, MockSystemAdapter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_app(tmp_path=None) -> LSwitchApp:
    """Create an LSwitchApp with mocked platform components."""
    config_path = None
    if tmp_path is not None:
        config_path = str(tmp_path / "config.json")
    app = LSwitchApp(headless=True, debug=True, config_path=config_path)
    # Inject mocks instead of calling _init_platform()
    app.xkb = MockXKBAdapter()
    app.selection = MockSelectionAdapter()
    app.system = MockSystemAdapter()
    app.virtual_kb = mock.MagicMock()
    app.device_manager = mock.MagicMock()

    from lswitch.intelligence.dictionary_service import DictionaryService

    dictionary = DictionaryService()
    app.conversion_engine = ConversionEngine(
        xkb=app.xkb,
        selection=app.selection,
        virtual_kb=app.virtual_kb,
        dictionary=dictionary,
        system=app.system,
        debug=True,
    )
    app.event_manager = EventManager(app.event_bus, debug=True)
    return app


@dataclass
class FakeEvdevEvent:
    """Minimal stand-in for an evdev InputEvent."""
    type: int
    code: int
    value: int  # 0=release, 1=press, 2=repeat


def _press(code: int) -> FakeEvdevEvent:
    return FakeEvdevEvent(type=EV_KEY, code=code, value=1)


def _release(code: int) -> FakeEvdevEvent:
    return FakeEvdevEvent(type=EV_KEY, code=code, value=0)


def _repeat(code: int) -> FakeEvdevEvent:
    return FakeEvdevEvent(type=EV_KEY, code=code, value=2)


KEY_A = 30
KEY_S = 31
KEY_D = 32
KEY_F = 33
KEY_ENTER_CODE = 28
KEY_LEFT_ARROW = 105
KEY_LSHIFT = 42
KEY_RSHIFT = 54


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAppInitAndWiring:
    """1. App init → _wire_event_bus → EventBus subscriptions."""

    def test_wire_event_bus_subscribes_key_events(self, tmp_path):
        """After _wire_event_bus, EventBus should have handlers for KEY_PRESS, KEY_RELEASE, MOUSE_CLICK."""
        app = _make_app(tmp_path)
        app._wire_event_bus()

        assert len(app.event_bus._handlers[EventType.KEY_PRESS]) >= 1
        assert len(app.event_bus._handlers[EventType.KEY_RELEASE]) >= 1
        assert len(app.event_bus._handlers[EventType.MOUSE_CLICK]) >= 1


class TestEventPipeline:
    """2. Raw evdev event → EventBus → StateManager → conversion triggered."""

    def test_double_shift_triggers_converting_state(self, tmp_path):
        """Simulate typing + double Shift → state should reach CONVERTING."""
        app = _make_app(tmp_path)
        app._wire_event_bus()

        # Type a few characters to enter TYPING state
        app.event_manager.handle_raw_event(_press(KEY_A), "test_kb")
        app.event_manager.handle_raw_event(_release(KEY_A), "test_kb")
        assert app.state_manager.state == State.TYPING

        # First Shift press+release — sets last_shift_time
        app.event_manager.handle_raw_event(_press(KEY_LSHIFT), "test_kb")
        app.event_manager.handle_raw_event(_release(KEY_LSHIFT), "test_kb")

        # Second Shift press+release — within double_click_timeout → double shift
        app.event_manager.handle_raw_event(_press(KEY_LSHIFT), "test_kb")
        app.event_manager.handle_raw_event(_release(KEY_LSHIFT), "test_kb")

        # After conversion, state goes back to IDLE
        assert app.state_manager.state == State.IDLE


class TestConfigChangePipeline:
    """3. CONFIG_CHANGED event through EventBus."""

    def test_config_changed_event_delivered(self, tmp_path):
        """Publishing CONFIG_CHANGED should be delivered to subscribers."""
        app = _make_app(tmp_path)
        received = []
        app.event_bus.subscribe(EventType.CONFIG_CHANGED, lambda e: received.append(e))

        app.event_bus.publish(
            Event(type=EventType.CONFIG_CHANGED, data={"auto_switch": True}, timestamp=time.time())
        )
        assert len(received) == 1
        assert received[0].data["auto_switch"] is True


class TestSelectionModeE2E:
    """4. Backspace hold → double Shift → selection mode → replace_selection called."""

    def test_backspace_hold_then_double_shift(self, tmp_path):
        """After backspace hold, double Shift should trigger selection mode conversion."""
        app = _make_app(tmp_path)
        app._wire_event_bus()

        # Type some characters first
        for code in [KEY_A, KEY_S, KEY_D]:
            app.event_manager.handle_raw_event(_press(code), "test_kb")
            app.event_manager.handle_raw_event(_release(code), "test_kb")

        assert app.state_manager.state == State.TYPING

        # Hold backspace (3 repeats triggers backspace_hold)
        app.event_manager.handle_raw_event(_press(KEY_BACKSPACE), "test_kb")
        for _ in range(4):
            app.event_manager.handle_raw_event(_repeat(KEY_BACKSPACE), "test_kb")
        app.event_manager.handle_raw_event(_release(KEY_BACKSPACE), "test_kb")

        assert app.state_manager.context.backspace_hold_active is True

        # Set up a selection for selection mode
        app.selection.set_selection("ghbdtn")

        # Double Shift
        app.event_manager.handle_raw_event(_press(KEY_LSHIFT), "test_kb")
        app.event_manager.handle_raw_event(_release(KEY_LSHIFT), "test_kb")
        app.event_manager.handle_raw_event(_press(KEY_LSHIFT), "test_kb")
        app.event_manager.handle_raw_event(_release(KEY_LSHIFT), "test_kb")

        # Conversion should have completed — state back to IDLE
        assert app.state_manager.state == State.IDLE


class TestRetypeModeE2E:
    """5. Typing → double Shift → retype mode attempts."""

    def test_retype_mode_executes_on_typing(self, tmp_path):
        """After typing characters and double Shift, retype should be attempted."""
        app = _make_app(tmp_path)
        app._wire_event_bus()

        # Type characters (entering TYPING state and adding to buffer)
        for code in [KEY_A, KEY_S, KEY_D, KEY_F]:
            app.event_manager.handle_raw_event(_press(code), "test_kb")
            app.event_manager.handle_raw_event(_release(code), "test_kb")

        assert app.state_manager.state == State.TYPING
        assert app.state_manager.context.chars_in_buffer == 4

        # Double shift to trigger conversion
        app.event_manager.handle_raw_event(_press(KEY_LSHIFT), "test_kb")
        app.event_manager.handle_raw_event(_release(KEY_LSHIFT), "test_kb")
        app.event_manager.handle_raw_event(_press(KEY_LSHIFT), "test_kb")
        app.event_manager.handle_raw_event(_release(KEY_LSHIFT), "test_kb")

        # After conversion, back to IDLE
        assert app.state_manager.state == State.IDLE


class TestMouseClickResetsState:
    """6. Mouse click resets state to IDLE."""

    def test_mouse_click_resets_to_idle(self, tmp_path):
        """After typing, a mouse click should reset state to IDLE."""
        app = _make_app(tmp_path)
        app._wire_event_bus()

        # Type to enter TYPING
        app.event_manager.handle_raw_event(_press(KEY_A), "test_kb")
        app.event_manager.handle_raw_event(_release(KEY_A), "test_kb")
        assert app.state_manager.state == State.TYPING

        # Mouse click (BTN_LEFT = 272)
        app.event_manager.handle_raw_event(_press(272), "test_kb")

        assert app.state_manager.state == State.IDLE


class TestNavigationResetsState:
    """7. Navigation keys (Enter, Tab, Arrow) reset state to IDLE."""

    def test_enter_resets_to_idle(self, tmp_path):
        """Enter key should reset state to IDLE."""
        app = _make_app(tmp_path)
        app._wire_event_bus()

        # Type to enter TYPING
        app.event_manager.handle_raw_event(_press(KEY_A), "test_kb")
        app.event_manager.handle_raw_event(_release(KEY_A), "test_kb")
        assert app.state_manager.state == State.TYPING

        # Release Enter (navigation key handling is on release)
        app.event_manager.handle_raw_event(_press(KEY_ENTER_CODE), "test_kb")
        app.event_manager.handle_raw_event(_release(KEY_ENTER_CODE), "test_kb")

        assert app.state_manager.state == State.IDLE

    def test_arrow_resets_to_idle(self, tmp_path):
        """Arrow key should reset state to IDLE."""
        app = _make_app(tmp_path)
        app._wire_event_bus()

        # Type to enter TYPING
        app.event_manager.handle_raw_event(_press(KEY_A), "test_kb")
        app.event_manager.handle_raw_event(_release(KEY_A), "test_kb")
        assert app.state_manager.state == State.TYPING

        # Release Left Arrow (navigation)
        app.event_manager.handle_raw_event(_press(KEY_LEFT_ARROW), "test_kb")
        app.event_manager.handle_raw_event(_release(KEY_LEFT_ARROW), "test_kb")

        assert app.state_manager.state == State.IDLE


class TestGracefulShutdown:
    """8. app.stop() does not crash."""

    def test_stop_safe_without_init(self, tmp_path):
        """stop() should be safe to call even without _init_platform()."""
        app = _make_app(tmp_path)
        app.stop()  # Should not raise

    def test_stop_safe_after_wiring(self, tmp_path):
        """stop() should be safe after _wire_event_bus()."""
        app = _make_app(tmp_path)
        app._wire_event_bus()
        app.stop()
        assert app._running is False


class TestDictionaryIntegration:
    """9. AutoDetector + TextConverter integration."""

    def test_should_convert_ghbdtn_en(self):
        """should_convert('ghbdtn', 'en') should return True — it's 'привет' typed in EN layout."""
        from lswitch.intelligence.dictionary_service import DictionaryService
        from lswitch.intelligence.ngram_analyzer import NgramAnalyzer
        from lswitch.intelligence.auto_detector import AutoDetector

        dictionary = DictionaryService()
        ngrams = NgramAnalyzer()
        detector = AutoDetector(dictionary=dictionary, ngrams=ngrams)

        should, reason = detector.should_convert("ghbdtn", "en")
        assert should is True, f"Expected True, got {should}: {reason}"

    def test_convert_text_ghbdtn(self):
        """convert_text('ghbdtn') should produce 'привет'."""
        result = convert_text("ghbdtn")
        assert result == "привет"


class TestConfigManagerRoundtrip:
    """10. ConfigManager save → reload → values preserved."""

    def test_save_and_reload_preserves_values(self, tmp_path):
        """Saving config and reloading should preserve all values."""
        cfg_path = str(tmp_path / "cfg.json")

        # Create and modify config
        cm = ConfigManager(config_path=cfg_path, debug=True)
        cm.set("auto_switch", True)
        cm.set("auto_switch_threshold", 42)
        cm.set("double_click_timeout", 0.5)
        assert cm.save() is True

        # Reload into a new instance
        cm2 = ConfigManager(config_path=cfg_path, debug=True)
        assert cm2.get("auto_switch") is True
        assert cm2.get("auto_switch_threshold") == 42
        assert cm2.get("double_click_timeout") == 0.5

    def test_reset_to_defaults_works(self, tmp_path):
        """reset_to_defaults should restore DEFAULT_CONFIG values."""
        cfg_path = str(tmp_path / "cfg2.json")
        cm = ConfigManager(config_path=cfg_path, debug=True)
        cm.set("auto_switch", True)
        cm.reset_to_defaults()
        assert cm.get("auto_switch") == DEFAULT_CONFIG["auto_switch"]
