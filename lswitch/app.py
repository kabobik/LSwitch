"""LSwitchApp — main application class, unifies service and GUI."""

from __future__ import annotations

import logging
import os
import signal

from lswitch.config import ConfigManager

logger = logging.getLogger(__name__)
from lswitch.core.event_bus import EventBus
from lswitch.core.state_manager import StateManager
from lswitch.core.conversion_engine import ConversionEngine
from lswitch.core.event_manager import EventManager


class LSwitchApp:
    """Single-process application combining input daemon and tray GUI.

    Modes:
        headless=True  — no GUI, runs as a background service
        headless=False — with tray icon (default)

    ``_init_platform()`` is separated from ``__init__`` so that tests
    can inject mocks without touching real X11 / evdev resources.
    """

    def __init__(
        self,
        headless: bool = False,
        debug: bool = False,
        config_path: str | None = None,
    ):
        self.headless = headless
        self.debug = debug
        self._running = False

        # Configuration
        self.config = ConfigManager(config_path=config_path, debug=debug)

        # Core components
        self.event_bus = EventBus()
        self.state_manager = StateManager(
            double_click_timeout=self.config.get('double_click_timeout', 0.3),
            debug=debug,
        )

        # Platform adapters — created by _init_platform()
        self.xkb = None
        self.selection = None
        self.system = None
        self.virtual_kb = None
        self.device_manager = None
        self.conversion_engine = None
        self.event_manager = None
        self._udev_monitor = None

    # ------------------------------------------------------------------
    # Platform initialisation (lazy — for testability)
    # ------------------------------------------------------------------

    def _init_platform(self):
        """Initialise platform components.

        Separated from ``__init__`` so that tests can substitute mocks
        without requiring real X11 / evdev.
        """
        from lswitch.platform.subprocess_impl import SubprocessSystemAdapter

        self.system = SubprocessSystemAdapter(debug=self.debug)

        try:
            from lswitch.platform.xkb_adapter import X11XKBAdapter
            self.xkb = X11XKBAdapter(debug=self.debug)
        except Exception:
            raise RuntimeError("X11 недоступен — XKBAdapter не удалось инициализировать")

        try:
            from lswitch.platform.selection_adapter import X11SelectionAdapter
            self.selection = X11SelectionAdapter(system=self.system, debug=self.debug)
        except Exception:
            raise RuntimeError("X11 SelectionAdapter не удалось инициализировать")

        try:
            from lswitch.input.virtual_keyboard import VirtualKeyboard
            self.virtual_kb = VirtualKeyboard(debug=self.debug)
        except Exception:
            raise RuntimeError("VirtualKeyboard (UInput) не удалось создать")

        from lswitch.intelligence.dictionary_service import DictionaryService

        dictionary = DictionaryService()

        self.conversion_engine = ConversionEngine(
            xkb=self.xkb,
            selection=self.selection,
            virtual_kb=self.virtual_kb,
            dictionary=dictionary,
            system=self.system,
            debug=self.debug,
        )

        self.event_manager = EventManager(self.event_bus, debug=self.debug)

        # Input devices
        from lswitch.input.device_manager import DeviceManager
        from lswitch.input.virtual_keyboard import VirtualKeyboard as _VK

        self.device_manager = DeviceManager(debug=self.debug)
        if self.virtual_kb:
            self.device_manager.set_virtual_kb_name(_VK.DEVICE_NAME)

        # Udev hot-plug monitor
        from lswitch.input.udev_monitor import UdevMonitor

        self._udev_monitor = UdevMonitor(
            on_added=self.device_manager._try_add_device,
            on_removed=lambda path: self.device_manager.remove_device(path),
        )

    # ------------------------------------------------------------------
    # Event bus wiring
    # ------------------------------------------------------------------

    def _wire_event_bus(self):
        """Subscribe event handlers to the EventBus."""
        from lswitch.core.events import EventType

        self.event_bus.subscribe(EventType.KEY_PRESS, self._on_key_press)
        self.event_bus.subscribe(EventType.KEY_RELEASE, self._on_key_release)
        self.event_bus.subscribe(EventType.KEY_REPEAT, self._on_key_repeat)
        self.event_bus.subscribe(EventType.MOUSE_CLICK, self._on_mouse_click)

    # ------------------------------------------------------------------
    # Event callbacks
    # ------------------------------------------------------------------

    def _on_key_press(self, event):
        from lswitch.core.event_manager import SHIFT_KEYS

        data = event.data
        if data.code in SHIFT_KEYS:
            self.state_manager.on_shift_down()
        else:
            self.state_manager.on_key_press(data.code)
            self.state_manager.context.chars_in_buffer += 1
            self.state_manager.context.event_buffer.append(data)
            self.state_manager.context.backspace_repeats = 0

    def _on_key_release(self, event):
        from lswitch.core.event_manager import (
            SHIFT_KEYS, NAVIGATION_KEYS, KEY_BACKSPACE, KEY_ENTER,
        )

        data = event.data
        if data.code in SHIFT_KEYS:
            is_double = self.state_manager.on_shift_up()
            if is_double:
                self._do_conversion()
        elif data.code in NAVIGATION_KEYS:
            self.state_manager.on_navigation()
        elif data.code == KEY_ENTER:
            self.state_manager.on_navigation()
        elif data.code == KEY_BACKSPACE:
            self.state_manager.context.backspace_repeats = 0
            if self.state_manager.context.chars_in_buffer > 0:
                self.state_manager.context.chars_in_buffer -= 1

    def _on_key_repeat(self, event):
        from lswitch.core.event_manager import KEY_BACKSPACE

        data = event.data
        if data.code == KEY_BACKSPACE:
            self.state_manager.context.backspace_repeats += 1
            if self.state_manager.context.backspace_repeats >= 3:
                self.state_manager.on_backspace_hold()

    def _on_mouse_click(self, event):
        self.state_manager.on_mouse_click()

    # ------------------------------------------------------------------
    # Conversion
    # ------------------------------------------------------------------

    def _do_conversion(self):
        """Trigger conversion if state machine is in CONVERTING state."""
        from lswitch.core.states import State

        if self.state_manager.state != State.CONVERTING:
            return
        try:
            self.conversion_engine.convert(self.state_manager.context)
        finally:
            self.state_manager.on_conversion_complete()

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self):
        """Blocking main event loop."""
        if not os.environ.get('DISPLAY') and not os.environ.get('WAYLAND_DISPLAY'):
            raise RuntimeError(
                "LSwitch требует X11 (переменная DISPLAY не установлена). "
                "Для systemd: добавьте ImportEnvironment=DISPLAY в .service файл."
            )

        self._init_platform()
        self._wire_event_bus()

        count = self.device_manager.scan_devices()

        if self._udev_monitor:
            self._udev_monitor.start()

        self._running = True

        logger.info("LSwitch 2.0 запущен (headless=%s, %d устройств)", self.headless, count)

        def _reload_handler(signum, frame):
            self.config.reload()
            if self.debug:
                logger.debug("Config reloaded via SIGHUP")
        signal.signal(signal.SIGHUP, _reload_handler)

        try:
            while self._running:
                for device, event in self.device_manager.get_events(timeout=0.1):
                    self.event_manager.handle_raw_event(event, device.name)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def stop(self):
        """Graceful shutdown — safe to call multiple times."""
        self._running = False
        if self._udev_monitor:
            try:
                self._udev_monitor.stop()
            except Exception:
                pass
        if self.device_manager:
            try:
                self.device_manager.close()
            except Exception:
                pass
        if self.virtual_kb:
            try:
                self.virtual_kb.close()
            except Exception:
                pass
        if self.xkb and hasattr(self.xkb, 'close'):
            try:
                self.xkb.close()
            except Exception:
                pass
