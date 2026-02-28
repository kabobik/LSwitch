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


class _SelectionLoggerThread(threading.Thread):
    """Background daemon thread polling X11 PRIMARY selection every 500ms.

    Logs changes at DEBUG level, and notifies ``LSwitchApp`` via
    ``on_primary_changed`` callback so the baseline is always up to date.
    Does NOT read PRIMARY at click time (avoids the race condition).
    Always runs when a selection adapter is available.
    """

    def __init__(self, selection_adapter, on_primary_changed=None):
        super().__init__(daemon=True, name="sel-logger")
        self._selection = selection_adapter
        self._running = True
        self._prev_text: str = ""
        self._prev_owner_id: int = 0
        self._on_primary_changed = on_primary_changed  # callback(text, owner_id)

    def run(self):
        import time
        _logger = logging.getLogger(__name__)
        while self._running:
            try:
                info = self._selection.get_selection()
                text_changed = info.text != self._prev_text
                owner_changed = info.owner_id != self._prev_owner_id
                if text_changed or owner_changed:
                    self._prev_text = info.text
                    self._prev_owner_id = info.owner_id
                    _logger.debug(
                        "PRIMARY changed: text=%r owner=0x%x",
                        info.text[:80] if info.text else "", info.owner_id,
                    )
                    if self._on_primary_changed:
                        self._on_primary_changed(info.text, info.owner_id)
            except Exception as exc:
                _logger.trace("sel-logger error: %s", exc)  # type: ignore[attr-defined]
            time.sleep(0.5)

    def stop(self):
        self._running = False


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
        self.user_dict = None
        self._last_auto_marker = None
        self.__selection_valid: bool = False
        self._prev_sel_text: str = ""
        self._prev_sel_owner_id: int = 0
        self._last_retype_events: list = []   # sticky buffer for repeat Shift+Shift
        self._selection_logger: _SelectionLoggerThread | None = None

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

        # UserDictionary: self-learning word weights
        if self.config.get('user_dict_enabled'):
            from lswitch.intelligence.user_dictionary import UserDictionary
            self.user_dict = UserDictionary()

        self.auto_detector = AutoDetector(
            dictionary=dictionary, ngrams=ngrams, user_dict=self.user_dict,
        )

        self.conversion_engine = ConversionEngine(
            xkb=self.xkb,
            selection=self.selection,
            virtual_kb=self.virtual_kb,
            dictionary=dictionary,
            system=self.system,
            user_dict=self.user_dict,
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
        self.event_bus.subscribe(EventType.MOUSE_RELEASE, self._on_mouse_release)

    # ------------------------------------------------------------------
    # Event callbacks
    # ------------------------------------------------------------------

    @property
    def _selection_valid(self) -> bool:
        return self.__selection_valid

    @_selection_valid.setter
    def _selection_valid(self, value: bool) -> None:
        if value != self.__selection_valid:
            logger.debug(
                "fresh=%s → %s",
                self.__selection_valid, value,
            )
            self.__selection_valid = value
        # Log at TRACE every assignment and its source (guarded to avoid extract_stack overhead)
        if logger.isEnabledFor(5):  # TRACE = 5
            import traceback as _tb
            caller = _tb.extract_stack(limit=3)[-2]
            logger.trace(  # type: ignore[attr-defined]
                "fresh=%s (set by %s:%d)",
                self.__selection_valid, caller.name, caller.lineno,
            )

    def _on_key_press(self, event):
        from lswitch.core.event_manager import SHIFT_KEYS, KEY_BACKSPACE, KEY_SPACE, MODIFIER_KEYS
        from lswitch.input.key_mapper import keycode_to_char

        data = event.data
        logger.trace(  # type: ignore[attr-defined]
            "KeyPress: code=%d dev=%s | state=%s buf=%d",
            data.code, data.device_name,
            self.state_manager.state.name,
            self.state_manager.context.chars_in_buffer,
        )
        if data.code in SHIFT_KEYS:
            self.state_manager.on_shift_down()
        elif data.code in MODIFIER_KEYS:
            pass  # modifiers don't produce text — ignore entirely
        elif data.code == KEY_BACKSPACE:
            # Backspace removes last event from buffer (don't append it)
            ctx = self.state_manager.context
            if ctx.event_buffer:
                ctx.event_buffer.pop()
            logger.trace(  # type: ignore[attr-defined]
                "Buffer -[BS] → %r (%d chars)",
                self._decode_buffer(),
                self.state_manager.context.chars_in_buffer,
            )
            ctx.backspace_repeats = 0
            self._selection_valid = False
            self._last_retype_events = []
        elif data.code == KEY_SPACE:
            # Word boundary — try auto-conversion if enabled
            if self.auto_detector and self.config.get('auto_switch'):
                if self._try_auto_conversion_at_space():
                    return  # space was consumed by auto-conversion
            # Normal space: add to buffer
            self.state_manager.on_key_press(data.code)
            self.state_manager.context.chars_in_buffer += 1
            data.shifted = self.state_manager.context.shift_pressed
            self.state_manager.context.event_buffer.append(data)
            logger.trace(  # type: ignore[attr-defined]
                "Buffer +[%d:%s] → %r (%d chars)",
                data.code,
                keycode_to_char(data.code, shift=data.shifted) or '?',
                self._decode_buffer(),
                self.state_manager.context.chars_in_buffer,
            )
            self.state_manager.context.backspace_repeats = 0
            self._selection_valid = False
            self._last_retype_events = []
        else:
            self.state_manager.on_key_press(data.code)
            self.state_manager.context.chars_in_buffer += 1
            data.shifted = self.state_manager.context.shift_pressed
            self.state_manager.context.event_buffer.append(data)
            logger.trace(  # type: ignore[attr-defined]
                "Buffer +[%d:%s] → %r (%d chars)",
                data.code,
                keycode_to_char(data.code, shift=data.shifted) or '?',
                self._decode_buffer(),
                self.state_manager.context.chars_in_buffer,
            )
            self.state_manager.context.backspace_repeats = 0
            self._selection_valid = False
            self._last_retype_events = []

    def _on_key_release(self, event):
        from lswitch.core.event_manager import (
            SHIFT_KEYS, NAVIGATION_KEYS, KEY_BACKSPACE, KEY_ENTER,
        )

        data = event.data
        if data.code in SHIFT_KEYS:
            is_double = self.state_manager.on_shift_up()
            if is_double:
                logger.debug(
                    "DoubleShift detected → _do_conversion() "
                    "[sel_valid=%s, chars=%d]",
                    self._selection_valid,
                    self.state_manager.context.chars_in_buffer,
                )
                self._do_conversion()
        elif data.code in NAVIGATION_KEYS:
            self._last_auto_marker = None
            self._selection_valid = False
            self._last_retype_events = []
            self.state_manager.on_navigation()
        elif data.code == KEY_ENTER:
            self._last_auto_marker = None
            self._selection_valid = False
            self._last_retype_events = []
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
            logger.trace(  # type: ignore[attr-defined]
                "Buffer -[BS repeat] → %r (%d chars)",
                self._decode_buffer(),
                len(self.state_manager.context.event_buffer),
            )
            if ctx.chars_in_buffer > 0:
                ctx.chars_in_buffer -= 1
            if ctx.backspace_repeats >= 3:
                self.state_manager.on_backspace_hold()

    def _on_mouse_click(self, event):
        self._last_auto_marker = None
        self._selection_valid = False
        self._last_retype_events = []
        # Do NOT read PRIMARY here — xclip -o sends XConvertSelection which
        # can cause the selection owner to drop PRIMARY when the click has
        # just deselected text (race condition on Cinnamon/GTK apps).
        # Baseline will be updated by _on_mouse_release instead.
        self.state_manager.on_mouse_click()

    def _on_mouse_release(self, event):
        """Mouse button release — potential end of drag-select.

        Read PRIMARY and compare with baseline.  If content changed,
        a drag-select just happened — mark selection as fresh.
        Always update baseline so the next click/release cycle has
        an accurate reference.

        Reading PRIMARY at release time is safe — the GTK application
        has already finished processing the button-release event and
        committed the selection to PRIMARY.
        """
        if self.selection is None:
            return
        try:
            info = self.selection.get_selection()
            old_text = self._prev_sel_text
            old_owner = self._prev_sel_owner_id
            # Always update baseline on release
            self._prev_sel_text = info.text or ""
            self._prev_sel_owner_id = info.owner_id
            # If PRIMARY changed → fresh selection (drag-select happened)
            if info.text and (info.text != old_text or
                              (info.owner_id != old_owner and info.owner_id != 0)):
                self._selection_valid = True
                logger.debug(
                    "MouseRelease: fresh selection — text=%r owner=0x%x",
                    info.text[:50] if info.text else "", info.owner_id,
                )
            else:
                logger.trace(  # type: ignore[attr-defined]
                    "MouseRelease: PRIMARY unchanged — text=%r",
                    info.text[:50] if info.text else "",
                )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _decode_buffer(self, events: list | None = None) -> str:
        """Decode event buffer to human-readable string of characters."""
        from lswitch.input.key_mapper import keycode_to_char
        if events is None:
            events = self.state_manager.context.event_buffer
        chars = []
        for e in events:
            ch = keycode_to_char(e.code, shift=getattr(e, 'shifted', False))
            chars.append(ch if ch else '?')
        return "".join(chars)

    # ------------------------------------------------------------------
    # Selection validity tracking
    # ------------------------------------------------------------------

    def _on_poller_primary_changed(self, text: str, owner_id: int) -> None:
        """Called by _SelectionLoggerThread when PRIMARY changes.

        Sets fresh=True so the next Shift+Shift will use SelectionMode.
        Does NOT update baseline (_prev_sel_text / _prev_sel_owner_id) —
        baseline is maintained by _on_mouse_release and _do_conversion.
        """
        self._selection_valid = True
        logger.debug(
            "Poller: PRIMARY changed, fresh=True — text=%r owner=0x%x",
            text[:50] if text else "", owner_id,
        )

    # ------------------------------------------------------------------
    # Conversion
    # ------------------------------------------------------------------

    def _do_conversion(self):
        """Trigger conversion if state machine is in CONVERTING state.

        User-dict learning logic:
          A) Shift+Shift right after auto-conversion (undo):
             _last_auto_marker is set, event_buffer is empty (reset by auto-conv).
             → add_correction(typed_word, typed_lang)  — weight -1
          B) Pure manual Shift+Shift (no prior auto-conversion):
             _last_auto_marker is None, event_buffer has the typed chars.
             → add_confirmation(typed_word, typed_lang)  — weight +1
             Weight accumulates across sessions; once |weight| >= min_weight
             AutoDetector will handle this word automatically.
        """
        from lswitch.core.states import State

        if self.state_manager.state != State.CONVERTING:
            return

        # --- Extract typed word from buffer BEFORE convert() clears it ---
        # Only relevant for Case B (manual conversion); Case A buffer is already empty.
        manual_word: str = ""
        manual_lang: str = ""
        if self.user_dict and self.state_manager.context.chars_in_buffer > 0:
            try:
                layout_info = self.xkb.get_current_layout() if self.xkb else None
                manual_lang = self._layout_to_lang(layout_info)
                manual_word, _ = self._extract_last_word_events(layout_info)
            except Exception:
                pass

        # --- Case A: undo of recent auto-conversion → penalise ---
        if self._last_auto_marker is not None:
            marker = self._last_auto_marker
            if self.user_dict:
                self.user_dict.add_correction(
                    marker['word'], marker['lang'], debug=self.debug,
                )
                logger.info(
                    "Correction: '%s' (%s) — weight -1",
                    marker['word'], marker['lang'],
                )
            self._last_auto_marker = None

        # --- Case B: pure manual conversion → confirm this word needs switching ---
        elif manual_word and manual_lang and self.user_dict:
            self.user_dict.add_confirmation(manual_word, manual_lang, debug=self.debug)
            logger.info(
                "Manual conversion: '%s' (%s) — weight +1",
                manual_word, manual_lang,
            )

        try:
            # Save buffer before convert (reset() will clear it)
            saved_events = list(self.state_manager.context.event_buffer)
            saved_count = self.state_manager.context.chars_in_buffer

            # Restore sticky buffer if context buffer is empty (repeat Shift+Shift)
            if saved_count == 0 and self._last_retype_events:
                saved_events = list(self._last_retype_events)
                saved_count = len(saved_events)
                self.state_manager.context.event_buffer = list(saved_events)
                self.state_manager.context.chars_in_buffer = saved_count
                logger.debug(
                    "DoConversion: restored sticky buffer → chars=%d",
                    saved_count,
                )

            # ---- Trim to last word for retype mode ----
            # If buffer has multiple words (contains space), trim to last word only.
            # Selection mode uses clipboard, not buffer — so trimming applies only
            # when retype would be chosen (chars > 0 and selection not valid).
            if saved_count > 0 and not self._selection_valid:
                try:
                    _, last_word_events = self._extract_last_word_events(
                        self.xkb.get_current_layout() if self.xkb else None
                    )
                    if last_word_events and len(last_word_events) < saved_count:
                        logger.debug(
                            "DoConversion: trim buffer to last word → %d events (was %d)",
                            len(last_word_events), saved_count,
                        )
                        saved_events = last_word_events
                        saved_count = len(last_word_events)
                        self.state_manager.context.event_buffer = list(last_word_events)
                        self.state_manager.context.chars_in_buffer = saved_count
                except Exception as exc:
                    logger.debug("DoConversion: trim skipped: %s", exc)

            logger.debug(
                "DoConversion: selection_valid=%s, chars_in_buffer=%d, "
                "saved_events=%d, sticky=%d, buffer=%r",
                self._selection_valid, saved_count,
                len(saved_events), len(self._last_retype_events),
                self._decode_buffer(saved_events),
            )

            success = self.conversion_engine.convert(
                self.state_manager.context,
                selection_valid=self._selection_valid,
            )

            # Remember events for potential repeat retype
            if success and saved_count > 0 and not self._selection_valid:
                self._last_retype_events = saved_events
            else:
                self._last_retype_events = []
        finally:
            # Update baseline to prevent re-conversion of same text
            if self.selection is not None:
                try:
                    info = self.selection.get_selection()
                    self._prev_sel_text = info.text or ""
                    self._prev_sel_owner_id = info.owner_id
                except Exception:
                    pass
            self._selection_valid = False  # consumed
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

        logger.debug(
            "AutoConv: extracted word=%r (%d chars), lang=%s, buf=%d",
            word, len(word) if word else 0, current_lang,
            ctx.chars_in_buffer,
        )

        # Skip very short words
        if not word or len(word) < MIN_WORD_LEN:
            logger.debug("Auto-conv skipped: word %r too short (%d chars)", word, len(word) if word else 0)
            return False

        # Ask AutoDetector
        try:
            should, reason = self.auto_detector.should_convert(word, current_lang)
        except Exception as exc:
            logger.warning("AutoDetector error: %s", exc)
            return False

        # Previous auto-conversion was accepted (user kept typing → next space)
        if self._last_auto_marker is not None and self.user_dict:
            old = self._last_auto_marker
            self.user_dict.add_confirmation(old['word'], old['lang'], debug=self.debug)
            self._last_auto_marker = None

        if not should:
            return False

        direction = "en_to_ru" if current_lang == "en" else "ru_to_en"
        logger.info("Auto-convert at space: '%s' → %s (%s)", word, direction, reason)
        self._do_auto_conversion_at_space(
            len(word_events), word_events, direction,
            orig_word=word, orig_lang=current_lang,
        )
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
        self, word_len: int, word_events: list, direction: str,
        orig_word: str = "", orig_lang: str = "",
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
            # Save marker BEFORE reset so correction can be detected later
            import time as _time
            if orig_word:
                self._last_auto_marker = {
                    'word': orig_word,
                    'direction': direction,
                    'lang': orig_lang,
                    'time': _time.time(),
                }
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

        if self.selection:
            self._selection_logger = _SelectionLoggerThread(
                self.selection,
                on_primary_changed=self._on_poller_primary_changed,
            )
            self._selection_logger.start()

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
        menu_obj = ContextMenu(config=self.config, event_bus=self.event_bus, app=self)
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
        if self._selection_logger:
            self._selection_logger.stop()
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
