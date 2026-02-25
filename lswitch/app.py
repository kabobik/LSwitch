"""LSwitchApp — main application class, unifies service and GUI."""

from __future__ import annotations

import logging
import os
import signal
import sys
import threading

import lswitch.log  # registers TRACE level and logger.trace()
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
        self.auto_detector = None

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
        from lswitch.intelligence.ngram_analyzer import NgramAnalyzer
        from lswitch.intelligence.auto_detector import AutoDetector

        dictionary = DictionaryService()
        ngrams = NgramAnalyzer()
        self.auto_detector = AutoDetector(dictionary=dictionary, ngrams=ngrams)

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
        from lswitch.core.event_manager import SHIFT_KEYS, KEY_BACKSPACE, KEY_SPACE

        data = event.data
        logger.trace(  # type: ignore[attr-defined]
            "KeyPress: code=%d dev=%s | state=%s buf=%d",
            data.code, data.device_name,
            self.state_manager.state.name,
            self.state_manager.context.chars_in_buffer,
        )
        if data.code in SHIFT_KEYS:
            self.state_manager.on_shift_down()
        elif data.code == KEY_BACKSPACE:
            # Backspace removes last event from buffer (don't append it)
            ctx = self.state_manager.context
            if ctx.event_buffer:
                ctx.event_buffer.pop()
            ctx.backspace_repeats = 0
        elif data.code == KEY_SPACE:
            # Word boundary — try auto-conversion if enabled
            if self.auto_detector and self.config.get('auto_switch'):
                if self._try_auto_conversion_at_space():
                    return  # space was consumed by auto-conversion
            # Normal space: add to buffer
            self.state_manager.on_key_press(data.code)
            self.state_manager.context.chars_in_buffer += 1
            self.state_manager.context.event_buffer.append(data)
            self.state_manager.context.backspace_repeats = 0
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
            ctx = self.state_manager.context
            ctx.backspace_repeats += 1
            # Each auto-repeat removes one more char from the event buffer
            if ctx.event_buffer:
                ctx.event_buffer.pop()
            if ctx.chars_in_buffer > 0:
                ctx.chars_in_buffer -= 1
            if ctx.backspace_repeats >= 3:
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
    # Auto-conversion (space-triggered, AutoDetector)
    # ------------------------------------------------------------------

    def _try_auto_conversion_at_space(self) -> bool:
        """Check and perform auto-conversion at Space word boundary.

        Returns True if conversion was performed (Space consumed).
        Returns False if no conversion needed (Space should be added to buffer).

        ``auto_switch_threshold`` — minimum number of chars typed since last
        reset before auto-conversion activates.  Set to 0 (default) to
        convert from the very first word.  Increase to avoid false-positives
        at the start of a field (e.g., 5 = activate after ≥5 chars typed).
        """
        MIN_WORD_LEN = 1

        ctx = self.state_manager.context
        if ctx.chars_in_buffer == 0:
            return False

        # Buffer warmup: don't activate until enough chars have been typed
        threshold = self.config.get('auto_switch_threshold', 0)
        if ctx.chars_in_buffer < threshold:
            if self.debug:
                logger.debug(
                    "Auto-conv skipped: buf=%d < threshold=%d",
                    ctx.chars_in_buffer, threshold,
                )
            return False

        # Get current layout FIRST — needed for correct char extraction below
        try:
            current_layout_info = self.xkb.get_current_layout() if self.xkb else None
        except Exception:
            return False

        current_lang = self._layout_to_lang(current_layout_info)

        # Extract last word using actual XKB layout mapping.
        # This prevents false truncation on RU keys that map to non-alpha EN
        # chars (б→, ю→. ж→; etc.) which would split the word mid-way.
        word, word_events = self._extract_last_word_events(current_layout_info)

        # Skip very short words
        if not word or len(word) < MIN_WORD_LEN:
            if self.debug:
                logger.debug("Auto-conv skipped: word %r too short (%d chars)", word, len(word) if word else 0)
            return False

        # Ask AutoDetector
        try:
            should, reason = self.auto_detector.should_convert(word, current_lang)
        except Exception as exc:
            logger.warning("AutoDetector error: %s", exc)
            return False

        if not should:
            return False

        direction = "en_to_ru" if current_lang == "en" else "ru_to_en"
        logger.info("Auto-convert at space: '%s' → %s (%s)", word, direction, reason)
        self._do_auto_conversion_at_space(len(word_events), word_events, direction)
        return True

    def _extract_last_word_events(self, current_layout=None) -> "tuple[str, list]":
        """Extract events for the last typed word from event_buffer.

        Scans backwards until a space or non-alpha character is found.
        Returns (word_str, word_events_in_order).

        When ``current_layout`` (a LayoutInfo) is provided and ``self.xkb`` is
        available, characters are resolved via the real XKB mapping so that
        Cyrillic letters on a RU layout are returned as Cyrillic (not as their
        EN physical-key equivalents, where б→, and ю→. are non-alpha and would
        truncate the word prematurely).
        """
        from lswitch.core.event_manager import KEY_SPACE
        from lswitch.input.key_mapper import keycode_to_char as _kc_en

        # Chars in EN layout that map to Cyrillic letters (e.g. ',' → 'б').
        # These keys must NOT break word scanning when the user is typing
        # Russian on the wrong EN keyboard.
        from lswitch.intelligence.maps import EN_TO_RU as _EN_TO_RU
        _is_cyrillic_key = lambda c: bool(c and not c.isalpha() and _EN_TO_RU.get(c.lower(), '').isalpha())

        word_events: list = []
        chars: list[str] = []
        for ev in reversed(self.state_manager.context.event_buffer):
            if ev.code == KEY_SPACE:
                break
            # Prefer actual XKB mapping for the current layout
            if current_layout is not None and self.xkb is not None:
                ch = self.xkb.keycode_to_char(ev.code, current_layout)
            else:
                ch = _kc_en(ev.code)
            if ch and ch.isalpha():
                word_events.append(ev)
                chars.append(ch)
            elif _is_cyrillic_key(ch):
                # On EN layout this key produces punctuation, but on RU it's a
                # Cyrillic letter (е.g. kc51 → ',' in EN, but 'б' in RU).
                # Include it so the full translit sequence is preserved for
                # AutoDetector ("hf,jnftn" → "работает" after conversion).
                word_events.append(ev)
                chars.append(ch)
            else:
                break  # genuine boundary: punctuation, digit, or unresolved key

        word_events.reverse()
        chars.reverse()
        return "".join(chars), word_events

    def _layout_to_lang(self, layout_info) -> str:
        """Map LayoutInfo to a 2-letter language code ('en' or 'ru')."""
        if layout_info is None:
            return "en"
        name = layout_info.name.lower()
        if name.startswith("ru") or name in ("russian", "россия"):
            return "ru"
        return "en"

    def _do_auto_conversion_at_space(
        self, word_len: int, word_events: list, direction: str
    ) -> None:
        """Perform auto-conversion: delete (word + space), retype in target layout, add space.

        The Space key was already delivered to the active application before LSwitch processed
        it (passive monitoring), so we must also delete that extra space character via backspace.
        """
        from lswitch.core.event_manager import KEY_BACKSPACE, KEY_SPACE
        from lswitch.core.states import State

        ctx = self.state_manager.context

        try:
            # Find target layout
            target_lang = "ru" if direction == "en_to_ru" else "en"
            try:
                layouts = self.xkb.get_layouts() if self.xkb else []
                target = next(
                    (l for l in layouts if l.name.lower().startswith(target_lang)),
                    None,
                )
            except Exception:
                target = None

            # Delete: word_len chars + 1 for the space that already landed in the app
            self.virtual_kb.tap_key(KEY_BACKSPACE, n_times=word_len + 1)

            # Switch to target layout
            if target and self.xkb:
                self.xkb.switch_layout(target=target)

            # Replay original keycodes in the new layout (produces converted text)
            self.virtual_kb.replay_events(word_events)

            # Re-add the space
            self.virtual_kb.tap_key(KEY_SPACE)

        except Exception as exc:
            logger.error("Auto-conversion at space failed: %s", exc)
        finally:
            ctx.reset()
            ctx.state = State.IDLE

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

        if self.headless:
            self._run_evdev_loop()
        else:
            self._run_with_gui()

    def _run_evdev_loop(self):
        """Evdev event loop (blocking, main thread)."""
        try:
            while self._running:
                for device, event in self.device_manager.get_events(timeout=0.1):
                    self.event_manager.handle_raw_event(event, device.name)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def _run_with_gui(self):
        """Run evdev in background thread + Qt event loop in main thread."""
        from PyQt5.QtWidgets import QApplication
        from lswitch.core.events import EventType
        from lswitch.ui.tray_icon import TrayIcon
        from lswitch.ui.context_menu import ContextMenu

        qt_app = QApplication.instance() or QApplication(sys.argv)

        # Build tray icon
        tray = TrayIcon(event_bus=self.event_bus, config=self.config, app=qt_app)

        # Build context menu
        menu_obj = ContextMenu(config=self.config, event_bus=self.event_bus)
        menu = menu_obj.build()
        tray.set_context_menu(menu)

        # Show current layout
        try:
            current = self.xkb.get_current_layout() if self.xkb else None
            tray.set_layout(current.name if current else "")
        except Exception:
            pass

        tray.show()

        # APP_QUIT → exit Qt event loop
        def _on_quit(event):
            qt_app.quit()
        self.event_bus.subscribe(EventType.APP_QUIT, _on_quit)

        # Evdev loop in background thread
        def _evdev_thread():
            try:
                while self._running:
                    for device, event in self.device_manager.get_events(timeout=0.1):
                        self.event_manager.handle_raw_event(event, device.name)
            except Exception as exc:
                logger.error("Evdev thread error: %s", exc)
            finally:
                qt_app.quit()

        t = threading.Thread(target=_evdev_thread, daemon=True, name="evdev-loop")
        t.start()

        try:
            qt_app.exec_()
        finally:
            tray.cleanup()
            self.stop()
            t.join(timeout=2.0)

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
