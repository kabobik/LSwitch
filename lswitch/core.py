#!/usr/bin/env python3
"""
LSwitch - Layout Switcher for Linux (evdev version)
Переключатель раскладки по двойному нажатию Shift
"""

import sys
import time
from lswitch import system as system
import json
import os
import collections
import selectors
import getpass
import signal
import threading
import ctypes
import ctypes.util

# Добавляем /usr/local/bin в путь для импорта dictionary.py
# Также добавляем /usr/local/lib/lswitch в путь — туда копирует инсталлятор утилиты `utils` и `adapters`

try:
    import evdev
    from evdev import ecodes
except ImportError:
    print("❌ Ошибка: установите python3-evdev")
    print("   sudo apt install python3-evdev")
    exit(1)

# Глобальный реестр экземпляров LSwitch (для тестовой/аварийной очистки)
LS_INSTANCES = []

def register_instance(inst):
    try:
        LS_INSTANCES.append(inst)
    except Exception:
        pass


def force_release_virtual_keyboards():
    """Force-close virtual keyboards created by LSwitch instances.

    This is intended as a safety mechanism for tests or emergency recovery
    when a test or process hangs while holding a virtual input device.
    It will attempt to close any `fake_kb` found on registered instances.
    Returns number of instances touched.
    """
    touched = 0
    for inst in list(LS_INSTANCES):
        try:
            if getattr(inst, 'fake_kb', None):
                try:
                    inst.fake_kb.close()
                except Exception:
                    pass
            touched += 1
        except Exception:
            pass
    return touched

try:
    from Xlib import display, X
    XLIB_AVAILABLE = True
except ImportError as e:
    XLIB_AVAILABLE = False
    print(f"⚠️  python-xlib не найден: {e}")
    print("   sudo apt install python3-xlib")

from lswitch.xkb import (
    XKB_AVAILABLE,
    libX11,
    XkbStateRec,
    get_layouts_from_xkb,
    get_current_layout,
    keycode_to_char,
)

# Импортируем словарь для автопереключения
try:
    from lswitch.dictionary import is_likely_wrong_layout
    DICT_AVAILABLE = True
except ImportError:
    DICT_AVAILABLE = False
    print("⚠️  Словарь не найден, автопереключение недоступно")

# Импортируем пользовательский словарь для самообучения
try:
    from lswitch.user_dictionary import UserDictionary
    USER_DICT_AVAILABLE = True
except ImportError:
    USER_DICT_AVAILABLE = False
    if os.path.exists('/usr/local/bin/user_dictionary.py'):
        print("⚠️  user_dictionary.py найден но не импортируется")


# Adapter для X11 (xclip/xdotool) — можно мокировать в тестах
try:
    from adapters import x11 as x11_adapter
except Exception:
    x11_adapter = None

# Импорты процессоров для рефакторинга
from lswitch.processors.text_processor import TextProcessor
from lswitch.processors.buffer_manager import BufferManager

# Импорт карт конвертации
from lswitch.conversion_maps import EN_TO_RU, RU_TO_EN


class LSwitch:
    # Proxy properties for backwards compatibility — делегируют к self.buffer
    @property
    def event_buffer(self):
        return self.buffer.event_buffer

    @event_buffer.setter
    def event_buffer(self, val):
        # val should be an iterable of events
        try:
            self.buffer.set_events(list(val))
        except Exception:
            self.buffer.event_buffer = val

    @property
    def text_buffer(self):
        return self.buffer.text_buffer

    @text_buffer.setter
    def text_buffer(self, val):
        self.buffer.text_buffer = list(val)

    @property
    def chars_in_buffer(self):
        return self.buffer.chars_in_buffer

    @chars_in_buffer.setter
    def chars_in_buffer(self, val):
        self.buffer.chars_in_buffer = int(val)

    def run(self):
        """Compatibility run loop (minimal evdev event loop).

        This method keeps the process alive and reads input events from
        available devices, dispatching them to `handle_event`.
        It's a smaller, robust fallback to ensure the service runs even if
        the original run implementation is not bound to the class for some
        reason in the runtime environment.
        """
        import time
        print("🚀 LSwitch run loop (compat) starting...", flush=True)
        device_selector = selectors.DefaultSelector()
        devices = []
        for path in evdev.list_devices():
            try:
                device = evdev.InputDevice(path)
                if device.name == self.fake_kb_name:
                    continue
                caps = device.capabilities()
                if ecodes.EV_KEY not in caps:
                    continue
                keys = caps.get(ecodes.EV_KEY, [])
                if not keys:
                    continue
                is_keyboard = ecodes.KEY_A in keys
                is_mouse = ecodes.BTN_LEFT in keys or ecodes.BTN_RIGHT in keys
                if not (is_keyboard or is_mouse):
                    continue
                device_selector.register(device, selectors.EVENT_READ)
                devices.append(device)
                if self.config.get('debug'):
                    device_type = "клавиатура" if is_keyboard else "мышь"
                    print(f"   Подключено: {device.name} ({device_type})", flush=True)
            except (OSError, PermissionError) as e:
                if self.config.get('debug'):
                    print(f"   Пропущено {path}: {e}", flush=True)
        if not devices:
            print("⚠️ Нет устройств ввода — запущено в режиме ожидания", flush=True)
        try:
            while self.running:
                events = device_selector.select(timeout=1)
                for key, mask in events:
                    device = key.fileobj
                    for event in device.read():
                        try:
                            self.handle_event(event)
                        except Exception:
                            pass
                time.sleep(0.01)
        except KeyboardInterrupt:
            self.running = False

    def load_config(self, config_path=None):
        """Delegate to `lswitch.config.load_config` (non-verbose by default).

        If `config_path` is None, use the test override `LSWITCH_TEST_SYSTEM_CONFIG`
        environment variable or the system default. Ensure a user config file
        in `~/.config/lswitch/config.json` exists (tests expect it to be created
        when missing).
        """
        if config_path is None:
            config_path = os.environ.get('LSWITCH_TEST_SYSTEM_CONFIG') or '/etc/lswitch/config.json'

        try:
            from lswitch import config as _cfg
            cfg = _cfg.load_config(config_path, debug=False)
        except Exception:
            # Ultimate fallback: return minimal defaults
            cfg = {
                'double_click_timeout': 0.3,
                'debug': False,
                'switch_layout_after_convert': True,
                'layout_switch_key': 'Alt_L+Shift_L',
                'auto_switch': False,
                '_config_path': config_path,
                '_user_config_path': None
            }

        # Ensure a user config file exists (tests expect creation)
        try:
            user_cfg_path = cfg.get('_user_config_path')
            if not user_cfg_path:
                user_cfg_path = os.path.expanduser('~/.config/lswitch/config.json')
                user_cfg_dir = os.path.dirname(user_cfg_path)
                if not os.path.exists(user_cfg_dir):
                    os.makedirs(user_cfg_dir, exist_ok=True)
                if not os.path.exists(user_cfg_path):
                    # Write minimal config so tests can assert file existence
                    import json
                    with open(user_cfg_path, 'w', encoding='utf-8') as f:
                        json.dump({
                            'double_click_timeout': cfg.get('double_click_timeout', 0.3),
                            'debug': cfg.get('debug', False),
                            'switch_layout_after_convert': cfg.get('switch_layout_after_convert', True),
                            'layout_switch_key': cfg.get('layout_switch_key', 'Alt_L+Shift_L'),
                            'auto_switch': cfg.get('auto_switch', False),
                        }, f, indent=2)
                    cfg['_user_config_path'] = user_cfg_path
        except Exception:
            pass

        return cfg

    def reload_config(self):
        """Перезагружает конфигурацию без перезапуска"""
        print("🔄 Перезагрузка конфигурации...", flush=True)
        old_config = self.config.copy()
        self.config = self.load_config(self.config.get('_config_path', '/etc/lswitch/config.json'))
        
        # Обновляем параметры
        self.double_click_timeout = self.config.get('double_click_timeout', 0.3)
        self.auto_switch_enabled = self.config.get('auto_switch', False)

        # Diagnostic/logging: show effective values after reload
        print(f"✓ Конфигурация перезагружена: auto_switch={self.auto_switch_enabled}, debug={self.config.get('debug')}, user_cfg={self.config.get('_user_config_path')}")
        print(f"✓ DICT_AVAILABLE={DICT_AVAILABLE}, USER_DICT_AVAILABLE={USER_DICT_AVAILABLE}, user_dict_loaded={bool(self.user_dict)}")

    def __init__(self, config_path=None, start_threads=True, system=None, input_handler=None, layout_monitor=None):
        """Initialise LSwitch.

        start_threads: when False, skip starting background threads and some
        runtime integrations (useful for unit testing without X11/evdev).

        system: optional `ISystem` implementation for dependency injection.
                If not provided, the module-level `lswitch.system.SYSTEM` is used.
        input_handler: optional instance implementing `.handle_event()` for DI.
        layout_monitor: optional instance implementing `.start()`/`.stop()` and
                        providing `.thread_layout` and `.thread_file` attributes.
        """
        # If tests explicitly request monitors to be disabled, respect that
        if os.environ.get('LSWITCH_TEST_DISABLE_MONITORS') == '1':
            start_threads = False

        # Автоматически определяем путь к конфигурации
        if config_path is None:
            if os.path.exists('/etc/lswitch/config.json'):
                config_path = '/etc/lswitch/config.json'
            else:
                config_path = 'config.json'
        
        # Dependency-injectable system wrapper (default to module SYSTEM)
        if system is None:
            try:
                from lswitch import system as _system_mod
                self.system = _system_mod.SYSTEM
            except Exception:
                # Ultimate fallback: keep using the module-level convenience
                # functions (legacy behaviour) if SYSTEM is not available.
                import lswitch as _pkg
                self.system = getattr(_pkg, 'system', None)
        else:
            self.system = system

        # Optional injection points for easier testing
        self._injected_input_handler = input_handler
        self._injected_layout_monitor = layout_monitor

        self.config = self.load_config(config_path)
        
        # Initialize processors for refactoring
        self.text_processor = TextProcessor(None, self.config)  # system passed later
        self.buffer_manager = BufferManager(self.config, debug=self.config.get('debug', False))
        
        # Track mtime safely — file may not exist in test environments
        cfg_path = self.config.get('_config_path')
        if cfg_path is None:
            cfg_path = self.config.get('_user_config_path')
        if cfg_path is None:
            cfg_path = '/etc/lswitch/config.json'
        try:
            if isinstance(cfg_path, str):
                self.config_mtime = os.path.getmtime(cfg_path)
            else:
                self.config_mtime = None
        except (OSError, FileNotFoundError, TypeError):
            self.config_mtime = None

        self.last_shift_press = 0
        self.double_click_timeout = self.config.get('double_click_timeout', 0.3)
        # Flag used to temporarily suppress double-Shift detection while the
        # instance is programmatically replaying events (to avoid re-triggering
        # conversions due to synthetic Shift events emitted during replay).
        self.suppress_shift_detection = False
        # Short-lived post-replay suppression window (timestamp). During this
        # period we also ignore double-shift detection to account for timing
        # and delivery delays of synthetic events.
        self._post_replay_suppress_until = 0.0
        
        # Создаём виртуальную клавиатуру для эмуляции событий
        self.fake_kb_name = 'LSwitch Virtual Keyboard'
        # evdev.UInput может требовать прав — в тестах мы мокаем этот класс
        self.fake_kb = evdev.UInput(name=self.fake_kb_name)

        # Регистрируем экземпляр (позволяет провести аварийную очистку извне)
        try:
            register_instance(self)
        except Exception:
            pass

        # Keyboard controller wraps fake_kb operations
        from lswitch.utils.keyboard import KeyboardController
        self.kb = KeyboardController(self.fake_kb)
        
        # Инкапсулированный буфер ввода
        from lswitch.utils.buffer import InputBuffer
        self.buffer = InputBuffer(maxlen=1000)

        # InputHandler encapsulates input/event handling logic
        if self._injected_input_handler is not None:
            self.input_handler = self._injected_input_handler
        else:
            try:
                from lswitch.input import InputHandler
                self.input_handler = InputHandler(self)
            except Exception:
                self.input_handler = None
        
        # Update text_processor with system after it's available
        self.text_processor.system = self.system

        # Проекционные свойства для обратной совместимости
        self.had_backspace = False  # Флаг: был ли backspace (пользователь исправляет)
        self.consecutive_backspace_repeats = 0  # Счетчик подряд идущих repeat Backspace
        self.backspace_hold_detected = False  # Флаг удержания Backspace
        
        # Ссылка на текущее устройство для отладки
        self.current_device = None

        # X11 для определения раскладки через XKB
        self.x11_display = display.Display() if XLIB_AVAILABLE else None
        self.layouts = self.get_layouts_from_xkb()

        # Проверка минимум 2 раскладок для работы
        if len(self.layouts) < 2:
            print(f"⚠️  Обнаружена только {len(self.layouts)} раскладка: {self.layouts}")
            print("   Программа будет работать в ограниченном режиме (без конвертации)")
        else:
            print(f"✓ Раскладки готовы: {self.layouts}")

        # Синхронизация текущей раскладки
        self.current_layout = self.get_current_layout()
        self.layout_lock = threading.Lock()
        self.running = True

        # Пользовательский словарь для самообучения
        self.user_dict = None
        self.last_auto_convert = None  # {"word": original, "converted_to": result, "time": timestamp, "lang": lang}
        self.last_manual_convert = None  # {"original": text, "converted": result, "from_lang": lang, "to_lang": lang, "time": timestamp}
        if USER_DICT_AVAILABLE and self.config.get('user_dict_enabled', False):
            try:
                self.user_dict = UserDictionary()
                min_weight = self.config.get('user_dict_min_weight', 2)
                self.user_dict.data['settings']['min_weight'] = min_weight
                if self.config.get('debug'):
                    stats = self.user_dict.get_stats()
                    print(f"📚 UserDict загружен: {stats['total_words']} слов, {stats['total_conversions']} конвертаций, {stats['total_corrections']} корректировок")
            except Exception as e:
                print(f"⚠️  Ошибка загрузки UserDict: {e}")
                self.user_dict = None
        
        # Update text_processor with user_dict after it's available  
        self.text_processor.user_dict = self.user_dict

        # Start background threads and runtime integrations only if requested
        if start_threads:
            # Use LayoutMonitor to manage layout polling and runtime file monitoring
            try:
                from lswitch.monitor import LayoutMonitor
                if self._injected_layout_monitor is not None:
                    # Use the provided instance; do not recreate
                    self.layout_monitor = self._injected_layout_monitor
                else:
                    self.layout_monitor = LayoutMonitor(self)

                # Start the monitor if it is not already running
                if not getattr(self.layout_monitor, 'running', False):
                    self.layout_monitor.start()

                # Keep old attributes for backwards compatibility
                self.layout_thread = self.layout_monitor.thread_layout
                self.layouts_file_monitor_thread = self.layout_monitor.thread_file
            except Exception:
                # Fallback to legacy threads if monitor import fails
                self.layout_thread = threading.Thread(target=self.monitor_layout_changes, daemon=True)
                self.layout_thread.start()
                self.layouts_file_monitor_thread = threading.Thread(target=self.monitor_layouts_file, daemon=True)
                self.layouts_file_monitor_thread.start()

            # Применяем раскладки к виртуальному устройству (иначе KDE глючит)
            self.configure_virtual_keyboard_layouts()

            # Conversion manager: centralizes mode selection
            try:
                from conversion import ConversionManager
                import lswitch as _pkg
                cm_x11 = getattr(_pkg, 'x11_adapter', x11_adapter)
                self.conversion_manager = ConversionManager(config=self.config, x11_adapter=cm_x11)
            except Exception:
                self.conversion_manager = None
        else:
            # Placeholders so tests can inspect attributes without starting threads
            self.layout_thread = None
            self.layouts_file_monitor_thread = None
            self.conversion_manager = None

            # If a layout monitor was injected, attach it but do NOT start it
            if self._injected_layout_monitor is not None:
                self.layout_monitor = self._injected_layout_monitor
        
        # Ссылка на текущее устройство для отладки
        self.current_device = None
        
        # X11 для определения раскладки через XKB
        self.x11_display = display.Display() if XLIB_AVAILABLE else None
        self.layouts = self.get_layouts_from_xkb()
        
        # Проверка минимум 2 раскладок для работы
        if len(self.layouts) < 2:
            print(f"⚠️  Обнаружена только {len(self.layouts)} раскладка: {self.layouts}")
            print("   Программа будет работать в ограниченном режиме (без конвертации)")
        else:
            print(f"✓ Раскладки готовы: {self.layouts}")
        
        # Синхронизация текущей раскладки
        self.current_layout = self.get_current_layout()
        self.layout_lock = threading.Lock()
        self.running = True
        
        # Пользовательский словарь для самообучения
        self.user_dict = None
        self.last_auto_convert = None  # {"word": original, "converted_to": result, "time": timestamp, "lang": lang}
        self.last_manual_convert = None  # {"original": text, "converted": result, "from_lang": lang, "to_lang": lang, "time": timestamp}
        if USER_DICT_AVAILABLE and self.config.get('user_dict_enabled', False):
            try:
                self.user_dict = UserDictionary()
                min_weight = self.config.get('user_dict_min_weight', 2)
                self.user_dict.data['settings']['min_weight'] = min_weight
                if self.config.get('debug'):
                    stats = self.user_dict.get_stats()
                    print(f"📚 UserDict загружен: {stats['total_words']} слов, {stats['total_conversions']} конвертаций, {stats['total_corrections']} корректировок")
            except Exception as e:
                print(f"⚠️  Ошибка загрузки UserDict: {e}")
                self.user_dict = None
        
        
        # Коды клавиш для отслеживания (алфавитно-цифровые + пробел)
        self.active_keycodes = set(range(2, 58))  # От '1' до '/'
        self.active_keycodes.add(ecodes.KEY_SPACE)  # Добавляем пробел!
        self.active_keycodes.difference_update((15, 28, 29, 56))  # Убираем Tab, Enter, Ctrl, Alt
        
        # Клавиши навигации - очищают буфер
        self.navigation_keys = {
            ecodes.KEY_LEFT, ecodes.KEY_RIGHT, ecodes.KEY_UP, ecodes.KEY_DOWN,
            ecodes.KEY_HOME, ecodes.KEY_END, ecodes.KEY_PAGEUP, ecodes.KEY_PAGEDOWN,
            ecodes.KEY_TAB
        }
        
        self.is_converting = False
        
        # Отслеживание реального выделения
        self.last_known_selection = ''  # Последняя известная PRIMARY selection
        self.selection_timestamp = 0  # Время последнего изменения выделения
        
        # Флаг: последний введённый символ был пробелом
        self.last_was_space = False
        
        # Для автопереключения
        self.auto_switch_enabled = self.config.get('auto_switch', False)
        
        # Флаг для перезагрузки конфигурации
        self.config_reload_requested = False
        
        # Отслеживание изменений конфига
        try:
            cfg_path = self.config.get('_config_path') or self.config.get('_user_config_path')
            if cfg_path is None:
                cfg_path = '/etc/lswitch/config.json'
            if isinstance(cfg_path, str):
                self.config_mtime = os.path.getmtime(cfg_path)
            else:
                self.config_mtime = None
        except (OSError, FileNotFoundError, TypeError):
            self.config_mtime = None
        self.last_config_check = time.time()
    
    def get_layouts_from_xkb(self):
        """Delegate to `lswitch.xkb.get_layouts_from_xkb` (keeps debug from config)."""
        return get_layouts_from_xkb(debug=self.config.get('debug'))
    
    def get_current_layout(self):
        """Delegate to `lswitch.xkb.get_current_layout` using cached layouts."""
        return get_current_layout(self.layouts, debug=self.config.get('debug'))
    
    def keycode_to_char(self, keycode, layout='en', shift=False):
        """Delegate to `lswitch.xkb.keycode_to_char` using current layouts and debug flag."""
        return keycode_to_char(keycode, layout, self.layouts, shift=shift, debug=self.config.get('debug'))
    
    def get_buffer_text(self):
        """Извлекает текст из буфера событий"""
        text = []
        for event in self.event_buffer:
            if event.value == 0:  # Отпускание клавиши
                if event.code == ecodes.KEY_BACKSPACE:
                    if text:
                        text.pop()
                elif event.code == ecodes.KEY_SPACE:
                    text.append(' ')
                elif event.code in range(2, 14):  # Цифры
                    keys = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0', '-', '=']
                    if event.code - 2 < len(keys):
                        text.append(keys[event.code - 2])
                elif event.code in range(16, 28):  # QWERTY верхний ряд
                    keys = ['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p', '[', ']']
                    if event.code - 16 < len(keys):
                        text.append(keys[event.code - 16])
                elif event.code in range(30, 41):  # ASDF средний ряд
                    keys = ['a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l', ';', "'"]
                    if event.code - 30 < len(keys):
                        text.append(keys[event.code - 30])
                elif event.code in range(44, 54):  # ZXCV нижний ряд
                    keys = ['z', 'x', 'c', 'v', 'b', 'n', 'm', ',', '.', '/']
                    if event.code - 44 < len(keys):
                        text.append(keys[event.code - 44])
        return ''.join(text)
    
    def monitor_layout_changes(self):
        """Мониторинг событий смены раскладки через X11 PropertyNotify"""
        if not XLIB_AVAILABLE:
            # Фолбэк на опрос если Xlib недоступен
            last_layout = self.get_current_layout()
            if self.config.get('debug'):
                print(f"⚠️  X11 недоступен, используем опрос (раз в секунду, текущая: {last_layout})")
            
            while self.running:
                try:
                    time.sleep(1)
                    new_layout = self.get_current_layout()
                    
                    with self.layout_lock:
                        if new_layout != last_layout:
                            old_layout = last_layout
                            last_layout = new_layout
                            self.current_layout = new_layout
                            
                            if self.config.get('debug'):
                                print(f"🔄 Раскладка изменена: {old_layout} → {new_layout}")
                except Exception as e:
                    if self.config.get('debug'):
                        print(f"⚠️  Ошибка опроса раскладки: {e}")
                    time.sleep(5)
            return
        
        # X11 мониторинг через события
        try:
            disp = display.Display()
            root = disp.screen().root
            
            # Подписываемся на PropertyNotify события
            root.change_attributes(event_mask=X.PropertyChangeMask)
            
            if self.config.get('debug'):
                print(f"✓ X11: Подписка на события смены раскладки активна (текущая: {self.current_layout})")
            
            last_check_time = time.time()
            
            while self.running:
                # Проверяем наличие событий
                while disp.pending_events() > 0:
                    event = disp.next_event()
                    
                    # При PropertyNotify проверяем раскладку
                    current_time = time.time()
                    if current_time - last_check_time >= 0.1:  # Не чаще 10 раз/сек
                        last_check_time = current_time
                        new_layout = self.get_current_layout()
                        
                        with self.layout_lock:
                            if new_layout != self.current_layout:
                                old_layout = self.current_layout
                                self.current_layout = new_layout
                                
                                if self.config.get('debug'):
                                    print(f"🔄 X11: Раскладка изменена {old_layout} → {new_layout}")
                
                # Небольшая задержка
                time.sleep(0.05)
                
        except Exception as e:
            if self.config.get('debug'):
                print(f"⚠️  Ошибка X11 мониторинга: {e}, переключаемся на опрос")
            
            # Фолбэк на опрос при ошибке X11
            last_layout = self.current_layout
            while self.running:
                try:
                    time.sleep(1)
                    new_layout = self.get_current_layout()
                    
                    with self.layout_lock:
                        if new_layout != last_layout:
                            old_layout = last_layout
                            last_layout = new_layout
                            self.current_layout = new_layout
                            
                            if self.config.get('debug'):
                                print(f"🔄 Раскладка изменена: {old_layout} → {new_layout}")
                except:
                    pass
    
    def monitor_layouts_file(self):
        """Мониторит изменения файла с раскладками от control panel"""
        runtime_dir = os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')
        layouts_file = f'{runtime_dir}/lswitch_layouts.json'
        last_mtime = 0
        
        while self.running:
            try:
                if os.path.exists(layouts_file):
                    current_mtime = os.path.getmtime(layouts_file)
                    
                    # Если файл изменился
                    if current_mtime != last_mtime:
                        last_mtime = current_mtime
                        
                        # Читаем новые раскладки
                        try:
                            with open(layouts_file, 'r') as f:
                                data = json.load(f)
                                new_layouts = data.get('layouts', [])
                                
                                if new_layouts and new_layouts != self.layouts:
                                    old_layouts = self.layouts
                                    self.layouts = new_layouts
                                    
                                    if self.config.get('debug'):
                                        print(f"🔄 Раскладки обновлены из файла: {old_layouts} → {new_layouts}", flush=True)
                                    
                                    # Проверяем достаточность раскладок
                                    if len(self.layouts) < 2:
                                        print(f"⚠️  ВНИМАНИЕ: Теперь только {len(self.layouts)} раскладка!")
                                    
                        except Exception as e:
                            if self.config.get('debug'):
                                print(f"⚠️  Ошибка чтения файла раскладок: {e}", flush=True)
                
                time.sleep(2)  # Проверяем каждые 2 секунды
                
            except Exception as e:
                if self.config.get('debug'):
                    print(f"⚠️  Ошибка мониторинга файла раскладок: {e}", flush=True)
                time.sleep(5)
    
    def configure_virtual_keyboard_layouts(self):
        """Настраивает раскладки виртуального устройства под системные (фикс для KDE)"""
        try:
            # Проверяем что system инициализирован
            if self.system is None:
                if self.config.get('debug'):
                    print(f"⚠️  System не инициализирована, пропускаем настройку раскладок", flush=True)
                return
            
            # Ищем ID нашего виртуального устройства
            result = self.system.xinput_list_id(self.fake_kb_name, timeout=2)
            
            device_id = result.stdout.strip()
            if not device_id:
                if self.config.get('debug'):
                    print(f"⚠️  Не найдено виртуальное устройство '{self.fake_kb_name}'")
                return
            
            # Конвертируем раскладки (en/ru -> us/ru для setxkbmap)
            xkb_layouts = ','.join('us' if l == 'en' else l for l in self.layouts)
            
            # Применяем раскладки к виртуальному устройству
            self.system.run(['setxkbmap', '-device', device_id, '-layout', xkb_layouts], capture_output=True, timeout=2, env={'DISPLAY': ':0'})
            
            if self.config.get('debug'):
                print(f"✓ Виртуальная клавиатура настроена: раскладки {xkb_layouts}")
                
        except Exception as e:
            if self.config.get('debug'):
                print(f"⚠️  Не удалось настроить виртуальную клавиатуру: {e}")
    
    def check_and_auto_convert(self):
        """Delegate to `lswitch.conversion.check_and_auto_convert` for auto-conversion."""
        try:
            from lswitch import conversion as _conv
            return _conv.check_and_auto_convert(self)
        except Exception:
            # Fallback: run existing inline logic if import fails (robustness)
            return None
                    
        except ImportError:
            # Фолбэк на старую логику если ngrams.py недоступен
            if self.config.get('debug'):
                print(f"⚠️  ngrams.py недоступен, используем базовую логику")
            self._check_with_dictionary(text)
        except Exception as e:
            if self.config.get('debug'):
                import traceback
                print(f"⚠️  Ошибка автоконвертации: {e}")
                traceback.print_exc()    
    def _check_with_dictionary(self, text):
        """Legacy wrapper that delegates to `lswitch.conversion._check_with_dictionary`."""
        try:
            from lswitch import conversion as _conv
            return _conv._check_with_dictionary(self, text)
        except Exception:
            # Fallback to original inline behavior if delegation fails
            try:
                from lswitch.dictionary import check_word, convert_text
                is_correct, _ = check_word(text, self.current_layout)
                if not is_correct:
                    converted = convert_text(text, self.current_layout)
                    is_conv_correct, _ = check_word(converted, 'en' if self.current_layout == 'ru' else 'ru')
                    if is_conv_correct:
                        if self.config.get('debug'):
                            print(f"🤖 Auto-convert (dictionary): '{text}' → '{converted}'")
                        self.convert_and_retype()
            except Exception as e:
                if self.config.get('debug'):
                    print(f"⚠️  Error in dictionary fallback: {e}")
    

    def tap_key(self, keycode, n_times=1):
        """Proxy to KeyboardController.tap_key for compatibility"""
        try:
            self.kb.tap_key(keycode, n_times=n_times)
        except Exception:
            # Fallback to direct uinput
            for _ in range(n_times):
                self.fake_kb.write(ecodes.EV_KEY, keycode, 1)
                self.fake_kb.syn()
                self.fake_kb.write(ecodes.EV_KEY, keycode, 0)
                self.fake_kb.syn()

    def replay_events(self, events):
        """Proxy to KeyboardController.replay_events for compatibility"""
        try:
            self.kb.replay_events(events)
        except Exception:
            for event in events:
                self.fake_kb.write(ecodes.EV_KEY, event.code, event.value)
                self.fake_kb.syn()
    
    def replay_events(self, events):
        """Delegate to InputHandler.replay_events when available."""
        if getattr(self, 'input_handler', None):
            return self.input_handler.replay_events(events)
        # Fallback: direct write
        for event in events:
            try:
                self.fake_kb.write(ecodes.EV_KEY, event.code, event.value)
                self.fake_kb.syn()
            except Exception:
                pass

    def _fallback_type_text(self, text: str):
        """Fallback typing: type characters from `text` using `tap_key` for common glyphs.

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

        for ch in text:
            if not ch:
                continue
            lower = ch.lower()
            code = CHAR_MAP.get(lower)
            # Support Cyrillic characters by mapping via RU_TO_EN when needed
            if code is None:
                try:
                    from lswitch.conversion import RU_TO_EN
                    mapped = RU_TO_EN.get(lower)
                    if mapped:
                        code = CHAR_MAP.get(mapped.lower())
                except Exception:
                    pass

            if code is None:
                # Unsupported char — skip for now
                continue

            try:
                self.tap_key(code, n_times=1)
            except Exception:
                # Last resort: direct uinput writes
                try:
                    self.fake_kb.write(ecodes.EV_KEY, code, 1)
                    self.fake_kb.syn()
                    self.fake_kb.write(ecodes.EV_KEY, code, 0)
                    self.fake_kb.syn()
                except Exception:
                    pass
    
    def clear_buffer(self):
        """Очищает буфер событий и текстовый буфер"""
        # Делегируем реальную очистку инкапсулированному буферу
        try:
            self.buffer.clear()
        except Exception:
            # Фолбэк: старое поведение в случае ошибки
            currently_pressed = {}
            for event in getattr(self, 'event_buffer', []):
                if event.code in (ecodes.BTN_LEFT, ecodes.BTN_RIGHT, ecodes.BTN_MIDDLE):
                    continue
                if event.value == 1:
                    currently_pressed[event.code] = event
                elif event.value == 0:
                    currently_pressed.pop(event.code, None)
            if hasattr(self, 'event_buffer'):
                self.event_buffer.clear()
                for ev in currently_pressed.values():
                    self.event_buffer.append(ev)
            self.chars_in_buffer = 0
            self.text_buffer.clear()

        # Сбрасываем локальные флаги Backspace
        self.had_backspace = False
        self.consecutive_backspace_repeats = 0
        # Keep backspace_hold flag recent timestamp; do not eagerly clear it here
        # to avoid losing the hold marker due to incidental navigation/events.
        if getattr(self, 'backspace_hold_detected_at', 0) and (time.time() - self.backspace_hold_detected_at) < 0.5:
            # Recent hold: preserve flag for short window
            if self.config.get('debug'):
                print(f"{time.time():.6f} ▸ Preserving backspace_hold_detected (recent: {time.time() - self.backspace_hold_detected_at:.3f}s)", flush=True)
            # leave self.backspace_hold_detected as-is
        else:
            self.backspace_hold_detected = False
            self.backspace_hold_detected_at = 0.0

        # NOTE: раньше тут обнулялся last_auto_convert, но это мешало ручной коррекции сразу после автоконвертации.
        # Оставляем last_auto_convert до тех пор, пока пользователь не начнёт ввод (в другом месте оно сбрасывается),
        # либо пока не истечёт timeout correction_timeout при проверке коррекции.
    
    def convert_text(self, text):
        """Конвертирует текст между раскладками с сохранением регистра"""
        return self.text_processor.convert_text(text)
    
    def convert_selection(self, prefer_trim_leading=False, user_has_selection=False):
        """Конвертирует выделенный текст через PRIMARY selection (без порчи clipboard)"""
        return self.text_processor.convert_selection(self, prefer_trim_leading, user_has_selection)

    def switch_keyboard_layout(self):
        """Переключает раскладку клавиатуры через XKB LockGroup"""
        try:
            # Переключаем через XKB LockGroup (правильный способ)
            if XKB_AVAILABLE and libX11:
                display_ptr = libX11.XOpenDisplay(None)
                if display_ptr:
                    try:
                        # Читаем текущее состояние
                        state_before = XkbStateRec()
                        status = libX11.XkbGetState(display_ptr, 0x100, ctypes.byref(state_before))
                        current_index = state_before.group
                        
                        if self.config.get('debug'):
                            print(f"🔄 Переключаю раскладку... (текущая группа: {current_index}, status: {status})")
                            print(f"   len(self.layouts)={len(self.layouts)}, layouts={self.layouts}")
                        
                        # Циклически переключаем на следующую
                        next_index = (current_index + 1) % len(self.layouts)
                        
                        if self.config.get('debug'):
                            print(f"   Вычислено: ({current_index} + 1) % {len(self.layouts)} = {next_index}")
                        
                        # XkbLockGroup(display, device, group)
                        # device=0x100 = XkbUseCoreKbd
                        ret = libX11.XkbLockGroup(display_ptr, 0x100, next_index)
                        libX11.XFlush(display_ptr)
                        
                        if self.config.get('debug'):
                            print(f"   XkbLockGroup вернула: {ret}, переключено на группу {next_index}")
                        
                        # Обновляем кеш текущей раскладки
                        self.current_layout = self.layouts[next_index] if next_index < len(self.layouts) else self.layouts[0]
                        
                        if self.config.get('debug'):
                            current_layout = self.layouts[current_index] if current_index < len(self.layouts) else 'unknown'
                            print(f"✓ Раскладка переключена: {current_layout} → {self.current_layout}")
                    finally:
                        libX11.XCloseDisplay(display_ptr)
            else:
                if self.config.get('debug'):
                    print(f"🔄 Переключаю раскладку через xdotool...")
                    
                # Fallback через xdotool
                old_layout = self.current_layout
                self.system.xdotool_key('Alt_L+Shift_L', timeout=1)
                # Обновляем кеш
                time.sleep(0.05)
                self.current_layout = self.get_current_layout()
                if self.config.get('debug'):
                    print(f"✓ Раскладка переключена: {old_layout} → {self.current_layout}")
                    
        except Exception as e:
            if self.config.get('debug'):
                print(f"⚠️  Ошибка переключения раскладки: {e}")
    
    def has_selection(self):
        """Проверяет есть ли СВЕЖЕЕ выделение (изменилось с прошлого раза)"""
        try:
            result = self.system.xclip_get(selection='primary', timeout=0.3)
            current_selection = result.stdout
            
            # Есть выделение только если:
            # 1. PRIMARY не пустая
            # 2. PRIMARY изменилась с последнего раза (свежее выделение!)
            if current_selection and current_selection != self.last_known_selection:
                return True
            return False
        except Exception:
            return False
    
    def update_selection_snapshot(self):
        """Обновляет снимок текущей PRIMARY selection"""
        try:
            result = self.system.xclip_get(selection='primary', timeout=0.3)
            self.last_known_selection = result.stdout
            self.selection_timestamp = time.time()
        except Exception:
            pass
    
    def convert_and_retype(self, is_auto=False):  # is_auto=True when conversion was triggered by autocorrect
        """Переконвертировать текст в буфере и воспроизвести события.
        Если is_auto=True, не устанавливаем last_manual_convert и не считаем это за ручную конвертацию."""
        """Конвертирует и перепечатывает последнее слово"""
        # Проверяем наличие минимум 2 раскладок
        if len(self.layouts) < 2:
            if self.config.get('debug'):
                print(f"⚠️  Конвертация невозможна: только {len(self.layouts)} раскладка")
            return
        
        if self.is_converting or self.chars_in_buffer == 0:
            return
        
        self.is_converting = True
        if self.config.get('debug'):
            print(f"{time.time():.6f} ▸ convert_and_retype ENTER (is_auto={is_auto}) chars_in_buffer={self.chars_in_buffer} is_converting={self.is_converting} last_shift_press={self.last_shift_press:.6f} suppress={getattr(self,'suppress_shift_detection',False)}")

        
        # Если была недавняя автоконвертация — отметим её в логах, но НЕ очищаем маркер.
        # Это нужно, чтобы последующая ручная конвертация могла быть распознана как коррекция
        # (проверка и очистка выполняется в блоке для ручной конвертации ниже).
        if self.user_dict and self.last_auto_convert and self.config.get('debug'):
            age = time.time() - self.last_auto_convert['time']
            print(f"🔍 Обнаружена недавняя автоконвертация (age={age:.2f}s), проверку коррекции выполним позже")
        
        try:
            if self.config.get('debug'):
                print(f"Конвертирую {self.chars_in_buffer} символов...")

            # Support override from ngrams fallback: if _override_converted_text is set,
            # expose it as local converted_text so later logic will use it to update buffer
            if hasattr(self, '_override_converted_text'):
                converted_text = getattr(self, '_override_converted_text')
            
            # КРИТИЧНО: сохраняем копию событий ДО очистки буфера!
            events_to_replay = list(self.buffer.event_buffer)
            num_chars = self.buffer.chars_in_buffer
            
            # Сохраняем информацию для отслеживания успешной ручной конвертации
            # Только если это НЕ автоконвертация
            if not is_auto and self.user_dict and len(self.buffer.text_buffer) > 0:
                original_text = ''.join(self.buffer.text_buffer)
                # Определяем язык исходного текста
                has_cyrillic = any(('А' <= c <= 'Я') or ('а' <= c <= 'я') or c in 'ЁёЪъЬь' for c in original_text)
                from_lang = 'ru' if has_cyrillic else 'en'
                to_lang = 'en' if from_lang == 'ru' else 'ru'
                
                # Конвертируем текст чтобы узнать результат
                converted_text = self.convert_text(original_text)
                
                self.last_manual_convert = {
                    "original": original_text,
                    "converted": converted_text,
                    "from_lang": from_lang,
                    "to_lang": to_lang,
                    "time": time.time()
                }
                if self.config.get('debug'):
                    print(f"🔍 last_manual_convert (convert_and_retype - manual): {self.last_manual_convert}")

                # Если сразу после автоконвертации пользователь вручную вернул слово — фиксируем коррекцию
                auto_marker = self.last_auto_convert or getattr(self, '_recent_auto_marker', None)
                if self.user_dict and auto_marker and self.conversion_manager:
                    try:
                        if self.conversion_manager.apply_correction(self.user_dict, auto_marker, original_text, converted_text, debug=self.config.get('debug')):
                            # Очищаем запись о последней автоконвертации
                            self.last_auto_convert = None
                            self._recent_auto_marker = None
                        else:
                            if self.config.get('debug'):
                                print("🔍 Условие коррекции не выполнено — не будет add_correction")
                    except Exception as e:
                        print(f"⚠️ Ошибка при проверке коррекции: {e}")
                elif self.user_dict and auto_marker:
                    # Legacy behavior if ConversionManager is not available
                    try:
                        time_since_auto = time.time() - auto_marker['time']
                        timeout = self.user_dict.data['settings'].get('correction_timeout', 5.0)

                        # Канонизируем и сравниваем, чтобы избежать проблем с кейсом/раскладкой
                        def canon(s):
                            s_clean = (s or '').strip()
                            lang = 'ru' if any(('А' <= c <= 'Я') or ('а' <= c <= 'я') or c in 'ЁёЪъЬь' for c in s_clean) else 'en'
                            try:
                                return self.user_dict._canonicalize(s_clean, lang)
                            except Exception:
                                return s_clean.lower()

                        orig_canon = canon(original_text)
                        auto_conv_canon = canon(auto_marker.get('converted_to', ''))
                        conv_canon = canon(converted_text)
                        auto_word_canon = canon(auto_marker.get('word', ''))

                        if time_since_auto < timeout and orig_canon == auto_conv_canon and conv_canon == auto_word_canon:
                            corrected_word = converted_text.strip().lower()
                            has_cyrillic = any(('А' <= c <= 'Я') or ('а' <= c <= 'я') or c in 'ЁёЪъЬь' for c in corrected_word)
                            corrected_lang = 'ru' if has_cyrillic else 'en'

                            # Регистрируем коррекцию в словаре
                            print(f"📚 APPLY CORRECTION (legacy): '{corrected_word}' ({corrected_lang})")
                            self.user_dict.add_correction(corrected_word, corrected_lang, debug=self.config.get('debug'))

                            # Очищаем запись о последней автоконвертации
                            self.last_auto_convert = None
                            self._recent_auto_marker = None
                    except Exception as e:
                        print(f"⚠️ Ошибка при проверке коррекции (legacy): {e}")

            # Очищаем буфер (чтобы не накапливались события)
            self.clear_buffer()
            
            # Удаляем введённые символы
            self.tap_key(ecodes.KEY_BACKSPACE, num_chars)
            
            # Переключаем раскладку
            if self.config.get('switch_layout_after_convert', True):
                self.switch_keyboard_layout()
            
            time.sleep(0.02)  # Маленькая задержка перед вводом

            # Print a short summary of events and reason for suppression
            try:
                shift_count = sum(1 for ev in events_to_replay if getattr(ev, 'code', None) in (ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT))
                total = len(events_to_replay)
                if self.config.get('debug'):
                    print(f"{time.time():.6f} ▸ Preparing to replay events: total={total}, Shift_count={shift_count}, release_count={release_count if 'release_count' in locals() else 'unknown'}, suppress_before={getattr(self,'suppress_shift_detection',False)}", flush=True)
            except Exception:
                pass

            # Suppress double-Shift detection during replay/typing to avoid the
            # replayed Shift events retriggering conversions.
            self.suppress_shift_detection = True
            if self.config.get('debug'):
                print(f"{time.time():.6f} ▸ suppress_shift_detection=True (replay)", flush=True)
            try:
                # Воспроизводим сохранённые события в новой раскладке
                self.replay_events(events_to_replay)

                # Если реплей событий не содержал release-ивентов для обычных клавиш,
                # то на некоторых системах/адаптерах никакой текст не появится на экране.
                # В этом случае делаем fallback: напрямую набираем `converted_text` через tap_key.
                try:
                    release_count = sum(1 for ev in events_to_replay if getattr(ev, 'value', None) in (0, 2) and ev.code not in (ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT, ecodes.KEY_BACKSPACE))
                except Exception:
                    release_count = 0

                if release_count == 0 and 'converted_text' in locals() and converted_text:
                    try:
                        if self.config.get('debug'):
                            print("⚠️ Replay missing releases — using fallback typing for converted text")
                        self._fallback_type_text(converted_text)
                    except Exception as e:
                        if self.config.get('debug'):
                            print(f"⚠️ fallback typing failed: {e}")

                # КРИТИЧНО: заполняем буфер заново конвертированными событиями!
                # Это позволяет конвертировать назад при повторном двойном Shift
                try:
                    self.buffer.set_events(events_to_replay)
                    self.buffer.chars_in_buffer = num_chars
                except Exception:
                    # Фолбэк
                    self.event_buffer = collections.deque(events_to_replay, maxlen=1000)
                    self.chars_in_buffer = num_chars

                # ВАЖНО: обновляем текстовый буфер, чтобы он отражал текущий (сконвертированный) текст.
                # Иначе при немедленном ручном возврате (double Shift) мы будем читать старый текст и
                # неправильно фиксировать направление. Если у нас есть вычисленный converted_text — используем его.
                try:
                    if 'converted_text' in locals() and converted_text:
                        # converted_text — строка
                        self.buffer.text_buffer = list(converted_text)
                    else:
                        # Фолбэк: восстановим из событий, если есть
                        self.buffer.text_buffer = []
                        layout = self.get_current_layout()
                        for ev in events_to_replay:
                            if ev.value == 0:
                                ch = self.keycode_to_char(ev.code, layout, shift=False)
                                if ch:
                                    self.buffer.text_buffer.append(ch)
                except Exception:
                    # Не фатально — оставим буфер пустым
                    self.text_buffer = []
            finally:
                # Give a short grace period so replayed events can be fully processed by the event loop
                time.sleep(0.05)
                # As a safety, explicitly emit release events for Shift so that
                # the system/virtual device won't be left in a pressed state.
                try:
                    # Use fake_kb directly; we're still in suppression so these
                    # releases won't retrigger the handler.
                    self.fake_kb.write(ecodes.EV_KEY, ecodes.KEY_LEFTSHIFT, 0)
                    self.fake_kb.syn()
                    self.fake_kb.write(ecodes.EV_KEY, ecodes.KEY_RIGHTSHIFT, 0)
                    self.fake_kb.syn()
                except Exception:
                    pass

                self.suppress_shift_detection = False
                if self.config.get('debug'):
                    print(f"{time.time():.6f} ▸ suppress_shift_detection=False (replay complete)", flush=True)
                # Reset marker to avoid immediate re-detection and establish a
                # short post-replay suppression window to handle delayed delivery
                # of synthetic events.
                self.last_shift_press = 0
                # Also reset InputHandler's shift-pressed flag if present
                try:
                    if getattr(self, 'input_handler', None):
                        self.input_handler._shift_pressed = False
                        self.input_handler._shift_last_press_time = 0.0
                except Exception:
                    pass
                self._post_replay_suppress_until = time.time() + max(0.1, self.double_click_timeout)
            
            if self.config.get('debug'):
                print("✓ Конвертация завершена")

            # Обновляем снимок PRIMARY selection — это предотвращает ошибочное
            # определение "свежего выделения" сразу после ручной конвертации.
            try:
                self.update_selection_snapshot()
            except Exception:
                pass
            
        except Exception as e:
            print(f"⚠️  Ошибка: {e}")
        finally:
            self.is_converting = False

    def on_double_shift(self):
        """Handle double-Shift action (exposed for testing).

        Centralizes the logic executed when a double Shift is detected so
        it can be invoked and tested independently from low-level event
        handling.
        """
        # Delegate to InputHandler if available
        if getattr(self, 'input_handler', None):
            return self.input_handler.on_double_shift()
        # Diagnostic snapshot
        try:
            has_sel = self.has_selection()
        except Exception:
            has_sel = False
        if self.config.get('debug'):
            print(f"🔔 on_double_shift: backspace_hold={self.backspace_hold_detected}, chars_in_buffer={self.chars_in_buffer}, has_selection={has_sel}, auto_switch={self.config.get('auto_switch')}")

        if self.conversion_manager:
            mode = self.conversion_manager.choose_mode(self.buffer, lambda: has_sel, backspace_hold=self.backspace_hold_detected)
            if self.config.get('debug'):
                print(f"→ ConversionManager selected mode: {mode} (backspace_hold={self.backspace_hold_detected}, chars={self.buffer.chars_in_buffer}, has_selection={has_sel})")
            if mode == 'selection':
                # Attempt to ensure a selection exists, but do not treat selection
                # navigation failure as fatal — proceed to convert_selection()
                # which may still find an existing selection.
                import lswitch as _pkg
                adapter = getattr(_pkg, 'x11_adapter', None)

                # Try to expand/select last word only if we don't already have a fresh selection
                try:
                    if not has_sel:
                        if adapter:
                            try:
                                adapter.ctrl_shift_left()
                            except Exception:
                                if self.config.get('debug'):
                                    print("⚠️ adapter.ctrl_shift_left failed (non-fatal)")
                        else:
                            try:
                                get_system().xdotool_key('ctrl+shift+Left', timeout=0.3, stderr=subprocess.DEVNULL)
                            except Exception:
                                if self.config.get('debug'):
                                    print("⚠️ system xdotool ctrl+shift+Left failed (non-fatal)")
                        # small delay for selection to settle
                        time.sleep(0.03)

                    # Now try to convert the selection; if it fails, fallback to retype
                    try:
                        if self.config.get('debug'):
                            print(f"{time.time():.6f} ▸ calling convert_selection(prefer_trim_leading={(not has_sel)}, user_has_selection={has_sel}) (has_sel={has_sel})", flush=True)
                        # If we expanded selection because there was no prior
                        # fresh selection, request trimming of any leading
                        # whitespace the adapter may have captured.
                        try:
                            self.convert_selection(prefer_trim_leading=(not has_sel), user_has_selection=has_sel)
                        except TypeError:
                            # Backwards compatibility for tests/monkeypatched methods
                            self.convert_selection()
                        self.backspace_hold_detected = False
                    except Exception as e:
                        if self.config.get('debug'):
                            print(f"⚠️ Selection conversion failed — falling back to retype: {e}")
                            import traceback
                            traceback.print_exc()
                        self.convert_and_retype()
                except Exception as e:
                    if self.config.get('debug'):
                        print(f"⚠️ Unexpected error during selection handling: {e}")
                    self.convert_and_retype()
            else:
                self.convert_and_retype()
        else:
            # Legacy behavior
            if self.backspace_hold_detected or self.chars_in_buffer == 0:
                reason = "удержание Backspace" if self.backspace_hold_detected else "пустой буфер"
                if self.config.get('debug'):
                    print(f"→ Выделение + конвертация ({reason})")
                try:
                    system.xdotool_key('ctrl+shift+Left', timeout=0.3, stderr=subprocess.DEVNULL)
                    time.sleep(0.03)
                    self.convert_selection()
                except Exception:
                    pass
                self.backspace_hold_detected = False
            elif self.has_selection():
                if self.config.get('debug'):
                    print("→ Конвертирую выделенный текст")
                self.convert_selection()
            else:
                if self.config.get('debug'):
                    print("→ Конвертирую последнее слово")
                self.convert_and_retype()

        # Reset marker
        self.last_shift_press = 0
    
    def handle_event(self, event):
        # Delegate to InputHandler if present (preferred path). If the handler
        # returns a non-None value it handled the event; otherwise continue
        # with legacy handling so features/tests that expect LSwitch to process
        # repeats/backspace still work.
        if getattr(self, 'input_handler', None):
            _res = self.input_handler.handle_event(event)
            if _res is not None:
                return _res
        """Обработка событий клавиатуры"""
        # For debugging: only log blocked space events when debug is enabled
        if event.type == ecodes.EV_KEY and event.code == ecodes.KEY_SPACE:
            if self.is_converting and self.config.get('debug'):
                print(f"🔍 ПРОБЕЛ ЗАБЛОКИРОВАН is_converting=True!")

        
        if self.is_converting:
            return
        
        # Обрабатываем только нажатия и отпускания клавиш
        if event.type != ecodes.EV_KEY:
            return
        
        current_time = time.time()
        
        # Навигационные клавиши - очищают буфер (новый контекст ввода)
        if event.code in self.navigation_keys and event.value == 0:
            if self.chars_in_buffer > 0:
                self.clear_buffer()
                if self.config.get('debug'):
                    print("Буфер очищен (навигация)")
            return
        
        # Shift: проверяем двойное нажатие
        if event.code in (ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT):
            # КРИТИЧНО: добавляем события Shift в буфер для правильного воспроизведения
            self.event_buffer.append(event)
            
            if event.value == 1:  # Нажатие
                if self.config.get('debug'):
                    print(f"🔑 Shift нажат! last_press={self.last_shift_press:.3f} current={current_time:.3f} delta={current_time - self.last_shift_press:.3f}", flush=True)
                pass  # Просто добавляем в буфер, отслеживание не нужно
            elif event.value == 0:  # Отпускание
                # If suppression is active, ignore shift releases to avoid retriggering
                if getattr(self, 'suppress_shift_detection', False):
                    if self.config.get('debug'):
                        print("🔕 Подавление детекции Shift (реплей/конвертация)")
                    self.last_shift_press = 0
                    return

                # Also ignore releases briefly after replay to account for delivery jitter
                if getattr(self, '_post_replay_suppress_until', 0) and current_time < self._post_replay_suppress_until:
                    if self.config.get('debug'):
                        print("🔕 Игнорирование релиза Shift (пост-реплей окно)")
                    self.last_shift_press = 0
                    return

                if current_time - self.last_shift_press < self.double_click_timeout:
                    if self.config.get('debug'):
                        print("✓ Двойной Shift обнаружен!")
                        print(f"🔔 Delegating double-shift to on_double_shift (backspace_hold={self.backspace_hold_detected}, chars={self.chars_in_buffer})")
                    try:
                        self.on_double_shift()
                    except Exception as e:
                        print(f"⚠️ Ошибка в on_double_shift: {e}")
                    return
                else:
                    self.last_shift_press = current_time
            return
        
        # ESC - выход
        if event.code == ecodes.KEY_ESC and event.value == 0:
            print("Выход...")
            # Сохраняем словарь перед выходом
            if self.user_dict:
                self.user_dict.flush()
            return False
        
        # Enter - сбрасываем буфер полностью (конец ввода)
        if event.code == ecodes.KEY_ENTER and event.value == 0:
            self.clear_buffer()
            self.last_was_space = False
            self.update_selection_snapshot()
            
            if self.config.get('debug'):
                print("Буфер очищен (enter)")
            return
        
        # Активные клавиши - добавляем в буфер
        if event.code in self.active_keycodes:
            # DEBUG: отслеживаем ВСЕ события пробела
            if event.code == ecodes.KEY_SPACE and self.config.get('debug'):
                print(f"🔍 ПРОБЕЛ ВХОД! value={event.value}, last_manual={self.last_manual_convert is not None}")
            
            # Если последний был пробел и это НЕ пробел - сбрасываем старое слово
            if self.last_was_space and event.code != ecodes.KEY_SPACE:
                # Просто очищаем буфер, начинаем новое слово БЕЗ пробела
                self.clear_buffer()
                # Обновляем снимок выделения - пользователь начал печатать новое слово
                self.update_selection_snapshot()
                # Сбрасываем флаг
                self.last_was_space = False
                
                if self.config.get('debug'):
                    print("Сброс буфера после пробела, начало нового слова")
            
            # КРИТИЧНО: При первом символе в буфере - обновляем снимок выделения
            # Это значит пользователь начал печатать (а не конвертировать выделенное)
            if len(self.event_buffer) == 0 and event.value == 1:  # Press первого символа
                self.update_selection_snapshot()
                if self.config.get('debug'):
                    print("Первый символ - снимок выделения обновлён")
            
            self.event_buffer.append(event)
            
            # Считаем символы (только при отпускании клавиши)
            if event.value == 0:  # Отпускание
                if event.code == ecodes.KEY_BACKSPACE:
                    # Простая логика: уменьшаем счетчик
                    self.had_backspace = True
                    
                    # Сбрасываем счетчик repeats
                    self.consecutive_backspace_repeats = 0
                    
                    # Сбрасываем отслеживание конвертаций
                    if self.last_auto_convert:
                        self.last_auto_convert = None
                    if self.last_manual_convert:
                        self.last_manual_convert = None
                    
                    # Уменьшаем счетчики
                    if self.chars_in_buffer > 0:
                        self.chars_in_buffer -= 1
                        if self.text_buffer:
                            self.text_buffer.pop()
                            
            elif event.value == 2:  # Repeat (удержание)
                if event.code == ecodes.KEY_BACKSPACE:
                    # ПРОСТОЙ детектор: 3+ повтора = удержание
                    print('DEBUG: repeat branch entered, before=', self.consecutive_backspace_repeats)
                    self.consecutive_backspace_repeats += 1
                    print('DEBUG: repeat branch after=', self.consecutive_backspace_repeats)
                    
                    if self.consecutive_backspace_repeats >= 3:
                        if not self.backspace_hold_detected:
                            self.backspace_hold_detected = True
                            if self.config.get('debug'):
                                print(f"⚠️ Удержание Backspace обнаружено")
                    
                    # НЕ трогаем счетчики - они не точные при repeats!
                    # Будем использовать выделение слова при конвертации
                else:
                    self.consecutive_backspace_repeats = 0
                    
            # Обработка обычных клавиш
            if event.value == 0 and event.code not in (ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT, ecodes.KEY_BACKSPACE):
                # Обрабатываем обычные клавиши
                self.chars_in_buffer += 1
                
                if self.config.get('debug'):
                    print(f"🔍 DEBUG обычная клавиша: last_manual_convert={self.last_manual_convert is not None}")
                
                # Сбрасываем отслеживание автоконвертации при любом новом символе
                # (пользователь продолжает печатать = автоконвертация была правильной)
                if self.last_auto_convert:
                    self.last_auto_convert = None
                
                # Сохраняем успешную ручную конвертацию в словарь
                # Если пользователь продолжает печатать после ручной конвертации - она была правильной!
                if self.user_dict and self.last_manual_convert:
                    time_since_convert = time.time() - self.last_manual_convert['time']
                    if time_since_convert < 5.0:  # В течение 5 секунд
                        original = self.last_manual_convert['original']
                        converted = self.last_manual_convert['converted']
                        from_lang = self.last_manual_convert['from_lang']
                        to_lang = self.last_manual_convert['to_lang']
                        
                        # Добавляем как успешную конвертацию с направлением
                        if self.config.get('debug'):
                            print(f"🔧 Вызов add_conversion (буква): original='{original}', from={from_lang}, to={to_lang}")
                        self.user_dict.add_conversion(original, from_lang, to_lang, debug=self.config.get('debug'))
                        
                        if self.config.get('debug'):
                            # Проверяем вес
                            weight = self.user_dict.get_conversion_weight(original, from_lang, to_lang)
                            auto_status = " → автоконвертация!" if weight >= 5 else ""
                            print(f"📚 Успешная конвертация сохранена: '{original}' ({from_lang}→{to_lang}), вес: {weight}{auto_status}")
                    
                    # Не обнуляем для пробела - он обработает сам
                    if event.code != ecodes.KEY_SPACE:
                        self.last_manual_convert = None
                
                # Добавляем символ в text_buffer (всегда lowercase - для словаря)
                # RAW события с Shift остаются в event_buffer для правильного replay
                layout = self.get_current_layout()
                char = self.keycode_to_char(event.code, layout, shift=False)
                if char:
                    self.text_buffer.append(char)
                    
                # Запоминаем если это был пробел
                if event.code == ecodes.KEY_SPACE:
                    if self.config.get('debug'):
                        print(f"🔍 ПРОБЕЛ! value={event.value}, last_manual={self.last_manual_convert is not None}")
                    
                    # При отпускании пробела - сохраняем успешную конвертацию
                    if event.value == 0:
                        if self.config.get('debug'):
                            print(f"🔍 DEBUG пробел: last_manual_convert={self.last_manual_convert is not None}")
                            if self.last_manual_convert:
                                time_since = time.time() - self.last_manual_convert['time']
                                print(f"🔍 DEBUG: time_since_convert={time_since:.2f}s, original='{self.last_manual_convert['original']}'")
                        
                        if self.user_dict and self.last_manual_convert:
                            time_since_convert = time.time() - self.last_manual_convert['time']
                            if time_since_convert < 5.0:
                                original = self.last_manual_convert['original']
                                from_lang = self.last_manual_convert['from_lang']
                                to_lang = self.last_manual_convert['to_lang']
                                
                                if self.config.get('debug'):
                                    print(f"🔧 Вызов add_conversion (пробел): original='{original}', from={from_lang}, to={to_lang}")
                                self.user_dict.add_conversion(original, from_lang, to_lang, debug=self.config.get('debug'))
                                
                                if self.config.get('debug'):
                                    weight = self.user_dict.get_conversion_weight(original, from_lang, to_lang)
                                    auto_status = " → автоконвертация!" if abs(weight) >= 5 else ""
                                    print(f"📚 Успешная конвертация сохранена (пробел): '{original}' ({from_lang}→{to_lang}), вес: {weight}{auto_status}")
                    
                    self.last_was_space = True
                    # При пробеле показываем буфер и проверяем автопереключение (при отпускании)
                    if event.value == 0:  # При отпускании клавиши
                        if self.config.get('debug'):
                            if len(self.text_buffer) > 0:
                                print(f"Буфер: {self.chars_in_buffer} символов, текст: '{''.join(self.text_buffer)}'")
                        self.check_and_auto_convert()

        
        # Любая другая клавиша очищает буфер
        else:
            if event.value == 0:  # Только при отпускании
                self.clear_buffer()
                if self.config.get('debug'):
                    print("Буфер очищен")
    
    def run(self):
        """Запуск основного цикла с evdev"""
        print("🚀 LSwitch запущен (evdev режим)!")
        print("💡 Нажмите Shift дважды для конвертации последнего слова")
        print(f"💡 Таймаут двойного нажатия: {self.double_click_timeout}s")
        print("💡 Нажмите ESC для выхода")
        print("-" * 50)
        
        # Создаём селектор для мониторинга всех устройств ввода
        device_selector = selectors.DefaultSelector()
        
        # Регистрируем все устройства ввода, кроме нашей виртуальной клавиатуры
        devices = []
        for path in evdev.list_devices():
            try:
                device = evdev.InputDevice(path)
                # КРИТИЧНО: пропускаем нашу виртуальную клавиатуру!
                if device.name == self.fake_kb_name:
                    continue
                
                # Проверяем что это клавиатура или мышь (имеет KEY события)
                caps = device.capabilities()
                if ecodes.EV_KEY not in caps:
                    continue
                
                keys = caps.get(ecodes.EV_KEY, [])
                if not keys:
                    continue
                
                # Проверяем что это клавиатура (есть KEY_A) ИЛИ мышь (есть BTN_LEFT)
                is_keyboard = ecodes.KEY_A in keys
                is_mouse = ecodes.BTN_LEFT in keys or ecodes.BTN_RIGHT in keys
                
                if not (is_keyboard or is_mouse):
                    continue
                
                device_selector.register(device, selectors.EVENT_READ)
                devices.append(device)
                if self.config.get('debug'):
                    device_type = "клавиатура" if is_keyboard else "мышь"
                    print(f"   Подключено: {device.name} ({device_type})")
            except (OSError, PermissionError) as e:
                # Пропускаем устройства к которым нет доступа
                if self.config.get('debug'):
                    print(f"   Пропущено {path}: {e}")
        
        if not devices:
            print("❌ Не найдено устройств ввода")
            return
        
        print(f"✓ Мониторинг {len(devices)} устройств")
        print("-" * 50)
        
        # КРИТИЧНО: очищаем буфер и обновляем снимок выделения при старте
        self.clear_buffer()
        self.update_selection_snapshot()
        
        # Основной цикл обработки событий
        try:
            if False:  # Debug logging disabled
                print(f"🔄 Начало основного цикла обработки событий", flush=True)
            
            while True:
                # Проверяем изменение файла конфигурации раз в секунду
                current_time = time.time()
                if current_time - self.last_config_check >= 1.0:
                    self.last_config_check = current_time
                    config_path = self.config.get('_config_path') or self.config.get('_user_config_path')
                    if config_path is None:
                        config_path = '/etc/lswitch/config.json'
                    try:
                        if isinstance(config_path, str):
                            current_mtime = os.path.getmtime(config_path)
                            if current_mtime != self.config_mtime:
                                self.config_mtime = current_mtime
                                print(f"📝 Обнаружено изменение {config_path}", flush=True)
                                self.reload_config()
                    except (OSError, TypeError):
                        pass  # Файл не существует или недоступен
                
                # Проверяем флаг перезагрузки конфигурации (для SIGHUP)
                if self.config_reload_requested:
                    self.reload_config()
                
                for key, mask in device_selector.select(timeout=0.1):
                    device = key.fileobj
                    event_count = 0
                    try:
                        events = list(device.read())
                    except (OSError, IOError) as e:
                        # Device disconnected
                        if self.config.get('debug'):
                            print(f"⚠️ Не могу прочитать события с {device.name}: {e}", flush=True)
                        continue
                    
                    for event in events:
                        event_count += 1
                        # Don't print every event - too noisy. Only print important ones in debug mode
                        # if self.config.get('debug'):
                        #     print(f"📍 [{device.name}] Event #{event_count}: type={event.type}({ecodes.EV_KEY if event.type==1 else event.type}) code={event.code} value={event.value}", flush=True)
                        
                        # Log space events only when debug is enabled and relevant (avoid noisy logs)
                        if event.code == ecodes.KEY_SPACE and self.config.get('debug'):
                            # Only print when there's content in buffer or a conversion in progress
                            if self.is_converting or self.chars_in_buffer > 0:
                                print(f"🔍 ПРОБЕЛ В ЦИКЛЕ: value={event.value}, device={device.name}")

                        # Клик мыши очищает буфер (новый контекст)
                        if event.type == ecodes.EV_KEY and event.code in (
                            ecodes.BTN_LEFT, ecodes.BTN_RIGHT, ecodes.BTN_MIDDLE
                        ) and event.value == 1:
                            if self.chars_in_buffer > 0:
                                self.clear_buffer()
                                if self.config.get('debug'):
                                    print("Буфер очищен (клик мыши)")
                        
                        # Сохраняем ссылку на устройство для проверки модификаторов
                        self.current_device = device
                        
                        if self.handle_event(event) is False:
                            return
        except KeyboardInterrupt:
            print("\nВыход по Ctrl+C...")
        finally:
            # Закрываем виртуальную клавиатуру и убираем из реестра
            try:
                if self in LS_INSTANCES:
                    LS_INSTANCES.remove(self)
            except Exception:
                pass
            try:
                self.fake_kb.close()
            except Exception:
                pass


# validate_config is provided by lswitch.config for reusability
from lswitch.config import validate_config  # re-export for backward compatibility
# Also expose load_config at module-level for convenience (back-compat)
from lswitch.config import load_config as _module_load_config


