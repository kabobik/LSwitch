#!/usr/bin/env python3
"""
Интерактивный тест логики буфера с РЕАЛЬНЫМ вводом
Нажмите F12 чтобы увидеть что будет при конвертации
Ctrl+C для выхода
"""

import evdev
from evdev import ecodes
import sys
import os
import time

# Detect if running under pytest and whether live tests were requested (via CLI or env)
RUN_LIVE = ('--run-live' in sys.argv) or os.environ.get('RUN_LIVE_TESTS') == '1'
# parse live timeout from CLI or env
LIVE_TIMEOUT = 20
for arg in sys.argv:
    if arg.startswith('--live-timeout='):
        try:
            LIVE_TIMEOUT = int(arg.split('=', 1)[1])
        except Exception:
            pass
if os.environ.get('LIVE_TIMEOUT'):
    try:
        LIVE_TIMEOUT = int(os.environ.get('LIVE_TIMEOUT'))
    except Exception:
        pass

# When imported by pytest, skip the module unless --run-live is present
if 'pytest' in sys.modules and not RUN_LIVE:
    import pytest
    pytest.skip("Live interactive test skipped by default. Run with --run-live or set RUN_LIVE_TESTS=1", allow_module_level=True)

class LiveBufferTest:
    def __init__(self, timeout=20):
        self.text_buffer = []
        self.event_buffer = []
        self.chars_in_buffer = 0
        self.last_activity = time.time()
        self.stop_requested = False
        self.timeout = timeout
        
        # Маппинг клавиш
        self.key_map = {
            ecodes.KEY_Q: 'q', ecodes.KEY_W: 'w', ecodes.KEY_E: 'e',
            ecodes.KEY_R: 'r', ecodes.KEY_T: 't', ecodes.KEY_Y: 'y',
            ecodes.KEY_U: 'u', ecodes.KEY_I: 'i', ecodes.KEY_O: 'o',
            ecodes.KEY_P: 'p', ecodes.KEY_A: 'a', ecodes.KEY_S: 's',
            ecodes.KEY_D: 'd', ecodes.KEY_F: 'f', ecodes.KEY_G: 'g',
            ecodes.KEY_H: 'h', ecodes.KEY_J: 'j', ecodes.KEY_K: 'k',
            ecodes.KEY_L: 'l', ecodes.KEY_Z: 'z', ecodes.KEY_X: 'x',
            ecodes.KEY_C: 'c', ecodes.KEY_V: 'v', ecodes.KEY_B: 'b',
            ecodes.KEY_N: 'n', ecodes.KEY_M: 'm',
        }
        
        # Для конвертации
        self.en_to_ru = {
            'q':'й', 'w':'ц', 'e':'у', 'r':'к', 't':'е', 'y':'н', 
            'u':'г', 'i':'ш', 'o':'щ', 'p':'з', 'a':'ф', 's':'ы',
            'd':'в', 'f':'а', 'g':'п', 'h':'р', 'j':'о', 'k':'л',
            'l':'д', 'z':'я', 'x':'ч', 'c':'с', 'v':'м', 'b':'и',
            'n':'т', 'm':'ь'
        }
    
    def handle_event(self, event):
        """Обрабатывает событие клавиатуры"""
        if event.type != ecodes.EV_KEY:
            return

        # Update activity timer on any key event
        self.last_activity = time.time()

        # ESC -> request stop
        if event.code == ecodes.KEY_ESC and event.value == 0:
            self.stop_requested = True
            print("\n⏹️ ESC pressed — stopping live test...", flush=True)
            return

        # F12 - показать симуляцию конвертации
        if event.code == ecodes.KEY_F12 and event.value == 0:
            self.show_conversion_simulation()
            return

        # Добавляем в event_buffer
        self.event_buffer.append({'code': event.code, 'value': event.value})

        # Обрабатываем только отпускания и repeats
        if event.value in (0, 2):
            if event.code == ecodes.KEY_BACKSPACE:
                if self.chars_in_buffer > 0:
                    self.chars_in_buffer -= 1
                    if self.text_buffer:
                        removed = self.text_buffer.pop()
                        val_str = "⟳" if event.value == 2 else "↑"
                        print(f"  BS{val_str} удалил '{removed}'", flush=True)
                        self.show_status()
            elif event.code in self.key_map:
                char = self.key_map[event.code]
                self.text_buffer.append(char)
                self.chars_in_buffer += 1
                print(f"  +'{char}'", flush=True)
                self.show_status()
    
    def show_status(self):
        """Показывает текущее состояние"""
        text = ''.join(self.text_buffer)
        bs_count = sum(1 for e in self.event_buffer if e['code'] == ecodes.KEY_BACKSPACE)
        key_count = sum(1 for e in self.event_buffer if e['code'] in self.key_map and e['value'] == 0)
        
        print(f"  📊 text_buffer: '{text}' (len={len(self.text_buffer)})", flush=True)
        print(f"     event_buffer: {len(self.event_buffer)} событий (букв:{key_count}, BS:{bs_count})", flush=True)
        print(f"     chars_in_buffer: {self.chars_in_buffer}", flush=True)
        print()
    
    def show_conversion_simulation(self):
        """Показывает что произойдет при конвертации"""
        print("\n" + "="*60)
        print("🔄 СИМУЛЯЦИЯ КОНВЕРТАЦИИ (как будет работать двойной Shift)")
        print("="*60)
        
        num_chars = len(self.text_buffer)
        current_text = ''.join(self.text_buffer)
        
        print(f"\n1️⃣  На экране сейчас: '{current_text}'")
        print(f"2️⃣  Удаляем {num_chars} символов → экран пустой")
        print(f"3️⃣  Переключаем раскладку en→ru")
        print(f"4️⃣  Воспроизводим {len(self.event_buffer)} событий:\n")
        
        # Симулируем воспроизведение
        simulated = []
        step = 0
        for event in self.event_buffer:
            if event['value'] in (0, 2):
                if event['code'] == ecodes.KEY_BACKSPACE:
                    if simulated:
                        removed = simulated.pop()
                        step += 1
                        val_str = "⟳" if event['value'] == 2 else "↑"
                        print(f"    {step}. BS{val_str}: удалить '{removed}' → '{''.join(simulated)}'")
                elif event['code'] in self.key_map:
                    en_char = self.key_map[event['code']]
                    ru_char = self.en_to_ru.get(en_char, en_char)
                    simulated.append(ru_char)
                    step += 1
                    print(f"    {step}. +'{ru_char}' → '{''.join(simulated)}'")
        
        result = ''.join(simulated)
        expected = ''.join([self.en_to_ru.get(c, c) for c in self.text_buffer])
        
        print(f"\n✅ ИТОГОВЫЙ РЕЗУЛЬТАТ: '{result}'")
        print(f"   Ожидалось: '{expected}'")
        print(f"   ✓ Правильно" if result == expected else f"   ❌ ОШИБКА!")
        print("="*60 + "\n")


print("="*60)
print("🎮 ИНТЕРАКТИВНЫЙ ТЕСТ БУФЕРА")
print("="*60)
print("\n📝 Инструкция:")
print("  • Печатайте текст как обычно")
print("  • Используйте Backspace (одиночно или удержанием)")
print("  • Нажмите F12 чтобы увидеть симуляцию конвертации")
print("  • Ctrl+C для выхода\n")
print("="*60 + "\n")

# Находим клавиатуру
devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
keyboards = []
for device in devices:
    caps = device.capabilities()
    if ecodes.EV_KEY in caps:
        keys = caps.get(ecodes.EV_KEY, [])
        if ecodes.KEY_A in keys:
            keyboards.append(device)
            print(f"✓ Найдена клавиатура: {device.name}")

if not keyboards:
    print("❌ Клавиатура не найдена!")
    sys.exit(1)

print(f"\n🎯 Начинаем мониторинг...\n")

tester = LiveBufferTest()

try:
    # Try to grab devices — handle devices that disappear gracefully
    for device in list(keyboards):
        try:
            device.grab()  # Перехватываем события (осторожно!)
        except OSError as e:
            print(f"⚠️ Не удалось захватить устройство {device.name}: {e}")
            keyboards.remove(device)

    if not keyboards:
        print("❌ Нет доступных клавиатур для захвата — выходим")
        sys.exit(1)

    print(f"⚠️  ВНИМАНИЕ: Клавиатура перехвачена! Для выхода нажмите ESC (или подождите {LIVE_TIMEOUT}s бездействия)\n")

    while True:
        now = time.time()
        # Inactivity auto-exit
        if now - tester.last_activity > tester.timeout:
            print(f"\n⏲️ {tester.timeout}s бездействия — авто-завершение live test\n")
            break

        if tester.stop_requested:
            break

        for device in list(keyboards):
            try:
                for event in device.read():
                    tester.handle_event(event)
            except BlockingIOError:
                pass
            except OSError as e:
                # Device disappeared; ungrab will fail — remove it and continue
                print(f"⚠️ Устройство {device.name} исчезло: {e}")
                try:
                    device.ungrab()
                except Exception:
                    pass
                try:
                    keyboards.remove(device)
                except ValueError:
                    pass
        # small sleep to avoid busy loop
        time.sleep(0.01)

except KeyboardInterrupt:
    print("\n\n👋 Выход...")
finally:
    for device in list(keyboards):
        try:
            device.ungrab()
        except Exception:
            pass
    print("✅ Live test finished — cleanup done")
