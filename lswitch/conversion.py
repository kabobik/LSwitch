"""ConversionManager: central logic for choosing conversion mode.

Responsibility:
- Decide between 'retype' (fast) and 'selection' (slow) conversion modes,
  based on buffer state, backspace hold, presence of selection, and config.
- Provide an API `choose_mode` and `execute` to call the appropriate callback.
"""
from typing import Callable
import time

# Default application policies: prefer retype (fast) in IDEs, selection (slow) in browsers
DEFAULT_APP_POLICIES = {
    'Code': 'retype',        # VSCode
    'IntelliJ': 'retype',    # JetBrains IDEs
    'Gedit': 'retype',       # simple editors
    'Firefox': 'selection',  # browsers tend to have complex widgets
    'Chromium': 'selection',
    'Google-chrome': 'selection'
}


class ConversionManager:
    def __init__(self, config=None, x11_adapter=None):
        self.config = config or {}
        self.x11_adapter = x11_adapter
        # Merge defaults with config-provided overrides
        base = DEFAULT_APP_POLICIES.copy()
        base.update(self.config.get('app_policies', {}))
        self.app_policies = base
        self.policies = []  # list of callables(context) -> 'retype'|'selection'|None

    def register_policy(self, policy_callable):
        """Register a policy callable that receives a context dict and may return a mode or None."""
        self.policies.append(policy_callable)

    def _detect_lang(self, s: str) -> str:
        s_clean = (s or '').strip()
        return 'ru' if any(('А' <= c <= 'Я') or ('а' <= c <= 'я') or c in 'ЁёЪъЬь' for c in s_clean) else 'en'

    def _canonicalize(self, s: str, user_dict=None) -> str:
        s_clean = (s or '').strip()
        if not s_clean:
            return ''
        lang = self._detect_lang(s_clean)
        if user_dict:
            try:
                return user_dict._canonicalize(s_clean, lang)
            except Exception:
                return s_clean.lower()
        return s_clean.lower()

    def is_correction(self, auto_marker: dict, original_text: str, converted_text: str, user_dict=None, timeout=5.0) -> bool:
        """Return True if the manual conversion should be considered a correction after an auto conversion."""
        try:
            if not auto_marker:
                return False
            time_since_auto = time.time() - auto_marker.get('time', 0)
            if time_since_auto >= timeout:
                return False

            orig_canon = self._canonicalize(original_text, user_dict)
            auto_conv_canon = self._canonicalize(auto_marker.get('converted_to', ''), user_dict)
            conv_canon = self._canonicalize(converted_text, user_dict)
            auto_word_canon = self._canonicalize(auto_marker.get('word', ''), user_dict)

            if orig_canon == auto_conv_canon and conv_canon == auto_word_canon:
                return True
            return False
        except Exception:
            return False

    def apply_correction(self, user_dict, auto_marker: dict, original_text: str, converted_text: str, timeout=None, debug=False) -> bool:
        """If correction is detected, call user_dict.add_correction and return True."""
        try:
            t = timeout if timeout is not None else user_dict.data['settings'].get('correction_timeout', 5.0) if user_dict else 5.0
            if self.is_correction(auto_marker, original_text, converted_text, user_dict=user_dict, timeout=t):
                corrected_word = converted_text.strip().lower()
                lang = self._detect_lang(corrected_word)
                if user_dict:
                    user_dict.add_correction(corrected_word, lang, debug=debug)
                if debug:
                    print(f"📚 APPLY CORRECTION (via ConversionManager): '{corrected_word}' ({lang})")
                return True
            return False
        except Exception as e:
            if debug:
                print(f"⚠️ ConversionManager.apply_correction error: {e}")
            return False
    def choose_mode(self, buffer, has_selection_fn: Callable[[], bool], backspace_hold=False):
        """Return 'retype' or 'selection'.

        Rules (simple, testable):
        - If backspace_hold is True or buffer.chars_in_buffer == 0 -> prefer selection
        - Else if has_selection_fn() is True -> selection
        - Else if config has prefer_retype_when_possible True -> retype
        - Else -> retype
        """
        # If explicit backspace hold or empty buffer -> selection
        if backspace_hold or getattr(buffer, 'chars_in_buffer', 0) == 0:
            if self.config.get('debug'):
                print(f"🔧 choose_mode decision: backspace_hold={backspace_hold}, chars_in_buffer={getattr(buffer,'chars_in_buffer',0)} -> selection", flush=True)
            return 'selection'

        # If there's a fresh selection -> selection
        try:
            has_sel = has_selection_fn()
            if self.config.get('debug'):
                print(f"🔧 choose_mode: has_selection_fn() -> {has_sel}", flush=True)
            if has_sel:
                if self.config.get('debug'):
                    print(f"🔧 choose_mode decision: has_selection -> selection", flush=True)
                return 'selection'
        except Exception:
            # If has_selection fails, prefer retype if possible
            if self.config.get('debug'):
                print(f"🔧 choose_mode: has_selection_fn() raised, falling through", flush=True)
            pass

        # Check app-specific policies (config mapping)
        try:
            if self.app_policies and self.x11_adapter:
                try:
                    win = None
                    if hasattr(self.x11_adapter, 'get_active_window_class'):
                        win = self.x11_adapter.get_active_window_class()
                    elif hasattr(self.x11_adapter, 'get_active_window_name'):
                        win = self.x11_adapter.get_active_window_name()
                    if win and win in self.app_policies:
                        return self.app_policies[win]
                except Exception:
                    pass
        except Exception:
            pass

        # Call registered policy callables (higher priority)
        for p in self.policies:
            try:
                res = p({'buffer': buffer, 'has_selection': has_selection_fn, 'x11': self.x11_adapter, 'config': self.config})
                if res in ('retype', 'selection'):
                    return res
            except Exception:
                continue

        # Config override
        if self.config.get('prefer_retype_when_possible'):
            return 'retype'

        # Default to retype when buffer has chars
        return 'retype'

    def execute(self, mode: str, retype_cb: Callable[[], None], selection_cb: Callable[[], None]):
        """Execute provided callback based on mode."""
        if mode == 'retype':
            return retype_cb()
        else:
            return selection_cb()


def check_and_auto_convert(ls):
    """Auto-convert text based on N-gram analysis and dictionary.
    
    This function is called when space is pressed (end of word).
    It analyzes the word in the buffer and automatically converts if needed.
    
    Args:
        ls: LSwitch instance with text_buffer, user_dict, config, etc.
    
    Returns:
        None
    """
    try:
        # Only proceed if auto_switch is enabled
        if not ls.config.get('auto_switch', False):
            return
        
        # Get the word from the text buffer
        if not ls.text_buffer:
            return
        
        word = ''.join(ls.text_buffer).strip()
        if not word or len(word) < 1:
            return
        
        # Use ngrams to check if conversion should happen
        from lswitch import ngrams
        import subprocess
        
        # Get user_dict if available
        user_dict = getattr(ls, 'user_dict', None)
        
        # Check if we should auto-convert
        should_convert, best_text, reason = ngrams.should_convert(
            word, 
            threshold=ls.config.get('auto_switch_threshold', 10),
            user_dict=user_dict
        )
        
        if ls.config.get('debug'):
            print(f"🤖 Auto-convert check: '{word}' → should_convert={should_convert}, reason='{reason}'")
        
        if should_convert and best_text != word:
            # We need to convert the text
            if ls.config.get('debug'):
                print(f"🔄 Auto-converting: '{word}' → '{best_text}'")
            
            try:
                # Delete the current word (select it backward and delete)
                # Use Ctrl+Shift+Left to select the word backward
                ls.system.xdotool_key('ctrl+shift+Left', timeout=0.3, stderr=subprocess.DEVNULL)
                time.sleep(0.05)
                
                # Delete the selected text
                ls.system.xdotool_key('Delete', timeout=0.1, stderr=subprocess.DEVNULL)
                time.sleep(0.05)
                
                # Type the converted text using fallback method for better compatibility
                if hasattr(ls, '_fallback_type_text'):
                    ls._fallback_type_text(best_text)
                else:
                    # Fallback: use fake_kb directly
                    from evdev import ecodes
                    for char in best_text.lower():
                        if char == ' ':
                            code = ecodes.KEY_SPACE
                        elif 'a' <= char <= 'z':
                            code = getattr(ecodes, f'KEY_{char.upper()}')
                        else:
                            continue
                        ls.fake_kb.write(ecodes.EV_KEY, code, 1)
                        ls.fake_kb.syn()
                        ls.fake_kb.write(ecodes.EV_KEY, code, 0)
                        ls.fake_kb.syn()
                
                time.sleep(0.05)
                
                # Update buffer to reflect the change
                ls.text_buffer = list(best_text.lower())
                ls.chars_in_buffer = len(best_text)
                
                if ls.config.get('debug'):
                    print(f"✓ Auto-conversion applied: '{word}' → '{best_text}'")
            except Exception as e:
                if ls.config.get('debug'):
                    print(f"⚠️ Auto-conversion failed: {e}")
    
    except Exception as e:
        if getattr(ls, 'config', {}).get('debug'):
            print(f"⚠️ check_and_auto_convert error: {e}")
            import traceback
            traceback.print_exc()
