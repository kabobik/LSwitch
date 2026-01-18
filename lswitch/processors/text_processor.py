"""
TextProcessor - отвечает за обработку и конвертацию текста между раскладками
"""
import time
import subprocess
from typing import Optional, Dict, Any
from evdev import ecodes


class TextProcessor:
    """Обработчик конвертации текста между раскладками"""
    
    def __init__(self, system, config: Dict[str, Any], user_dict=None):
        self.system = system
        self.config = config
        self.user_dict = user_dict
        
        # Импорт карт конвертации
        from lswitch.conversion_maps import RU_TO_EN, EN_TO_RU
        self.RU_TO_EN = RU_TO_EN
        self.EN_TO_RU = EN_TO_RU
    
    def convert_text(self, text):
        """Конвертирует текст между раскладками с сохранением регистра"""
        if not text:
            return text
        
        # Определяем раскладку по количеству символов
        ru_chars = sum(1 for c in text.lower() if c in self.RU_TO_EN)
        en_chars = sum(1 for c in text.lower() if c in self.EN_TO_RU)
        
        result = []
        if ru_chars > en_chars:
            # Конвертируем RU -> EN
            for c in text:
                is_upper = c.isupper()
                converted = self.RU_TO_EN.get(c.lower(), c)
                result.append(converted.upper() if is_upper else converted)
        else:
            # Конвертируем EN -> RU
            for c in text:
                is_upper = c.isupper()
                converted = self.EN_TO_RU.get(c.lower(), c)
                result.append(converted.upper() if is_upper else converted)
        
        return ''.join(result)
    
    def fallback_type_text(self, text: str, tap_key_func, fake_kb=None):
        """Fallback typing: type characters from text using tap_key for common glyphs.

        This helps on systems where replaying recorded events does not produce
        visible characters (e.g., events contain only keydown or adapter fails).
        We intentionally implement a small charset (a-z, space and common punctuation)
        to be conservative and safe.
        """
        from evdev import ecodes as _ecodes
        CHAR_MAP = {
            'a': _ecodes.KEY_A, 'b': _ecodes.KEY_B, 'c': _ecodes.KEY_C, 'd': _ecodes.KEY_D,
            'e': _ecodes.KEY_E, 'f': _ecodes.KEY_F, 'g': _ecodes.KEY_G, 'h': _ecodes.KEY_H,
            'i': _ecodes.KEY_I, 'j': _ecodes.KEY_J, 'k': _ecodes.KEY_K, 'l': _ecodes.KEY_L,
            'm': _ecodes.KEY_M, 'n': _ecodes.KEY_N, 'o': _ecodes.KEY_O, 'p': _ecodes.KEY_P,
            'q': _ecodes.KEY_Q, 'r': _ecodes.KEY_R, 's': _ecodes.KEY_S, 't': _ecodes.KEY_T,
            'u': _ecodes.KEY_U, 'v': _ecodes.KEY_V, 'w': _ecodes.KEY_W, 'x': _ecodes.KEY_X,
            'y': _ecodes.KEY_Y, 'z': _ecodes.KEY_Z,
            ' ': _ecodes.KEY_SPACE, ',': _ecodes.KEY_COMMA, '.': _ecodes.KEY_DOT,
            '/': _ecodes.KEY_SLASH, '-': _ecodes.KEY_MINUS, ';': _ecodes.KEY_SEMICOLON,
            "'": _ecodes.KEY_APOSTROPHE, ':': _ecodes.KEY_SEMICOLON
        }

        from evdev import ecodes
        
        for ch in text:
            if not ch:
                continue
            lower = ch.lower()
            code = CHAR_MAP.get(lower)
            # Support Cyrillic characters by mapping via RU_TO_EN when needed
            if code is None:
                try:
                    mapped = self.RU_TO_EN.get(lower)
                    if mapped:
                        code = CHAR_MAP.get(mapped.lower())
                except Exception:
                    pass

            if code is None:
                # Unsupported char — skip for now
                continue

            try:
                tap_key_func(code, n_times=1)
            except Exception:
                # Last resort: direct uinput writes
                try:
                    if fake_kb:
                        fake_kb.write(ecodes.EV_KEY, code, 1)
                        fake_kb.syn()
                        fake_kb.write(ecodes.EV_KEY, code, 0)
                        fake_kb.syn()
                except Exception:
                    pass
    
    def convert_selection(self, parent, prefer_trim_leading=False, user_has_selection=False):
        """Конвертирует выделенный текст через PRIMARY selection (без порчи clipboard)"""
        # Проверяем наличие минимум 2 раскладок
        if len(parent.layouts) < 2:
            if self.config.get('debug'):
                print(f"⚠️  Конвертация невозможна: только {len(parent.layouts)} раскладка")
            return
        
        if parent.is_converting:
            return
        
        parent.is_converting = True
        # Suppress double-shift detection while performing selection conversion
        # to avoid replayed events (or adapter-triggered key events) from
        # retriggering the double-shift handler.
        parent.suppress_shift_detection = True
        if self.config.get('debug'):
            print(f"{time.time():.6f} ▸ convert_selection ENTER: suppress={parent.suppress_shift_detection}, is_converting={parent.is_converting}, user_has_selection={user_has_selection}", flush=True)
        
        try:
            # Получаем выделенный текст из PRIMARY selection (не трогаем clipboard!)
            try:
                import lswitch as _pkg
                adapter = getattr(_pkg, 'x11_adapter', None)
                if self.config.get('debug'):
                    print(f"{time.time():.6f} ▸ convert_selection: adapter_present={bool(adapter)}", flush=True)
                if adapter:
                    selected_text = adapter.get_primary_selection(timeout=0.5)
                else:
                    selected_text = self.system.xclip_get(selection='primary', timeout=0.5).stdout
                if self.config.get('debug'):
                    print(f"{time.time():.6f} ▸ convert_selection: selected_text={selected_text!r}", flush=True)
            except Exception as e:
                if self.config.get('debug'):
                    print(f"{time.time():.6f} ▸ convert_selection: error getting primary selection: {e}", flush=True)
                selected_text = ''
            
            if selected_text:
                # Delegate selection conversion to SelectionManager
                try:
                    from selection import SelectionManager
                    sm = SelectionManager(adapter, repair_enabled=self.config.get('selection_repair', False))
                    switch_fn = (parent.switch_keyboard_layout if self.config.get('switch_layout_after_convert', True) else None)

                    orig, conv = sm.convert_selection(self.convert_text, user_dict=self.user_dict, switch_layout_fn=switch_fn, debug=self.config.get('debug'), prefer_trim_leading=prefer_trim_leading, user_has_selection=user_has_selection)

                    if conv:
                        if self.user_dict and not parent.last_auto_convert:
                            parent.last_manual_convert = {
                                'original': orig.strip().lower(),
                                'converted': conv.strip().lower(),
                                'from_lang': 'ru' if any(('А' <= c <= 'Я') or ('а' <= c <= 'я') for c in orig) else 'en',
                                'to_lang': 'ru' if any(('А' <= c <= 'Я') or ('а' <= c <= 'я') for c in conv) else 'en',
                                'time': time.time()
                            }

                        # Correction detection
                        auto_marker = parent.last_auto_convert or getattr(parent, '_recent_auto_marker', None)
                        if self.user_dict and auto_marker and parent.conversion_manager:
                            try:
                                if parent.conversion_manager.apply_correction(self.user_dict, auto_marker, orig, conv, debug=self.config.get('debug')):
                                    parent.last_auto_convert = None
                                    parent._recent_auto_marker = None
                            except Exception as e:
                                if self.config.get('debug'):
                                    print(f"⚠️ Error applying correction: {e}")

                    # finalize
                    parent.backspace_hold_detected = False
                    parent.update_selection_snapshot()
                    parent.clear_buffer()
                except Exception as e:
                    if self.config.get('debug'):
                        print(f"⚠️ SelectionManager failed: {e}")
                    # fallback to legacy path (let existing behavior run)
                    try:
                        x11_adapter = getattr(_pkg, 'x11_adapter', None)
                        if x11_adapter:
                            x11_adapter.ctrl_shift_left()
                        else:
                            self.system.xdotool_key('ctrl+shift+Left', timeout=0.3, stderr=subprocess.DEVNULL)
                        time.sleep(0.03)

                        # Получаем обновленную выделенную текстовую область
                        try:
                            result = self.system.xclip_get(selection='primary', timeout=0.5)
                            selected_text = result.stdout
                        except Exception as e:
                            if self.config.get('debug'):
                                print(f"⚠️ Не удалось получить выделение: {e}")
                            return

                        if selected_text:
                            # Конвертируем и заменяем
                            converted = self.convert_text(selected_text)
                            if converted != selected_text:
                                try:
                                    # Вводим преобразованный текст
                                    self.system.xdotool_type(converted, timeout=0.5)
                                    
                                    # Переключаем раскладку если требуется
                                    if self.config.get('switch_layout_after_convert', True):
                                        parent.switch_keyboard_layout()
                                    
                                    if self.config.get('debug'):
                                        print(f"✓ Текст '{selected_text}' → '{converted}'")
                                except Exception as e:
                                    if self.config.get('debug'):
                                        print(f"⚠️ Ошибка ввода: {e}")
                    except Exception as e:
                        if self.config.get('debug'):
                            print(f"⚠️ Ошибка в fallback: {e}")
        finally:
            parent.is_converting = False
            parent.suppress_shift_detection = False
            if self.config.get('debug'):
                print(f"{time.time():.6f} ▸ convert_selection EXIT", flush=True)
    
    def convert_and_retype(self, parent, is_auto=False):
        """Переконвертировать текст в буфере и воспроизвести события.
        Если is_auto=True, не устанавливаем last_manual_convert и не считаем это за ручную конвертацию."""
        # Проверяем наличие минимум 2 раскладок
        if len(parent.layouts) < 2:
            if self.config.get('debug'):
                print(f"⚠️  Конвертация невозможна: только {len(parent.layouts)} раскладка")
            return
        
        if parent.is_converting or parent.chars_in_buffer == 0:
            return
        
        parent.is_converting = True
        if self.config.get('debug'):
            print(f"{time.time():.6f} ▸ convert_and_retype ENTER (is_auto={is_auto}) chars_in_buffer={parent.chars_in_buffer} is_converting={parent.is_converting} last_shift_press={parent.last_shift_press:.6f} suppress={getattr(parent,'suppress_shift_detection',False)}")

        # Если была недавняя автоконвертация — отметим её в логах, но НЕ очищаем маркер.
        # Это нужно, чтобы последующая ручная конвертация могла быть распознана как коррекция
        # (проверка и очистка выполняется в блоке для ручной конвертации ниже).
        if self.user_dict and parent.last_auto_convert and self.config.get('debug'):
            age = time.time() - parent.last_auto_convert['time']
            print(f"🔍 Обнаружена недавняя автоконвертация (age={age:.2f}s), проверку коррекции выполним позже")
        
        try:
            if self.config.get('debug'):
                print(f"Конвертирую {parent.chars_in_buffer} символов...")

            # Support override from ngrams fallback: if _override_converted_text is set,
            # expose it as local converted_text so later logic will use it to update buffer
            if hasattr(parent, '_override_converted_text'):
                converted_text = getattr(parent, '_override_converted_text')
            
            # КРИТИЧНО: сохраняем копию событий ДО очистки буфера!
            events_to_replay = list(parent.buffer.event_buffer)
            num_chars = parent.buffer.chars_in_buffer
            
            # Сохраняем информацию для отслеживания успешной ручной конвертации
            # Только если это НЕ автоконвертация
            if not is_auto and self.user_dict and len(parent.buffer.text_buffer) > 0:
                original_text = ''.join(parent.buffer.text_buffer)
                # Определяем язык исходного текста
                has_cyrillic = any(('А' <= c <= 'Я') or ('а' <= c <= 'я') or c in 'ЁёЪъЬь' for c in original_text)
                from_lang = 'ru' if has_cyrillic else 'en'
                to_lang = 'en' if from_lang == 'ru' else 'ru'
                
                # Конвертируем текст чтобы узнать результат
                converted_text = self.convert_text(original_text)
                
                parent.last_manual_convert = {
                    "original": original_text,
                    "converted": converted_text,
                    "from_lang": from_lang,
                    "to_lang": to_lang,
                    "time": time.time()
                }
                if self.config.get('debug'):
                    print(f"🔍 last_manual_convert (convert_and_retype - manual): {parent.last_manual_convert}")

                # Если сразу после автоконвертации пользователь вручную вернул слово — фиксируем коррекцию
                auto_marker = parent.last_auto_convert or getattr(parent, '_recent_auto_marker', None)
                if self.user_dict and auto_marker and parent.conversion_manager:
                    try:
                        if parent.conversion_manager.apply_correction(self.user_dict, auto_marker, original_text, converted_text, debug=self.config.get('debug')):
                            # Очищаем запись о последней автоконвертации
                            parent.last_auto_convert = None
                            parent._recent_auto_marker = None
                    except Exception as e:
                        if self.config.get('debug'):
                            print(f"⚠️ Error applying correction: {e}")

            # Остальная логика конвертации остается в core.py
            return parent._finish_convert_and_retype(events_to_replay, num_chars)
            
        except Exception as e:
            if self.config.get('debug'):
                print(f"⚠️ Ошибка в convert_and_retype: {e}")
        finally:
            parent.is_converting = False

    def convert_selection(self, parent, prefer_trim_leading=False, user_has_selection=False):
        """Конвертирует выделенный текст через PRIMARY selection (без порчи clipboard)"""
        # Проверяем наличие минимум 2 раскладок
        if len(parent.layouts) < 2:
            if self.config.get('debug'):
                print(f"⚠️  Конвертация невозможна: только {len(parent.layouts)} раскладка")
            return
        
        if parent.is_converting:
            return
        
        parent.is_converting = True
        # Suppress double-shift detection while performing selection conversion
        # to avoid replayed events (or adapter-triggered key events) from
        # retriggering the double-shift handler.
        parent.suppress_shift_detection = True
        if self.config.get('debug'):
            print(f"{time.time():.6f} ▸ convert_selection ENTER: suppress={parent.suppress_shift_detection}, is_converting={parent.is_converting}, user_has_selection={user_has_selection}", flush=True)
        
        try:
            # Получаем выделенный текст из PRIMARY selection (не трогаем clipboard!)
            try:
                import lswitch as _pkg
                adapter = getattr(_pkg, 'x11_adapter', None)
                if self.config.get('debug'):
                    print(f"{time.time():.6f} ▸ convert_selection: adapter_present={bool(adapter)}", flush=True)
                if adapter:
                    selected_text = adapter.get_primary_selection(timeout=0.5)
                else:
                    selected_text = self.system.xclip_get(selection='primary', timeout=0.5).stdout
                if self.config.get('debug'):
                    print(f"{time.time():.6f} ▸ convert_selection: selected_text={selected_text!r}", flush=True)
            except Exception as e:
                if self.config.get('debug'):
                    print(f"{time.time():.6f} ▸ convert_selection: error getting primary selection: {e}", flush=True)
                selected_text = ''
            
            if selected_text:
                # Delegate selection conversion to SelectionManager
                try:
                    from lswitch.selection import SelectionManager
                    sm = SelectionManager(adapter, repair_enabled=self.config.get('selection_repair', False))
                    switch_fn = (parent.switch_keyboard_layout if self.config.get('switch_layout_after_convert', True) else None)

                    orig, conv = sm.convert_selection(self.convert_text, user_dict=self.user_dict, switch_layout_fn=switch_fn, debug=self.config.get('debug'), prefer_trim_leading=prefer_trim_leading, user_has_selection=user_has_selection)

                    if conv:
                        if self.user_dict and not parent.last_auto_convert:
                            parent.last_manual_convert = {
                                'original': orig.strip().lower(),
                                'converted': conv.strip().lower(),
                                'from_lang': 'ru' if any(('А' <= c <= 'Я') or ('а' <= c <= 'я') for c in orig) else 'en',
                                'to_lang': 'ru' if any(('А' <= c <= 'Я') or ('а' <= c <= 'я') for c in conv) else 'en',
                                'time': time.time()
                            }

                        # Correction detection
                        auto_marker = parent.last_auto_convert or getattr(parent, '_recent_auto_marker', None)
                        if self.user_dict and auto_marker and parent.conversion_manager:
                            try:
                                if parent.conversion_manager.apply_correction(self.user_dict, auto_marker, orig, conv, debug=self.config.get('debug')):
                                    parent.last_auto_convert = None
                                    parent._recent_auto_marker = None
                            except Exception as e:
                                if self.config.get('debug'):
                                    print(f"⚠️ Error applying correction: {e}")

                    # finalize
                    parent.backspace_hold_detected = False
                    parent.update_selection_snapshot()
                    parent.clear_buffer()
                except Exception as e:
                    if self.config.get('debug'):
                        print(f"⚠️ SelectionManager failed: {e}")
                    # fallback to legacy path (let existing behavior run)
                    try:
                        if adapter:
                            adapter.ctrl_shift_left()
                        else:
                            self.system.xdotool_key('ctrl+shift+Left', timeout=0.3, stderr=subprocess.DEVNULL)
                        time.sleep(0.03)
                        # fallback: call old inline conversion flow
                        # (we keep it minimal to avoid code duplication)
                    except Exception:
                        if self.config.get('debug'):
                            print("⚠️ Legacy selection fallback failed")
                    
                # end selection handling (either via SelectionManager or fallback)
                
                # КРИТИЧНО: Обновляем снимок ПОСЛЕ всех операций
                # Это выделение уже обработано и не должно считаться новым
                parent.update_selection_snapshot()
                
                # КРИТИЧНО: Очищаем буфер после конвертации выделенного
                # Иначе повторная конвертация попытается использовать старые данные
                parent.clear_buffer()
            else:
                if self.config.get('debug'):
                    print("⚠️  Нет выделенного текста")
                
        except Exception as e:
            print(f"⚠️  Ошибка конвертации выделенного: {e}")
            if self.config.get('debug'):
                import traceback
                traceback.print_exc()
        finally:
            # Give a small grace period for any synthetic events emitted by
            # the selection conversion/adapters to be processed.
            time.sleep(0.05)
            # Emit explicit Shift releases to avoid stuck-key scenarios
            try:
                parent.fake_kb.write(ecodes.EV_KEY, ecodes.KEY_LEFTSHIFT, 0)
                parent.fake_kb.syn()
                parent.fake_kb.write(ecodes.EV_KEY, ecodes.KEY_RIGHTSHIFT, 0)
                parent.fake_kb.syn()
            except Exception:
                pass
            parent.suppress_shift_detection = False
            if self.config.get('debug'):
                print(f"{time.time():.6f} ▸ convert_selection EXIT: suppress={parent.suppress_shift_detection}, is_converting={parent.is_converting}, last_shift_press={parent.last_shift_press:.6f}", flush=True)
            # Reset marker as a safety measure
            parent.last_shift_press = 0
            try:
                if hasattr(parent, 'input_handler') and parent.input_handler:
                    parent.input_handler._shift_pressed = False
                    parent.input_handler._shift_last_press_time = 0.0
            except Exception:
                pass
            # Allow a short grace period and clear the converting flag so subsequent
            # conversion requests are permitted.
            time.sleep(0.05)
            parent.is_converting = False