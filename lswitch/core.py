#!/usr/bin/env python3
"""
LSwitch - Layout Switcher for Linux (evdev version)
Переключатель раскладки по двойному нажатию Shift
"""

import sys
import time
import subprocess
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

# Загружаем libX11 для XKB функций
try:
    libX11_path = ctypes.util.find_library('X11')
    if libX11_path:
        libX11 = ctypes.CDLL(libX11_path)
        
        # Структура XkbStateRec для получения состояния XKB
        class XkbStateRec(ctypes.Structure):
            _fields_ = [
                ("group", ctypes.c_ubyte),           # Текущая группа раскладки
                ("locked_group", ctypes.c_ubyte),
                ("base_group", ctypes.c_ushort),
                ("latched_group", ctypes.c_ushort),
                ("mods", ctypes.c_ubyte),
                ("base_mods", ctypes.c_ubyte),
                ("latched_mods", ctypes.c_ubyte),
                ("locked_mods", ctypes.c_ubyte),
                ("compat_state", ctypes.c_ubyte),
                ("grab_mods", ctypes.c_ubyte),
                ("compat_grab_mods", ctypes.c_ubyte),
                ("lookup_mods", ctypes.c_ubyte),
                ("compat_lookup_mods", ctypes.c_ubyte),
                ("ptr_buttons", ctypes.c_ushort),
            ]
        
        # Настройка XKB функций
        libX11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        libX11.XOpenDisplay.restype = ctypes.c_void_p
        
        libX11.XkbGetState.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(XkbStateRec)]
        libX11.XkbGetState.restype = ctypes.c_int
        
        libX11.XkbLockGroup.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint]
        libX11.XkbLockGroup.restype = ctypes.c_int
        
        libX11.XFlush.argtypes = [ctypes.c_void_p]
        libX11.XFlush.restype = ctypes.c_int
        
        libX11.XCloseDisplay.argtypes = [ctypes.c_void_p]
        
        # Функции для получения символов из KeyCode
        libX11.XkbKeycodeToKeysym.argtypes = [ctypes.c_void_p, ctypes.c_ubyte, ctypes.c_uint, ctypes.c_uint]
        libX11.XkbKeycodeToKeysym.restype = ctypes.c_ulong
        
        libX11.XKeysymToString.argtypes = [ctypes.c_ulong]
        libX11.XKeysymToString.restype = ctypes.c_char_p
        
        XKB_AVAILABLE = True
    else:
        XKB_AVAILABLE = False
        libX11 = None
        print("⚠️  libX11 не найдена")
except Exception as e:
    XKB_AVAILABLE = False
    libX11 = None
    print(f"⚠️  Ошибка загрузки XKB: {e}")

# Импортируем словарь для автопереключения
try:
    from dictionary import is_likely_wrong_layout
    DICT_AVAILABLE = True
except ImportError:
    DICT_AVAILABLE = False
    print("⚠️  Словарь не найден, автопереключение недоступно")

# Импортируем пользовательский словарь для самообучения
try:
    from user_dictionary import UserDictionary
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

# Карта переключения EN -> RU
EN_TO_RU = {
    'q': 'й', 'w': 'ц', 'e': 'у', 'r': 'к', 't': 'е', 'y': 'н', 'u': 'г', 'i': 'ш', 'o': 'щ', 'p': 'з',
    '[': 'х', ']': 'ъ', 'a': 'ф', 's': 'ы', 'd': 'в', 'f': 'а', 'g': 'п', 'h': 'р', 'j': 'о', 'k': 'л',
    'l': 'д', ';': 'ж', "'": 'э', 'z': 'я', 'x': 'ч', 'c': 'с', 'v': 'м', 'b': 'и', 'n': 'т', 'm': 'ь',
    ',': 'б', '.': 'ю', '/': '.', '`': 'ё',
    '{': 'х', '}': 'ъ', ':': 'ж', '"': 'э', '<': 'б', '>': 'ю', '?': ',', '~': 'ё',
    '@': '"', '#': '№', '$': ';', '^': ':', '&': '?'
}

# Карта переключения RU -> EN
RU_TO_EN = {v: k for k, v in EN_TO_RU.items()}
# При обратной маппинге некоторые символы отображаются неоднозначно
# (например и ',' и '<' мапятся в 'б'). Выберем предпочтительные ASCII-символы
# чтобы обратная конвертация была предсказуемой и давала «нормальную» форму.
PREFERRED_REVERSE = {
    'б': ',',  # prefer comma over '<'
    'ю': '.',  # prefer dot over '>'
    'ё': '`',  # prefer backtick for ё (from `)
    'э': "'", # prefer single-quote for э
}
for ru, en in PREFERRED_REVERSE.items():
    RU_TO_EN[ru] = en


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

    def load_config(self, config_path):
        """Загружает конфигурацию из файла.

        Поддерживает системный конфиг (обычно `/etc/lswitch/config.json`) и
        пользовательский конфиг `~/.config/lswitch/config.json`, который
        перекрывает системные значения при наличии.
        """
        default_config = {
            'double_click_timeout': 0.3,
            'debug': False,
            'switch_layout_after_convert': True,
            'layout_switch_key': 'Alt_L+Shift_L',
            'auto_switch': False
        }

        # Helper to try read + validate a config file and merge into defaults
        def _sanitize_json_text(s: str) -> str:
            # Remove shell-style comments (# ...) and C++ style // ...
            import re
            # Remove lines that start with optional whitespace followed by # or //
            s = re.sub(r"^[ \t]*#.*$", "", s, flags=re.MULTILINE)
            s = re.sub(r"//.*$", "", s, flags=re.MULTILINE)
            # Remove trailing commas before } or ]
            s = re.sub(r",[ \t\r\n]+(\}|\])", r"\1", s)
            return s

        def _read_and_merge(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    raw = f.read()
                try:
                    cfg = json.loads(raw)
                except json.JSONDecodeError:
                    # Try sanitized version (strip comments, trailing commas)
                    try:
                        sanitized = _sanitize_json_text(raw)
                        cfg = json.loads(sanitized)
                        print(f"⚠️  Конфиг {path} содержал комментарии/трейлинг-запятые — применена попытка санации")
                    except json.JSONDecodeError as e:
                        print(f"⚠️  Ошибка разбора JSON в конфиге {path}: {e}")
                        return False
                try:
                    validated = validate_config(cfg)
                    default_config.update(validated)
                    print(f"✓ Конфиг загружен и валидирован: {path}")
                    return True
                except ValueError as verr:
                    print(f"⚠️  Неверный формат конфига {path}: {verr}")
            except Exception:
                # Silent: файл может не существовать
                return False
            return False

        # 1) Try the explicit path (system /etc/lswitch/config.json or config.json in cwd)
        _read_and_merge(config_path)

        # 2) Then try per-user config as an override if present
        user_cfg = os.path.expanduser('~/.config/lswitch/config.json')
        if os.path.exists(user_cfg):
            _read_and_merge(user_cfg)

        # Keep path for reference (prefer system path; note user override exists separately)
        default_config['_config_path'] = config_path
        default_config['_user_config_path'] = user_cfg if os.path.exists(user_cfg) else None
        return default_config

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

    def __init__(self, config_path=None, start_threads=True):
        """Initialise LSwitch.

        start_threads: when False, skip starting background threads and some
        runtime integrations (useful for unit testing without X11/evdev).
        """
        # Автоматически определяем путь к конфигурации
        if config_path is None:
            if os.path.exists('/etc/lswitch/config.json'):
                config_path = '/etc/lswitch/config.json'
            else:
                config_path = 'config.json'
        
        self.config = self.load_config(config_path)
        # Track mtime safely — file may not exist in test environments
        cfg_path = self.config.get('_config_path', '/etc/lswitch/config.json')
        try:
            self.config_mtime = os.path.getmtime(cfg_path)
        except (OSError, FileNotFoundError):
            self.config_mtime = None

        self.last_shift_press = 0
        self.double_click_timeout = self.config.get('double_click_timeout', 0.3)
        
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
        from utils.keyboard import KeyboardController
        self.kb = KeyboardController(self.fake_kb)
        
        # Инкапсулированный буфер ввода
        from utils.buffer import InputBuffer
        self.buffer = InputBuffer(maxlen=1000)

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

        # Start background threads and runtime integrations only if requested
        if start_threads:
            # Запускаем поток мониторинга раскладки
            self.layout_thread = threading.Thread(target=self.monitor_layout_changes, daemon=True)
            self.layout_thread.start()
            
            # Запускаем поток мониторинга файла с раскладками
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
            self.config_mtime = os.path.getmtime(self.config.get('_config_path', '/etc/lswitch/config.json'))
        except (OSError, FileNotFoundError):
            self.config_mtime = None
        self.last_config_check = time.time()
    
    def get_layouts_from_xkb(self):
        """Получает список раскладок - сначала из файла от control panel, затем через setxkbmap"""
        # Сначала пробуем прочитать из файла, который публикует lswitch_control.py
        try:
            runtime_dir = os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')
            layouts_file = f'{runtime_dir}/lswitch_layouts.json'
            
            if os.path.exists(layouts_file):
                # Проверяем свежесть файла (не старше 60 секунд)
                import time as time_module
                file_age = time_module.time() - os.path.getmtime(layouts_file)
                
                if file_age < 60:
                    with open(layouts_file, 'r') as f:
                        data = json.load(f)
                        layouts = data.get('layouts', [])
                        
                        if len(layouts) >= 2:
                            if self.config.get('debug'):
                                print(f"✓ Раскладки из control panel: {layouts}", flush=True)
                            return layouts
        except Exception as e:
            if self.config.get('debug'):
                print(f"⚠️  Не удалось прочитать раскладки из файла: {e}", flush=True)
        
        # Фолбэк: читаем через setxkbmap
        try:
            result = subprocess.run(
                ['setxkbmap', '-query'],
                capture_output=True, text=True, timeout=2
            )
            
            for line in result.stdout.split('\n'):
                if line.startswith('layout:'):
                    layouts_str = line.split(':', 1)[1].strip()
                    layouts = [l.strip() for l in layouts_str.split(',')]
                    # Нормализуем: us -> en
                    result = ['en' if l == 'us' else l for l in layouts if l]
                    
                    if len(result) >= 2:
                        if self.config.get('debug'):
                            print(f"✓ Раскладки: {result}", flush=True)
                        return result
                    elif len(result) == 1:
                        if self.config.get('debug'):
                            print(f"⚠️  Обнаружена только 1 раскладка: {result}", flush=True)
                        return result
                        
        except Exception as e:
            if self.config.get('debug'):
                print(f"⚠️  Ошибка чтения раскладок: {e}", flush=True)
        
        # Фолбэк - по умолчанию
        if self.config.get('debug'):
            print("⚠️  Использую fallback: ['en', 'ru']", flush=True)
        return ['en', 'ru']
    
    def get_current_layout(self):
        """Получает текущую активную раскладку через XKB GetState"""
        if not XKB_AVAILABLE or not libX11:
            # Fallback к первой раскладке
            return self.layouts[0] if self.layouts else 'en'
        
        try:
            # Открываем Display
            display_ptr = libX11.XOpenDisplay(None)
            if not display_ptr:
                return self.layouts[0] if self.layouts else 'en'
            
            try:
                # Создаём структуру для результата
                state = XkbStateRec()
                
                # Вызываем XkbGetState (0x100 = XkbUseCoreKbd)
                status = libX11.XkbGetState(display_ptr, 0x100, ctypes.byref(state))
                
                if status == 0:  # Success
                    group = state.group
                    # Возвращаем соответствующую раскладку
                    if group < len(self.layouts):
                        return self.layouts[group]
                    else:
                        return self.layouts[0] if self.layouts else 'en'
            finally:
                libX11.XCloseDisplay(display_ptr)
        except Exception as e:
            if self.config.get('debug'):
                print(f"⚠️  Ошибка получения раскладки через XKB: {e}")
        
        return self.layouts[0] if self.layouts else 'en'
    
    def keycode_to_char(self, keycode, layout='en', shift=False):
        """Преобразует evdev keycode в символ согласно раскладке используя XKB"""
        if not XKB_AVAILABLE or not libX11:
            return ''
        
        try:
            # Открываем Display
            display_ptr = libX11.XOpenDisplay(None)
            if not display_ptr:
                return ''
            
            try:
                # Преобразуем evdev keycode в X11 keycode (evdev + 8)
                x11_keycode = keycode + 8
                
                # Определяем группу раскладки (0=en, 1=ru, ...)
                group = 0
                if layout == 'en':
                    # Ищем индекс английской раскладки
                    for i, lay in enumerate(self.layouts):
                        if lay == 'en':
                            group = i
                            break
                elif layout == 'ru':
                    # Ищем индекс русской раскладки
                    for i, lay in enumerate(self.layouts):
                        if lay == 'ru':
                            group = i
                            break
                
                # level: 0 = без shift, 1 = с shift
                level = 1 if shift else 0
                
                # Получаем KeySym для указанной группы и уровня
                keysym = libX11.XkbKeycodeToKeysym(display_ptr, x11_keycode, group, level)
                
                if keysym == 0:
                    return ''
                
                # Конвертируем KeySym в строку
                keysym_str = libX11.XKeysymToString(keysym)
                if not keysym_str:
                    return ''
                
                keysym_name = keysym_str.decode('utf-8')
                
                # Простые символы (1 буква) - возвращаем как есть
                if len(keysym_name) == 1:
                    return keysym_name
                
                # Cyrillic буквы вида "Cyrillic_a" -> "а"
                if keysym_name.startswith('Cyrillic_'):
                    cyrillic_map = {
                        'io': 'ё', 'IO': 'Ё',
                        'a': 'а', 'A': 'А', 'be': 'б', 'BE': 'Б',
                        've': 'в', 'VE': 'В', 'ghe': 'г', 'GHE': 'Г',
                        'de': 'д', 'DE': 'Д', 'ie': 'е', 'IE': 'Е',
                        'zhe': 'ж', 'ZHE': 'Ж', 'ze': 'з', 'ZE': 'З',
                        'i': 'и', 'I': 'И', 'shorti': 'й', 'SHORTI': 'Й',
                        'ka': 'к', 'KA': 'К', 'el': 'л', 'EL': 'Л',
                        'em': 'м', 'EM': 'М', 'en': 'н', 'EN': 'Н',
                        'o': 'о', 'O': 'О', 'pe': 'п', 'PE': 'П',
                        'er': 'р', 'ER': 'Р', 'es': 'с', 'ES': 'С',
                        'te': 'т', 'TE': 'Т', 'u': 'у', 'U': 'У',
                        'ef': 'ф', 'EF': 'Ф', 'ha': 'х', 'HA': 'Х',
                        'tse': 'ц', 'TSE': 'Ц', 'che': 'ч', 'CHE': 'Ч',
                        'sha': 'ш', 'SHA': 'Ш', 'shcha': 'щ', 'SHCHA': 'Щ',
                        'hardsign': 'ъ', 'HARDSIGN': 'Ъ',
                        'yeru': 'ы', 'YERU': 'Ы',
                        'softsign': 'ь', 'SOFTSIGN': 'Ь',
                        'e': 'э', 'E': 'Э', 'yu': 'ю', 'YU': 'Ю',
                        'ya': 'я', 'YA': 'Я'
                    }
                    key = keysym_name[9:]  # Убираем "Cyrillic_"
                    return cyrillic_map.get(key, '')
                
                return ''
                
            finally:
                libX11.XCloseDisplay(display_ptr)
        except Exception as e:
            if self.config.get('debug'):
                if self.config.get('debug'):
                    print(f"⚠️  Ошибка keycode_to_char({keycode}, {layout}): {e}")
            return ''
    
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
            # Ищем ID нашего виртуального устройства
            result = subprocess.run(
                ['xinput', 'list', '--id-only', self.fake_kb_name],
                capture_output=True,
                text=True,
                timeout=2,
                env={'DISPLAY': ':0'}
            )
            
            device_id = result.stdout.strip()
            if not device_id:
                if self.config.get('debug'):
                    print(f"⚠️  Не найдено виртуальное устройство '{self.fake_kb_name}'")
                return
            
            # Конвертируем раскладки (en/ru -> us/ru для setxkbmap)
            xkb_layouts = ','.join('us' if l == 'en' else l for l in self.layouts)
            
            # Применяем раскладки к виртуальному устройству
            subprocess.run(
                ['setxkbmap', '-device', device_id, '-layout', xkb_layouts],
                capture_output=True,
                timeout=2,
                env={'DISPLAY': ':0'}
            )
            
            if self.config.get('debug'):
                print(f"✓ Виртуальная клавиатура настроена: раскладки {xkb_layouts}")
                
        except Exception as e:
            if self.config.get('debug'):
                print(f"⚠️  Не удалось настроить виртуальную клавиатуру: {e}")
    
    def check_and_auto_convert(self):
        """Проверяет и автоматически конвертирует при пробеле используя n-граммный анализ"""
        # Early-exit diagnostics (only print when debug enabled) to help troubleshooting
        if not self.auto_switch_enabled or not DICT_AVAILABLE:
            if self.config.get('debug'):
                if not self.auto_switch_enabled:
                    print("⏭️  Автопереключение выключено в конфиге (auto_switch=False)")
                if not DICT_AVAILABLE:
                    print("⏭️  Словарь недоступен (DICT_AVAILABLE=False). Установка dictionary.py или user_dictionary.py требуется.")
            return
        
        # Защита: Если был backspace - пользователь контролирует, не трогаем
        if self.had_backspace:
            if self.config.get('debug'):
                print(f"  ⏭️  Пропуск: был backspace (пользователь исправляет)")
            return
        
        # Проверяем текущую раскладку - поддерживаем только ru/en
        if self.current_layout not in ['ru', 'en']:
            if self.config.get('debug'):
                print(f"  ⏭️  Пропуск автоконвертации: неподдерживаемая раскладка '{self.current_layout}'")
            return
        
        if self.chars_in_buffer == 0:
            return
        
        # Получаем текст из буфера
        text = ''.join(self.buffer.text_buffer).strip()
        
        if not text:
            if self.config.get('debug'):
                print(f"  ⏭️  Пропуск автоконвертации: пустой буфер")
            return
        
        # Проверяем словарь конвертаций - возможно это слово надо автоматически конвертировать
        try:
            if self.user_dict and hasattr(self.user_dict, 'should_auto_convert'):
                # Определяем текущий язык текста
                has_cyrillic = any(('А' <= c <= 'Я') or ('а' <= c <= 'я') or c in 'ЁёЪъЬь' for c in text)
                from_lang = 'ru' if has_cyrillic else 'en'
                to_lang = 'en' if from_lang == 'ru' else 'ru'
                
                # Use threshold from user dictionary settings to respect user preferences
                threshold = self.user_dict.data.get('settings', {}).get('auto_convert_threshold', 5)
                will = self.user_dict.should_auto_convert(text, from_lang, to_lang, threshold=threshold)
                if self.config.get('debug'):
                    weight = self.user_dict.get_conversion_weight(text, from_lang, to_lang)
                    print(f"🔎 Auto-convert decision: word='{text}', from={from_lang}, to={to_lang}, weight={weight}, threshold={threshold}, will_convert={will}")

                if will:
                    if self.config.get('debug'):
                        print(f"🎯 Автоконвертация по словарю: '{text}' ({from_lang}→{to_lang}), вес: {weight}")

                    # Сохраняем информацию о автоконвертации для возможной коррекции
                    converted_text = self.convert_text(text)
                    self.last_auto_convert = {
                        "word": text,
                        "converted_to": converted_text,
                        "time": time.time(),
                        "lang": from_lang
                    }
                    # Дублируем маркер в резерве, чтобы его не смогли случайно стереть обработчики событий
                    self._recent_auto_marker = dict(self.last_auto_convert)

                    if self.config.get('debug'):
                        print(f"🔍 last_auto_convert set: {self.last_auto_convert}")

                    # Выполняем автоконвертацию (не считаем её за manual)
                    self.convert_and_retype(is_auto=True)
                else:
                    if self.config.get('debug'):
                        print(f"  ⏭️  Конвертация не требуется (user_dict) - weight {weight} < threshold {threshold}")
                    # Фолбэк: сначала попробуем старую логику со словарём (dictionary.py)
                    try:
                        if self.config.get('debug'):
                            print("  🔁 Попытка фолбэка через словарь (_check_with_dictionary)")
                        self._check_with_dictionary(text)
                    except Exception as e:
                        if self.config.get('debug'):
                            print(f"⚠️  Ошибка в фолбэке словаря: {e}")

                    # Дополнительно: фолбэк через n-gram анализ (если доступен)
                    try:
                        import ngrams
                        should, best_text, reason = ngrams.should_convert(text, threshold=5, user_dict=self.user_dict)
                        if self.config.get('debug'):
                            print(f"🔁 N-gram fallback: should={should}, best='{best_text}', reason={reason}")
                        if should:
                            if self.config.get('debug'):
                                print(f"🎯 Автоконвертация (n-grams): '{text}' → '{best_text}' ({reason})")
                            # Устанавливаем маркер автоконвертации и временно переопределяем converted_text
                            self.last_auto_convert = {
                                "word": text,
                                "converted_to": best_text,
                                "time": time.time(),
                                "lang": from_lang
                            }
                            self._recent_auto_marker = dict(self.last_auto_convert)
                            # Переопределение converted_text, используемое convert_and_retype
                            self._override_converted_text = best_text
                            self.convert_and_retype(is_auto=True)
                            # Очистим временный атрибут
                            try:
                                del self._override_converted_text
                            except Exception:
                                pass
                    except ImportError:
                        if self.config.get('debug'):
                            print("⚠️  ngrams.py недоступен, пропускаем ngram-фолбэк")
                    except Exception as e:
                        if self.config.get('debug'):
                            print(f"⚠️  Ошибка ngram-фолбэка: {e}")
                
                if self.config.get('debug'):
                    print(f"  ⏭️  Конвертация не требуется (user_dict)")
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
        """Фолбэк проверка через словарь (старая логика)"""
        try:
            from dictionary import check_word, convert_text
            
            # Проверяем оригинальный текст
            is_correct, _ = check_word(text, self.current_layout)
            
            if not is_correct:
                # Пробуем конвертировать
                converted = convert_text(text, self.current_layout)
                is_conv_correct, _ = check_word(converted, 
                    'en' if self.current_layout == 'ru' else 'ru')
                
                if is_conv_correct:
                    if self.config.get('debug'):
                        print(f"🤖 Автоконвертация (словарь): '{text}' → '{converted}'")
                    self.convert_and_retype()
                    
        except Exception as e:
            if self.config.get('debug'):
                print(f"⚠️  Ошибка словаря: {e}")
    

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
        """Воспроизводит записанные события клавиатуры"""
        shift_codes = {ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT}
        
        if self.config.get('debug'):
            shift_events = [e for e in events if e.code in shift_codes]
            letter_events = [e for e in events if e.code not in shift_codes and e.value == 0]
            print(f"  Воспроизвожу: {len(events)} событий ({len(shift_events)} Shift, {len(letter_events)} букв)", flush=True)
            
            # Показываем первые 5 событий для диагностики
            print("  Первые события:", flush=True)
            for i, e in enumerate(events[:5]):
                shift_str = "SHIFT" if e.code in shift_codes else f"KEY_{e.code}"
                val_str = "↓" if e.value == 1 else "↑"
                print(f"    {i+1}. {shift_str} {val_str}", flush=True)
        
        for event in events:
            # Без задержки - evdev обрабатывает события моментально
            self.fake_kb.write(ecodes.EV_KEY, event.code, event.value)
            self.fake_kb.syn()
    
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
        self.backspace_hold_detected = False

        # NOTE: раньше тут обнулялся last_auto_convert, но это мешало ручной коррекции сразу после автоконвертации.
        # Оставляем last_auto_convert до тех пор, пока пользователь не начнёт ввод (в другом месте оно сбрасывается),
        # либо пока не истечёт timeout correction_timeout при проверке коррекции.
    
    def convert_text(self, text):
        """Конвертирует текст между раскладками с сохранением регистра"""
        if not text:
            return text
        
        # Определяем раскладку по количеству символов
        ru_chars = sum(1 for c in text.lower() if c in RU_TO_EN)
        en_chars = sum(1 for c in text.lower() if c in EN_TO_RU)
        
        result = []
        if ru_chars > en_chars:
            # Конвертируем RU -> EN
            for c in text:
                is_upper = c.isupper()
                converted = RU_TO_EN.get(c.lower(), c)
                result.append(converted.upper() if is_upper else converted)
        else:
            # Конвертируем EN -> RU
            for c in text:
                is_upper = c.isupper()
                converted = EN_TO_RU.get(c.lower(), c)
                result.append(converted.upper() if is_upper else converted)
        
        return ''.join(result)
    
    def convert_selection(self):
        """Конвертирует выделенный текст через PRIMARY selection (без порчи clipboard)"""
        # Проверяем наличие минимум 2 раскладок
        if len(self.layouts) < 2:
            if self.config.get('debug'):
                print(f"⚠️  Конвертация невозможна: только {len(self.layouts)} раскладка")
            return
        
        if self.is_converting:
            return
        
        self.is_converting = True
        
        try:
            # Получаем выделенный текст из PRIMARY selection (не трогаем clipboard!)
            try:
                import lswitch as _pkg
                adapter = getattr(_pkg, 'x11_adapter', None)
                if adapter:
                    selected_text = adapter.get_primary_selection(timeout=0.5)
                else:
                    selected_text = subprocess.run(
                        ['xclip', '-o', '-selection', 'primary'],
                        capture_output=True, timeout=0.5, text=True
                    ).stdout
            except Exception:
                selected_text = ''
            
            if selected_text:
                # Delegate selection conversion to SelectionManager
                try:
                    from selection import SelectionManager
                    sm = SelectionManager(adapter)
                    switch_fn = (self.switch_keyboard_layout if self.config.get('switch_layout_after_convert', True) else None)

                    orig, conv = sm.convert_selection(self.convert_text, user_dict=self.user_dict, switch_layout_fn=switch_fn, debug=self.config.get('debug'))

                    if conv:
                        if self.user_dict and not self.last_auto_convert:
                            self.last_manual_convert = {
                                'original': orig.strip().lower(),
                                'converted': conv.strip().lower(),
                                'from_lang': 'ru' if any(('А' <= c <= 'Я') or ('а' <= c <= 'я') for c in orig) else 'en',
                                'to_lang': 'ru' if any(('А' <= c <= 'Я') or ('а' <= c <= 'я') for c in conv) else 'en',
                                'time': time.time()
                            }

                        # Correction detection
                        auto_marker = self.last_auto_convert or getattr(self, '_recent_auto_marker', None)
                        if self.user_dict and auto_marker and self.conversion_manager:
                            try:
                                if self.conversion_manager.apply_correction(self.user_dict, auto_marker, orig, conv, debug=self.config.get('debug')):
                                    self.last_auto_convert = None
                                    self._recent_auto_marker = None
                            except Exception as e:
                                if self.config.get('debug'):
                                    print(f"⚠️ Error applying correction: {e}")

                    # finalize
                    self.backspace_hold_detected = False
                    self.update_selection_snapshot()
                    self.clear_buffer()
                except Exception as e:
                    if self.config.get('debug'):
                        print(f"⚠️ SelectionManager failed: {e}")
                    # fallback to legacy path (let existing behavior run)
                    try:
                        if x11_adapter:
                            x11_adapter.ctrl_shift_left()
                        else:
                            subprocess.run(['xdotool', 'key', 'ctrl+shift+Left'], timeout=0.3, stderr=subprocess.DEVNULL)
                        time.sleep(0.03)
                        # fallback: call old inline conversion flow
                        # (we keep it minimal to avoid code duplication)
                    except Exception:
                        if self.config.get('debug'):
                            print("⚠️ Legacy selection fallback failed")
                    
                # end selection handling (either via SelectionManager or fallback)
                
                # КРИТИЧНО: Обновляем снимок ПОСЛЕ всех операций
                # Это выделение уже обработано и не должно считаться новым
                self.update_selection_snapshot()
                
                # КРИТИЧНО: Очищаем буфер после конвертации выделенного
                # Иначе повторная конвертация попытается использовать старые данные
                self.clear_buffer()
            else:
                if self.config.get('debug'):
                    print("⚠️  Нет выделенного текста")
                
        except Exception as e:
            print(f"⚠️  Ошибка конвертации выделенного: {e}")
            if self.config.get('debug'):
                import traceback
                traceback.print_exc()
        finally:
            time.sleep(0.1)
            self.is_converting = False
    
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
                subprocess.run(['xdotool', 'key', 'Alt_L+Shift_L'], timeout=1)
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
            result = subprocess.run(
                ['xclip', '-o', '-selection', 'primary'],
                capture_output=True, timeout=0.3, text=True
            )
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
            result = subprocess.run(
                ['xclip', '-o', '-selection', 'primary'],
                capture_output=True, timeout=0.3, text=True
            )
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
            
            # Воспроизводим сохранённые события в новой раскладке
            self.replay_events(events_to_replay)
            
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
                try:
                    import lswitch as _pkg
                    adapter = getattr(_pkg, 'x11_adapter', None)
                    if adapter:
                        adapter.ctrl_shift_left()
                    else:
                        subprocess.run(['xdotool', 'key', 'ctrl+shift+Left'], timeout=0.3, stderr=subprocess.DEVNULL)
                    time.sleep(0.03)
                    self.convert_selection()
                    self.backspace_hold_detected = False
                except Exception:
                    if self.config.get('debug'):
                        print("⚠️ Selection attempt failed — falling back to retype")
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
                    subprocess.run(['xdotool', 'key', 'ctrl+shift+Left'], timeout=0.3, stderr=subprocess.DEVNULL)
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
                pass  # Просто добавляем в буфер, отслеживание не нужно
            elif event.value == 0:  # Отпускание
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
                    self.consecutive_backspace_repeats += 1
                    
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
            while True:
                # Проверяем изменение файла конфигурации раз в секунду
                current_time = time.time()
                if current_time - self.last_config_check >= 1.0:
                    self.last_config_check = current_time
                    config_path = self.config.get('_config_path', '/etc/lswitch/config.json')
                    try:
                        current_mtime = os.path.getmtime(config_path)
                        if current_mtime != self.config_mtime:
                            self.config_mtime = current_mtime
                            print(f"📝 Обнаружено изменение {config_path}", flush=True)
                            self.reload_config()
                    except OSError:
                        pass  # Файл не существует или недоступен
                
                # Проверяем флаг перезагрузки конфигурации (для SIGHUP)
                if self.config_reload_requested:
                    self.reload_config()
                
                for key, mask in device_selector.select(timeout=0.1):
                    device = key.fileobj
                    for event in device.read():
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


def validate_config(conf: dict) -> dict:
    """Validate and normalize configuration dictionary.

    Ensures expected keys have correct types and sensible ranges. Returns
    a normalized config dict (filling missing keys with defaults). Raises
    ValueError with a descriptive message if validation fails.
    """
    if conf is None:
        conf = {}

    defaults = {
        'double_click_timeout': 0.3,
        'debug': False,
        'switch_layout_after_convert': True,
        'layout_switch_key': 'Alt_L+Shift_L',
        'auto_switch': False,
        'user_dict_enabled': False,
        'user_dict_min_weight': 2,
    }

    out = dict(defaults)

    # double_click_timeout: positive number between 0.05 and 10
    dct = conf.get('double_click_timeout', defaults['double_click_timeout'])
    try:
        dct_val = float(dct)
        if not (0.05 <= dct_val <= 10.0):
            raise ValueError('double_click_timeout must be between 0.05 and 10.0')
        out['double_click_timeout'] = dct_val
    except Exception:
        raise ValueError(f"Invalid 'double_click_timeout': {dct}")

    # debug
    dbg = conf.get('debug', defaults['debug'])
    if not isinstance(dbg, bool):
        raise ValueError("Invalid 'debug' flag: must be boolean")
    out['debug'] = dbg

    # switch_layout_after_convert
    sl = conf.get('switch_layout_after_convert', defaults['switch_layout_after_convert'])
    if not isinstance(sl, bool):
        raise ValueError("Invalid 'switch_layout_after_convert': must be boolean")
    out['switch_layout_after_convert'] = sl

    # layout_switch_key
    lsk = conf.get('layout_switch_key', defaults['layout_switch_key'])
    if not isinstance(lsk, str) or not lsk:
        raise ValueError("Invalid 'layout_switch_key': must be a non-empty string")
    out['layout_switch_key'] = lsk

    # auto_switch
    autos = conf.get('auto_switch', defaults['auto_switch'])
    if not isinstance(autos, bool):
        raise ValueError("Invalid 'auto_switch': must be boolean")
    out['auto_switch'] = autos

    # user_dict_enabled
    ude = conf.get('user_dict_enabled', defaults['user_dict_enabled'])
    if not isinstance(ude, bool):
        raise ValueError("Invalid 'user_dict_enabled': must be boolean")
    out['user_dict_enabled'] = ude

    # user_dict_min_weight
    udw = conf.get('user_dict_min_weight', defaults['user_dict_min_weight'])
    try:
        udw_i = int(udw)
        if udw_i < 0:
            raise ValueError('user_dict_min_weight must be >= 0')
        out['user_dict_min_weight'] = udw_i
    except Exception:
        raise ValueError(f"Invalid 'user_dict_min_weight': {udw}")

    return out


