"""Input handling for LSwitch.

Encapsulates low-level keyboard event handling, double-shift detection and
replaying events. Designed to be instantiated with a reference to the
`LSwitch` instance so it can operate on its state and call higher-level
services (conversion, selection, user_dict, etc.).
"""
from __future__ import annotations

import time
from . import system as system
import collections
import threading

try:
    from evdev import ecodes
except Exception:
    # Provide minimal fallback to avoid import errors in tests
    class _E: pass
    ecodes = _E()


class InputHandler:
    def __init__(self, lswitch):
        self.ls = lswitch
        # Track whether we've seen a real Shift press recently so we can
        # distinguish stray release events from legitimate user actions.
        self._shift_pressed = False
        self._shift_last_press_time = 0.0

    def replay_events(self, events):
        """Replays events into the virtual keyboard device."""
        shift_codes = {getattr(ecodes, 'KEY_LEFTSHIFT', None), getattr(ecodes, 'KEY_RIGHTSHIFT', None)}
        if self.ls.config.get('debug'):
            shift_events = [e for e in events if getattr(e, 'code', None) in shift_codes]
            letter_events = [e for e in events if getattr(e, 'code', None) not in shift_codes and getattr(e, 'value', None) == 0]
            print(f"  Replaying: {len(events)} events ({len(shift_events)} Shift, {len(letter_events)} letters)", flush=True)
            print("  First events:", flush=True)
            for i, e in enumerate(events[:5]):
                shift_str = "SHIFT" if getattr(e, 'code', None) in shift_codes else f"KEY_{getattr(e, 'code', None)}"
                val_str = "↓" if getattr(e, 'value', None) == 1 else "↑"
                print(f"    {i+1}. {shift_str} {val_str}", flush=True)

        for event in events:
            try:
                self.ls.fake_kb.write(getattr(ecodes, 'EV_KEY', 1), event.code, event.value)
                self.ls.fake_kb.syn()
            except Exception:
                # best-effort
                pass

    def on_double_shift(self):
        """Handle double shift event. This method is callable from tests (LSwitch.on_double_shift delegates to it)."""
        try:
            has_sel = False
            try:
                has_sel = self.ls.has_selection()
            except Exception:
                has_sel = False

            if self.ls.config.get('debug'):
                print(f"🔔 on_double_shift: backspace_hold={self.ls.backspace_hold_detected}, chars_in_buffer={self.ls.chars_in_buffer}, has_selection={has_sel}, auto_switch={self.ls.config.get('auto_switch')}")

            if self.ls.conversion_manager:
                mode = self.ls.conversion_manager.choose_mode(self.ls.buffer, lambda: has_sel, backspace_hold=self.ls.backspace_hold_detected)
                if self.ls.config.get('debug'):
                    print(f"→ ConversionManager selected mode: {mode} (backspace_hold={self.ls.backspace_hold_detected}, chars={self.ls.buffer.chars_in_buffer}, has_selection={has_sel})")
                if mode == 'selection':
                    import lswitch as _pkg
                    adapter = getattr(_pkg, 'x11_adapter', None)
                    try:
                        if not has_sel:
                            if adapter:
                                try:
                                    adapter.ctrl_shift_left()
                                except Exception:
                                    if self.ls.config.get('debug'):
                                        print("⚠️ adapter.ctrl_shift_left failed (non-fatal)")
                            else:
                                try:
                                    system.xdotool_key('ctrl+shift+Left', timeout=0.3, stderr=subprocess.DEVNULL)
                                except Exception:
                                    if self.ls.config.get('debug'):
                                        print("⚠️ system xdotool ctrl+shift+Left failed (non-fatal)")
                            time.sleep(0.03)

                        try:
                            if self.ls.config.get('debug'):
                                print(f"{time.time():.6f} ▸ calling convert_selection(prefer_trim_leading={(not has_sel)}) (has_sel={has_sel})", flush=True)
                            try:
                                self.ls.convert_selection(prefer_trim_leading=(not has_sel))
                            except TypeError:
                                # Backwards compatibility for patched objects in tests
                                self.ls.convert_selection()
                            self.ls.backspace_hold_detected = False
                        except Exception as e:
                            if self.ls.config.get('debug'):
                                print(f"⚠️ Selection conversion failed — falling back to retype: {e}")
                                import traceback
                                traceback.print_exc()
                            self.ls.convert_and_retype()
                    except Exception:
                        if self.ls.config.get('debug'):
                            print("⚠️ Unexpected error during selection handling — falling back to retype")
                        self.ls.convert_and_retype()
                else:
                    self.ls.convert_and_retype()
            else:
                # Legacy behavior
                if self.ls.backspace_hold_detected or self.ls.chars_in_buffer == 0:
                    reason = "hold Backspace" if self.ls.backspace_hold_detected else "empty buffer"
                    if self.ls.config.get('debug'):
                        print(f"→ Selection + convert ({reason})")
                    try:
                        system.xdotool_key('ctrl+shift+Left', timeout=0.3, stderr=subprocess.DEVNULL)
                        time.sleep(0.03)
                        # Legacy path: for empty buffer/backspace hold, prefer trimming
                        self.ls.convert_selection(prefer_trim_leading=True)
                    except Exception:
                        pass
                    self.ls.backspace_hold_detected = False
                elif has_sel:
                    if self.ls.config.get('debug'):
                        print("→ Converting selection")
                    self.ls.convert_selection()
                else:
                    if self.ls.config.get('debug'):
                        print("→ Converting last word")
                    self.ls.convert_and_retype()

            # Reset marker
            self.ls.last_shift_press = 0
        except Exception as e:
            if self.ls.config.get('debug'):
                print(f"⚠️ on_double_shift error: {e}")

    def handle_event(self, event):
        """Main event handler. Returns False to indicate exit (ESC)."""
        # For debugging: only log blocked space events when debug is enabled
        if event.type == getattr(ecodes, 'EV_KEY', None) and getattr(event, 'code', None) == getattr(ecodes, 'KEY_SPACE', None):
            if self.ls.is_converting and self.ls.config.get('debug'):
                print(f"🔍 SPACE BLOCKED is_converting=True!")

        if self.ls.is_converting:
            if self.ls.config.get('debug'):
                print(f"{time.time():.6f} ▸ Event ignored: is_converting=True", flush=True)
            return True

        if event.type != getattr(ecodes, 'EV_KEY', None):
            return

        current_time = time.time()

        # Navigation keys - clear buffer
        if getattr(event, 'code', None) in getattr(self.ls, 'navigation_keys', set()) and event.value == 0:
            # Always clear buffer on navigation to ensure transient flags (like had_backspace)
            # don't persist and influence later conversions unexpectedly.
            try:
                self.ls.clear_buffer()
            except Exception:
                pass
            if self.ls.config.get('debug'):
                print("Buffer cleared (navigation)")
            return

        # Shift handling
        if getattr(event, 'code', None) in (getattr(ecodes, 'KEY_LEFTSHIFT', None), getattr(ecodes, 'KEY_RIGHTSHIFT', None)):
            # Keep shifts in event buffer
            self.ls.event_buffer.append(event)

            if event.value == 1:  # press
                # Mark that we've seen a real press and remember time (used to
                # ignore stray releases that are not preceded by a press).
                self._shift_pressed = True
                self._shift_last_press_time = current_time
                if self.ls.config.get('debug'):
                    print(f"{time.time():.6f} ▸ SHIFT press (handler): _shift_pressed={self._shift_pressed}, _shift_last_press_time={self._shift_last_press_time:.6f}", flush=True)
            elif event.value == 0:  # release
                # Reset pressed flag for this release
                self._shift_pressed = False
                if self.ls.config.get('debug'):
                    print(f"{time.time():.6f} ▸ SHIFT release (handler): last_shift_press={self.ls.last_shift_press:.6f}, _shift_pressed={self._shift_pressed}, suppress={getattr(self.ls, 'suppress_shift_detection', False)}, post_until={getattr(self.ls, '_post_replay_suppress_until', 0):.6f}, is_converting={getattr(self.ls, 'is_converting', False)}", flush=True)

                # If suppression is active (e.g., we're replaying synthetic events),
                # ignore shift releases so they don't retrigger conversions.
                if getattr(self.ls, 'suppress_shift_detection', False):
                    if self.ls.config.get('debug'):
                        print("🔕 Suppressing shift detection due to replay", flush=True)
                    # Clear marker to avoid partial detection after suppression
                    self.ls.last_shift_press = 0
                    return

                # Also ignore double-shift detection for a short period after replay
                # to allow delivery timing jitter to settle.
                if getattr(self.ls, '_post_replay_suppress_until', 0) and current_time < self.ls._post_replay_suppress_until:
                    if self.ls.config.get('debug'):
                        print("🔕 Ignoring shift release due to post-replay suppression window", flush=True)
                    self.ls.last_shift_press = 0
                    return

                if current_time - self.ls.last_shift_press < self.ls.double_click_timeout:
                    if self.ls.config.get('debug'):
                        print("✓ Double Shift detected!")
                        print(f"🔔 Delegating double-shift to on_double_shift (backspace_hold={self.ls.backspace_hold_detected}, chars={self.ls.chars_in_buffer})")
                    try:
                        self.on_double_shift()
                    except Exception as e:
                        print(f"⚠️ Error in on_double_shift: {e}")
                    return True
                else:
                    self.ls.last_shift_press = current_time
            return True

        # ESC - exit
        if getattr(event, 'code', None) == getattr(ecodes, 'KEY_ESC', None) and event.value == 0:
            if self.ls.user_dict:
                try:
                    self.ls.user_dict.flush()
                except Exception:
                    pass
            return False

        # Enter - clear buffer
        if getattr(event, 'code', None) == getattr(ecodes, 'KEY_ENTER', None) and event.value == 0:
            self.ls.clear_buffer()
            self.ls.last_was_space = False
            try:
                self.ls.update_selection_snapshot()
            except Exception:
                pass
            if self.ls.config.get('debug'):
                print("Buffer cleared (enter)")
            return

        # Active keys
        if getattr(event, 'code', None) in getattr(self.ls, 'active_keycodes', set()):
            if event.code == getattr(ecodes, 'KEY_SPACE', None) and self.ls.config.get('debug'):
                print(f"🔍 SPACE INCOMING! value={event.value}, last_manual={self.ls.last_manual_convert is not None}")

            if self.ls.last_was_space and event.code != getattr(ecodes, 'KEY_SPACE', None):
                self.ls.clear_buffer()
                self.ls.update_selection_snapshot()
                self.ls.last_was_space = False
                if self.ls.config.get('debug'):
                    print("Buffer reset after space, new word started")

            if len(self.ls.event_buffer) == 0 and event.value == 1:
                self.ls.update_selection_snapshot()
                if self.ls.config.get('debug'):
                    print("First char - selection snapshot updated")

            self.ls.event_buffer.append(event)

            if event.value == 0:
                if event.code == getattr(ecodes, 'KEY_BACKSPACE', None):
                    self.ls.had_backspace = True
                    self.ls.consecutive_backspace_repeats = 0
                    if self.ls.last_auto_convert:
                        self.ls.last_auto_convert = None
                    if self.ls.last_manual_convert:
                        self.ls.last_manual_convert = None
                    if self.ls.chars_in_buffer > 0:
                        self.ls.chars_in_buffer -= 1
                        if self.ls.text_buffer:
                            self.ls.text_buffer.pop()
            elif event.value == 2:  # repeat (key held down)
                if event.code == getattr(ecodes, 'KEY_BACKSPACE', None):
                    self.ls.consecutive_backspace_repeats += 1
                    if self.ls.consecutive_backspace_repeats >= 3:
                        if not self.ls.backspace_hold_detected:
                            self.ls.backspace_hold_detected = True
                            self.ls.backspace_hold_detected_at = time.time()
                            if self.ls.config.get('debug'):
                                print(f"⚠️ Backspace hold detected")
                else:
                    self.ls.consecutive_backspace_repeats = 0

            if event.value == 0 and event.code not in (getattr(ecodes, 'KEY_LEFTSHIFT', None), getattr(ecodes, 'KEY_RIGHTSHIFT', None), getattr(ecodes, 'KEY_BACKSPACE', None), getattr(ecodes, 'KEY_SPACE', None)):
                self.ls.chars_in_buffer += 1
                if self.ls.config.get('debug'):
                    print(f"🔍 DEBUG normal key: last_manual_convert={self.ls.last_manual_convert is not None}")
                if self.ls.last_auto_convert:
                    self.ls.last_auto_convert = None

                if self.ls.user_dict and self.ls.last_manual_convert:
                    time_since_convert = time.time() - self.ls.last_manual_convert['time']
                    if time_since_convert < 5.0:
                        original = self.ls.last_manual_convert['original']
                        converted = self.ls.last_manual_convert['converted']
                        from_lang = self.ls.last_manual_convert['from_lang']
                        to_lang = self.ls.last_manual_convert['to_lang']
                        if self.ls.config.get('debug'):
                            print(f"🔧 add_conversion (char): original='{original}', from={from_lang}, to={to_lang}")
                        try:
                            self.ls.user_dict.add_conversion(original, from_lang, to_lang, debug=self.ls.config.get('debug'))
                        except Exception:
                            pass
                    if event.code != getattr(ecodes, 'KEY_SPACE', None):
                        self.ls.last_manual_convert = None

                layout = self.ls.get_current_layout()
                ch = self.ls.keycode_to_char(event.code, layout, shift=False)
                if ch:
                    self.ls.text_buffer.append(ch)

                if event.code == getattr(ecodes, 'KEY_SPACE', None):
                    if self.ls.config.get('debug') and event.value == 0:
                        print(f"🔍 DEBUG space: last_manual_convert={self.ls.last_manual_convert is not None}")
                    if event.value == 0:
                        if self.ls.user_dict and self.ls.last_manual_convert:
                            time_since_convert = time.time() - self.ls.last_manual_convert['time']
                            if time_since_convert < 5.0:
                                original = self.ls.last_manual_convert['original']
                                from_lang = self.ls.last_manual_convert['from_lang']
                                to_lang = self.ls.last_manual_convert['to_lang']
                                try:
                                    self.ls.user_dict.add_conversion(original, from_lang, to_lang, debug=self.ls.config.get('debug'))
                                except Exception:
                                    pass
                    self.ls.last_was_space = True
                    if event.value == 0:
                        if self.ls.config.get('debug'):
                            if len(self.ls.text_buffer) > 0:
                                print(f"Buffer: {self.ls.chars_in_buffer} chars, text: '{''.join(self.ls.text_buffer)}'")
                        self.ls.check_and_auto_convert()
                return True

        else:
            if event.value == 0:
                self.ls.clear_buffer()
                if self.ls.config.get('debug'):
                    print("Buffer cleared")
            return True
