"""EventHandler: Centralized event processing for LSwitch.

Handles keyboard events, double-shift detection, and event replay.
Extracted from core.py to improve maintainability.
"""
import time
from typing import List, Dict, Any, Callable, Optional
from evdev import ecodes


class EventHandler:
    """Handles keyboard events and double-shift detection."""
    
    def __init__(self, config: Dict[str, Any], debug: bool = False):
        """Initialize EventHandler.
        
        Args:
            config: Configuration dictionary.
            debug: Enable debug output.
        """
        self.config = config
        self.debug = debug
        
        # Double-shift detection
        self.double_click_timeout = config.get('double_click_timeout', 0.3)
        self.last_shift_press = 0.0
        self._shift_pressed = False
        self._shift_last_press_time = 0.0
        
        # Event buffering and replay
        self.event_buffer: List[Any] = []
        self.replay_mode = False
        
        # State tracking
        self.suppress_events_until = 0.0
        self.is_converting = False
        self.last_was_space = False
        self.had_backspace = False
        self.consecutive_backspace_repeats = 0
        self.backspace_hold_detected = False
        self.suppress_shift_detection = False
        self._post_replay_suppress_until = 0.0
        
        # Navigation keys that clear buffer
        self.navigation_keys = [
            ecodes.KEY_LEFT, ecodes.KEY_RIGHT, ecodes.KEY_UP, ecodes.KEY_DOWN,
            ecodes.KEY_HOME, ecodes.KEY_END, ecodes.KEY_PAGEUP, ecodes.KEY_PAGEDOWN,
            ecodes.KEY_TAB, ecodes.KEY_ENTER
        ]
        
        # Callbacks  
        self.on_double_shift_callback: Optional[Callable[[], None]] = None
        self.on_auto_convert_callback: Optional[Callable[[], None]] = None
        self.on_clear_buffer_callback: Optional[Callable[[], None]] = None
        self.input_handler = None
    
    def set_config(self, config: Dict[str, Any]) -> None:
        """Update configuration."""
        self.config = config
        self.double_click_timeout = config.get('double_click_timeout', 0.3)
    
    def set_callbacks(self, 
                     on_double_shift: Optional[Callable[[], None]] = None,
                     on_auto_convert: Optional[Callable[[], None]] = None,
                     on_clear_buffer: Optional[Callable[[], None]] = None) -> None:
        """Set event callbacks."""
        if on_double_shift:
            self.on_double_shift_callback = on_double_shift
        if on_auto_convert:
            self.on_auto_convert_callback = on_auto_convert
        if on_clear_buffer:
            self.on_clear_buffer_callback = on_clear_buffer
    
    def handle_event(self, event, chars_in_buffer=0, clear_buffer_callback=None) -> Optional[bool]:
        """Handle keyboard event - MAIN EVENT PROCESSING.
        
        Args:
            event: evdev keyboard event.
            chars_in_buffer: Current buffer size.
            clear_buffer_callback: Function to clear buffer.
            
        Returns:
            None to continue processing, or bool to indicate handled.
        """
        # Delegate to InputHandler if present (preferred path)
        if self.input_handler:
            result = self.input_handler.handle_event(event)
            if result is not None:
                return result
        
        # Debug space blocking
        if event.type == ecodes.EV_KEY and event.code == ecodes.KEY_SPACE:
            if self.is_converting and self.debug:
                print("🔍 ПРОБЕЛ ЗАБЛОКИРОВАН is_converting=True!")
        
        if self.is_converting:
            return None
        
        # Only handle key events
        if event.type != ecodes.EV_KEY:
            return None
        
        current_time = time.time()
        
        # Navigation keys - clear buffer (new input context)
        if event.code in self.navigation_keys and event.value == 0:
            if chars_in_buffer > 0:
                if clear_buffer_callback:
                    clear_buffer_callback()
                if self.debug:
                    print("Буфер очищен (навигация)")
            return None
        
        # Shift: check for double-shift
        if event.code in (ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT):
            # Add shift events to buffer for proper replay
            self.event_buffer.append(event)
            
            if event.value == 1:  # Press
                if self.debug:
                    print(f"🔑 Shift нажат! last_press={self.last_shift_press:.3f} current={current_time:.3f} delta={current_time - self.last_shift_press:.3f}")
                pass  # Just add to buffer, no additional tracking needed
            elif event.value == 0:  # Release
                # If suppression is active, ignore shift releases
                if self.suppress_shift_detection:
                    if self.debug:
                        print("🔕 Подавление детекции Shift (реплей/конвертация)")
                    self.last_shift_press = 0
                    return None
                
                # Ignore releases briefly after replay
                if self._post_replay_suppress_until and current_time < self._post_replay_suppress_until:
                    if self.debug:
                        print("🔕 Игнорирование релиза Shift (пост-реплей окно)")
                    self.last_shift_press = 0
                    return None
                
                if current_time - self.last_shift_press < self.double_click_timeout:
                    if self.debug:
                        print("✓ Двойной Shift обнаружен!")
                        print(f"🔔 Delegating double-shift to on_double_shift")
                    
                    if self.on_double_shift_callback:
                        try:
                            self.on_double_shift_callback()
                        except Exception as e:
                            if self.debug:
                                print(f"⚠️ Ошибка в on_double_shift: {e}")
                    
                    self.last_shift_press = 0
                    return None
                else:
                    self.last_shift_press = current_time
            return None
        
        # Space key - trigger auto-conversion
        if event.code == ecodes.KEY_SPACE:
            self.last_was_space = True
            # При пробеле показываем буфер и проверяем автопереключение (при отпускании)
            if event.value == 0:  # При отпускании клавиши
                if self.debug:
                    if chars_in_buffer > 0:
                        print(f"Буфер: {chars_in_buffer} символов")
                    print("🔴 SPACE RELEASED - calling check_and_auto_convert()")
                
                if self.on_auto_convert_callback:
                    self.on_auto_convert_callback()
        
        # Handle other keys
        else:
            # Clear space flag and handle buffer management
            if self.last_was_space:
                self.last_was_space = False
                if clear_buffer_callback:
                    clear_buffer_callback()
                if self.debug:
                    print("Buffer cleared")
        
        return None
    
    def _handle_shift_event(self, event, current_time: float) -> bool:
        """Handle shift key events for double-shift detection."""
        if event.value == 1:  # Shift press
            if self.debug:
                print(f"{current_time:.6f} SHIFT press")
            
            # Check for double-shift
            time_since_last = current_time - self._shift_last_press_time if self._shift_last_press_time > 0 else float('inf')
            
            if (self._shift_pressed and 
                time_since_last <= self.double_click_timeout and 
                not self.is_converting):
                
                if self.debug:
                    print(f"🚀 DOUBLE SHIFT detected! (interval: {time_since_last:.3f}s)")
                
                # Call double-shift callback
                if self.on_double_shift_callback:
                    self.on_double_shift_callback()
                
                # Reset state
                self._shift_pressed = False
                self._shift_last_press_time = 0.0
                return True  # Suppress this event
            
            self._shift_pressed = True
            self._shift_last_press_time = current_time
            
        elif event.value == 0:  # Shift release
            if self.debug:
                print(f"{current_time:.6f} SHIFT release")
            self._shift_pressed = False
        
        return False  # Don't suppress normal shift events
    
    def _handle_space_event(self, event) -> bool:
        """Handle space key events for auto-conversion."""
        self.last_was_space = True
        
        if event.value == 0:  # Space key release
            if self.debug:
                print("🔴 SPACE RELEASED - calling auto-conversion check")
            
            # Call auto-convert callback
            if self.on_auto_convert_callback:
                self.on_auto_convert_callback()
        
        return False  # Don't suppress space events
    
    def _handle_backspace_event(self, event) -> bool:
        """Handle backspace key events."""
        if event.value == 1:  # Backspace press
            self.had_backspace = True
        
        return False  # Don't suppress backspace events
    
    def _handle_normal_key_event(self, event) -> bool:
        """Handle normal key events (letters, numbers, etc.)."""
        # Clear space flag on any non-space key
        self.last_was_space = False
        
        if event.value == 1 and self.debug:
            print("🔍 DEBUG normal key")
        
        return False  # Don't suppress normal key events
    
    def start_suppression(self, duration: float) -> None:
        """Start event suppression for given duration."""
        self.suppress_events_until = time.time() + duration
        if self.debug:
            print(f"🔇 Event suppression started for {duration:.3f}s")
    
    def set_converting_state(self, converting: bool) -> None:
        """Set conversion state."""
        self.is_converting = converting
        
        if converting:
            # Reset double-shift detection during conversion
            self._shift_pressed = False
            self._shift_last_press_time = 0.0