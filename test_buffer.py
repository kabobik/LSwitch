#!/usr/bin/env python3
"""
Тестовый скрипт для проверки логики буфера
Эмулирует события клавиш и показывает состояние буферов
"""

from evdev import ecodes

class BufferTest:
    def __init__(self):
        self.text_buffer = []
        self.event_buffer = []
        self.chars_in_buffer = 0
        
        # Маппинг кодов клавиш на символы
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
    
    def process_event(self, keycode, value, description=""):
        """Обрабатывает событие клавиши"""
        # Добавляем в event_buffer
        self.event_buffer.append({'code': keycode, 'value': value})
        
        # Обрабатываем только отпускания и repeats
        if value in (0, 2):  # Release или Repeat
            if keycode == ecodes.KEY_BACKSPACE:
                # Backspace
                if self.chars_in_buffer > 0:
                    self.chars_in_buffer -= 1
                    if self.text_buffer:
                        removed = self.text_buffer.pop()
                        print(f"  BS: удалил '{removed}' из text_buffer")
            elif keycode in self.key_map:
                # Обычная клавиша
                char = self.key_map[keycode]
                self.text_buffer.append(char)
                self.chars_in_buffer += 1
                print(f"  +'{char}' → text_buffer")
        
        self.show_state(description)
    
    def show_state(self, description=""):
        """Показывает текущее состояние буферов"""
        text = ''.join(self.text_buffer)
        print(f"  [{description}]")
        print(f"    text_buffer: '{text}' (len={len(self.text_buffer)})")
        print(f"    chars_in_buffer: {self.chars_in_buffer}")
        print(f"    event_buffer: {len(self.event_buffer)} событий")
        
        # Показываем события
        bs_count = sum(1 for e in self.event_buffer if e['code'] == ecodes.KEY_BACKSPACE)
        key_count = sum(1 for e in self.event_buffer if e['code'] in self.key_map and e['value'] == 0)
        print(f"      (букв: {key_count}, BS: {bs_count})")
        print()
    
    def simulate_conversion(self):
        """Симулирует конвертацию"""
        print("\n" + "="*50)
        print("КОНВЕРТАЦИЯ:")
        print("="*50)
        
        num_chars = len(self.text_buffer)
        print(f"1. Удаляем {num_chars} символов с экрана")
        print(f"   Текст на экране ДО: '{''.join(self.text_buffer)}'")
        print(f"   Текст на экране ПОСЛЕ: '' (пусто)")
        
        print(f"\n2. Переключаем раскладку en→ru")
        
        print(f"\n3. Воспроизводим {len(self.event_buffer)} событий:")
        
        # Симулируем воспроизведение
        simulated_text = []
        for event in self.event_buffer:
            if event['value'] in (0, 2):  # Release или Repeat
                if event['code'] == ecodes.KEY_BACKSPACE:
                    if simulated_text:
                        removed = simulated_text.pop()
                        print(f"   BS: удалил '{removed}'")
                elif event['code'] in self.key_map:
                    # Конвертируем в русскую раскладку (упрощенно)
                    en_to_ru = {'q':'й', 'w':'ц', 'e':'у', 'r':'к', 't':'е', 'y':'н', 
                                'u':'г', 'i':'ш', 'o':'щ', 'p':'з', 'a':'ф', 's':'ы',
                                'd':'в', 'f':'а', 'g':'п', 'h':'р', 'j':'о', 'k':'л',
                                'l':'д', 'z':'я', 'x':'ч', 'c':'с', 'v':'м', 'b':'и',
                                'n':'т', 'm':'ь'}
                    en_char = self.key_map[event['code']]
                    ru_char = en_to_ru.get(en_char, en_char)
                    simulated_text.append(ru_char)
                    print(f"   +'{ru_char}'")
        
        result = ''.join(simulated_text)
        print(f"\n✅ РЕЗУЛЬТАТ: '{result}'")
        print(f"   Ожидалось: '{''.join([en_to_ru.get(c, c) for c in self.text_buffer])}'")
        print(f"   Совпадает: {result == ''.join([en_to_ru.get(c, c) for c in self.text_buffer])}")
        
        # Мапинг для проверки
        en_to_ru = {'q':'й', 'w':'ц', 'e':'у', 'r':'к', 't':'е', 'y':'н', 
                    'u':'г', 'i':'ш', 'o':'щ', 'p':'з', 'a':'ф', 's':'ы',
                    'd':'в', 'f':'а', 'g':'п', 'h':'р', 'j':'о', 'k':'л',
                    'l':'д', 'z':'я', 'x':'ч', 'c':'с', 'v':'м', 'b':'и',
                    'n':'т', 'm':'ь'}


print("="*60)
print("ТЕСТ 1: Простое слово без удалений")
print("="*60)
test1 = BufferTest()
print("Печатаем: test")
test1.process_event(ecodes.KEY_T, 1, "t↓")
test1.process_event(ecodes.KEY_T, 0, "t↑")
test1.process_event(ecodes.KEY_E, 1, "e↓")
test1.process_event(ecodes.KEY_E, 0, "e↑")
test1.process_event(ecodes.KEY_S, 1, "s↓")
test1.process_event(ecodes.KEY_S, 0, "s↑")
test1.process_event(ecodes.KEY_T, 1, "t↓")
test1.process_event(ecodes.KEY_T, 0, "t↑")
test1.simulate_conversion()

print("\n\n")
print("="*60)
print("ТЕСТ 2: С одиночными Backspace")
print("="*60)
test2 = BufferTest()
print("Печатаем: qwertyuiop")
for key in [ecodes.KEY_Q, ecodes.KEY_W, ecodes.KEY_E, ecodes.KEY_R, ecodes.KEY_T,
            ecodes.KEY_Y, ecodes.KEY_U, ecodes.KEY_I, ecodes.KEY_O, ecodes.KEY_P]:
    test2.process_event(key, 1, "↓")
    test2.process_event(key, 0, "↑")

print("\nУдаляем 6 раз (одиночные Backspace):")
for i in range(6):
    test2.process_event(ecodes.KEY_BACKSPACE, 1, f"BS{i+1}↓")
    test2.process_event(ecodes.KEY_BACKSPACE, 0, f"BS{i+1}↑")

test2.simulate_conversion()

print("\n\n")
print("="*60)
print("ТЕСТ 3: С удержанием Backspace (repeats)")
print("="*60)
test3 = BufferTest()
print("Печатаем: qwertyuiop")
for key in [ecodes.KEY_Q, ecodes.KEY_W, ecodes.KEY_E, ecodes.KEY_R, ecodes.KEY_T,
            ecodes.KEY_Y, ecodes.KEY_U, ecodes.KEY_I, ecodes.KEY_O, ecodes.KEY_P]:
    test3.process_event(key, 1, "↓")
    test3.process_event(key, 0, "↑")

print("\nУдерживаем Backspace (6 удалений):")
test3.process_event(ecodes.KEY_BACKSPACE, 1, "BS↓ press")
test3.process_event(ecodes.KEY_BACKSPACE, 2, "BS⟳ repeat1")
test3.process_event(ecodes.KEY_BACKSPACE, 2, "BS⟳ repeat2")
test3.process_event(ecodes.KEY_BACKSPACE, 2, "BS⟳ repeat3")
test3.process_event(ecodes.KEY_BACKSPACE, 2, "BS⟳ repeat4")
test3.process_event(ecodes.KEY_BACKSPACE, 0, "BS↑ release")

test3.simulate_conversion()
