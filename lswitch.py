#!/usr/bin/env python3
"""
LSwitch - Layout Switcher for Linux (evdev version)
Переключатель раскладки по двойному нажатию Shift
"""

import time
import subprocess
import json
import os
import collections
import selectors
import getpass

try:
    import evdev
    from evdev import ecodes
except ImportError:
    print("❌ Ошибка: установите python3-evdev")
    print("   sudo apt install python3-evdev")
    exit(1)


# Карта переключения EN -> RU
EN_TO_RU = {
    'q': 'й', 'w': 'ц', 'e': 'у', 'r': 'к', 't': 'е', 'y': 'н', 'u': 'г', 'i': 'ш', 'o': 'щ', 'p': 'з',
    '[': 'х', ']': 'ъ', 'a': 'ф', 's': 'ы', 'd': 'в', 'f': 'а', 'g': 'п', 'h': 'р', 'j': 'о', 'k': 'л',
    'l': 'д', ';': 'ж', "'": 'э', 'z': 'я', 'x': 'ч', 'c': 'с', 'v': 'м', 'b': 'и', 'n': 'т', 'm': 'ь',
    '/': '/', '`': 'ё',
    'Q': 'Й', 'W': 'Ц', 'E': 'У', 'R': 'К', 'T': 'Е', 'Y': 'Н', 'U': 'Г', 'I': 'Ш', 'O': 'Щ', 'P': 'З',
    '{': 'Х', '}': 'Ъ', 'A': 'Ф', 'S': 'Ы', 'D': 'В', 'F': 'А', 'G': 'П', 'H': 'Р', 'J': 'О', 'K': 'Л',
    'L': 'Д', ':': 'Ж', '"': 'Э', 'Z': 'Я', 'X': 'Ч', 'C': 'С', 'V': 'М', 'B': 'И', 'N': 'Т', 'M': 'Ь',
    '<': 'Б', '>': 'Ю', '?': '?', '~': 'Ё',
    '@': '"', '#': '№', '$': ';', '^': ':', '&': '&'
}

# Карта переключения RU -> EN
RU_TO_EN = {v: k for k, v in EN_TO_RU.items()}


class LSwitch:
    def __init__(self, config_path='config.json'):
        self.config = self.load_config(config_path)
        self.last_shift_press = 0
        self.double_click_timeout = self.config.get('double_click_timeout', 0.3)
        
        # Создаём виртуальную клавиатуру для эмуляции событий
        self.fake_kb_name = 'LSwitch Virtual Keyboard'
        self.fake_kb = evdev.UInput(name=self.fake_kb_name)
        
        # Буфер событий для повторного ввода
        self.event_buffer = collections.deque(maxlen=1000)
        self.chars_in_buffer = 0
        
        # Коды клавиш для отслеживания (алфавитно-цифровые + пробел)
        self.active_keycodes = set(range(2, 58))  # От '1' до '/'
        self.active_keycodes.add(ecodes.KEY_SPACE)  # Добавляем пробел!
        self.active_keycodes.difference_update((15, 28, 29, 56))  # Убираем Tab, Enter, Ctrl, Alt
        
        self.is_converting = False
        self.sleep_time = 0.005  # 5ms между нажатиями
        
        # Отслеживание реального выделения
        self.last_known_selection = ''  # Последняя известная PRIMARY selection
        self.selection_timestamp = 0  # Время последнего изменения выделения
        
        # Флаг: последний введённый символ был пробелом
        self.last_was_space = False
    
    def load_config(self, config_path):
        """Загружает конфигурацию из файла"""
        default_config = {
            'double_click_timeout': 0.3,
            'debug': False,
            'switch_layout_after_convert': True,
            'layout_switch_key': 'Alt_L+Shift_L'
        }
        
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    default_config.update(config)
                    print(f"✓ Конфиг загружен: {config_path}")
            except Exception as e:
                print(f"⚠️  Ошибка чтения конфига: {e}")
        
        return default_config
    
    def tap_key(self, keycode, n_times=1):
        """Эмулирует нажатие клавиши через виртуальную клавиатуру"""
        for _ in range(n_times):
            time.sleep(self.sleep_time)
            self.fake_kb.write(ecodes.EV_KEY, keycode, 1)  # Нажатие
            self.fake_kb.syn()
            time.sleep(self.sleep_time)
            self.fake_kb.write(ecodes.EV_KEY, keycode, 0)  # Отпускание
            self.fake_kb.syn()
    
    def replay_events(self, events):
        """Воспроизводит записанные события клавиатуры"""
        for event in events:
            time.sleep(self.sleep_time)
            self.fake_kb.write(ecodes.EV_KEY, event.code, event.value)
            self.fake_kb.syn()
    
    def clear_buffer(self):
        """Очищает буфер событий"""
        self.event_buffer.clear()
        self.chars_in_buffer = 0
    
    def convert_text(self, text):
        """Конвертирует текст между раскладками"""
        if not text:
            return text
        
        # Определяем раскладку по количеству символов
        ru_chars = sum(1 for c in text if c in RU_TO_EN)
        en_chars = sum(1 for c in text if c in EN_TO_RU)
        
        if ru_chars > en_chars:
            # Конвертируем RU -> EN
            return ''.join(RU_TO_EN.get(c, c) for c in text)
        else:
            # Конвертируем EN -> RU
            return ''.join(EN_TO_RU.get(c, c) for c in text)
    
    def convert_selection(self):
        """Конвертирует выделенный текст через PRIMARY selection (без порчи clipboard)"""
        if self.is_converting:
            return
        
        self.is_converting = True
        
        try:
            # Получаем выделенный текст из PRIMARY selection (не трогаем clipboard!)
            try:
                selected_text = subprocess.run(
                    ['xclip', '-o', '-selection', 'primary'],
                    capture_output=True, timeout=0.5, text=True
                ).stdout
            except Exception:
                selected_text = ''
            
            if selected_text:
                # Конвертируем
                converted = self.convert_text(selected_text)
                
                if self.config.get('debug'):
                    print(f"Выделенное: '{selected_text}' -> '{converted}'")
                
                # Удаляем выделенное через BackSpace
                num_chars = len(selected_text)
                self.tap_key(ecodes.KEY_BACKSPACE, num_chars)
                
                time.sleep(0.02)
                
                # Печатаем конвертированный текст через xdotool
                # (не можем через evdev - сложные символы типа кириллицы)
                subprocess.run(
                    ['xdotool', 'type', '--clearmodifiers', '--', converted],
                    timeout=1, stderr=subprocess.DEVNULL
                )
                
                time.sleep(0.05)
                
                # Переключаем раскладку если нужно
                if self.config.get('switch_layout_after_convert', True):
                    self.switch_keyboard_layout()
                
                # Обновляем снимок - это выделение уже обработано
                self.update_selection_snapshot()
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
        """Переключает раскладку клавиатуры через setxkbmap"""
        try:
            if self.config.get('debug'):
                print(f"🔄 Переключаю раскладку...")
            
            # Получаем список раскладок
            result = subprocess.run(
                ['setxkbmap', '-query'],
                capture_output=True, text=True, timeout=1
            )
            
            all_layouts = []
            for line in result.stdout.split('\n'):
                if line.startswith('layout:'):
                    layouts_str = line.split(':')[1].strip()
                    all_layouts = layouts_str.split(',')
                    break
            
            if len(all_layouts) > 1:
                # Циклически переключаем на следующую раскладку
                current_layout = all_layouts[0]
                next_layout = all_layouts[1] if current_layout == all_layouts[0] else all_layouts[0]
                new_order = ','.join([next_layout] + [l for l in all_layouts if l != next_layout])
                subprocess.run(['setxkbmap', new_order], timeout=1)
                
                if self.config.get('debug'):
                    print(f"✓ Раскладка переключена: {current_layout} → {next_layout}")
                    
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
    
    def convert_and_retype(self):
        """Конвертирует и перепечатывает последнее слово"""
        if self.is_converting or self.chars_in_buffer == 0:
            return
        
        self.is_converting = True
        
        try:
            if self.config.get('debug'):
                print(f"Конвертирую {self.chars_in_buffer} символов...")
            
            # КРИТИЧНО: сохраняем копию событий ДО очистки буфера!
            events_to_replay = list(self.event_buffer)
            num_chars = self.chars_in_buffer
            
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
            self.event_buffer = collections.deque(events_to_replay, maxlen=1000)
            self.chars_in_buffer = num_chars
            
            if self.config.get('debug'):
                print("✓ Конвертация завершена")
            
        except Exception as e:
            print(f"⚠️  Ошибка: {e}")
        finally:
            self.is_converting = False
    
    def handle_event(self, event):
        """Обработка событий клавиатуры"""
        if self.is_converting:
            return
        
        # Обрабатываем только нажатия и отпускания клавиш
        if event.type != ecodes.EV_KEY:
            return
        
        current_time = time.time()
        
        # Shift: проверяем двойное нажатие
        if event.code in (ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT):
            if event.value == 0:  # Отпускание
                if current_time - self.last_shift_press < self.double_click_timeout:
                    if self.config.get('debug'):
                        print("✓ Двойной Shift обнаружен!")
                    
                    # Интуитивная логика: есть выделение → конвертируем выделенное
                    if self.has_selection():
                        if self.config.get('debug'):
                            print("→ Конвертирую выделенный текст")
                        self.convert_selection()
                    else:
                        if self.config.get('debug'):
                            print("→ Конвертирую последнее слово")
                        self.convert_and_retype()
                    
                    self.last_shift_press = 0
                else:
                    self.last_shift_press = current_time
            return
        
        # ESC - выход
        if event.code == ecodes.KEY_ESC and event.value == 0:
            print("Выход...")
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
            # Если последний был пробел и это НЕ пробел - сбрасываем старое слово
            if self.last_was_space and event.code != ecodes.KEY_SPACE:
                # Просто очищаем буфер, начинаем новое слово БЕЗ пробела
                self.clear_buffer()
                # Обновляем снимок выделения
                self.update_selection_snapshot()
                # Сбрасываем флаг
                self.last_was_space = False
                
                if self.config.get('debug'):
                    print("Сброс буфера после пробела, начало нового слова")
            
            self.event_buffer.append(event)
            
            # Считаем символы (только при отпускании клавиши)
            if event.value == 0:  # Отпускание
                if event.code == ecodes.KEY_BACKSPACE:
                    if self.chars_in_buffer > 0:
                        self.chars_in_buffer -= 1
                        # Удаляем последнее событие из буфера
                        if len(self.event_buffer) >= 2:
                            self.event_buffer.pop()  # Удаляем release
                            self.event_buffer.pop()  # Удаляем press
                elif event.code not in (ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT):
                    self.chars_in_buffer += 1
                    
                # Запоминаем если это был пробел
                if event.code == ecodes.KEY_SPACE:
                    self.last_was_space = True
            
            if self.config.get('debug'):
                print(f"Буфер: {self.chars_in_buffer} символов")
        
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
            device = evdev.InputDevice(path)
            # КРИТИЧНО: пропускаем нашу виртуальную клавиатуру!
            if device.name != self.fake_kb_name:
                device_selector.register(device, selectors.EVENT_READ)
                devices.append(device)
                if self.config.get('debug'):
                    print(f"   Подключено: {device.name}")
        
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
                for key, mask in device_selector.select():
                    device = key.fileobj
                    for event in device.read():
                        if self.handle_event(event) is False:
                            return
        except KeyboardInterrupt:
            print("\nВыход по Ctrl+C...")
        finally:
            # Закрываем виртуальную клавиатуру
            self.fake_kb.close()


if __name__ == "__main__":
    # Проверяем права root
    if getpass.getuser() != 'root':
        print("❌ LSwitch должен запускаться от root для доступа к /dev/input/")
        print("   Запустите: sudo python3 lswitch.py")
        exit(126)
    
    app = LSwitch()
    app.run()
