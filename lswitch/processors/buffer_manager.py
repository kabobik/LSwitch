"""
BufferManager - управляет буферами событий и текста
"""
import time
from typing import List, Any
from collections import deque


class BufferManager:
    """Менеджер для управления буферами событий и текста"""
    
    def __init__(self, config: dict, debug: bool = False):
        self.config = config
        self.debug = debug
        self.event_buffer: List[Any] = []
        self.text_buffer: deque = deque(maxlen=self.config.get('max_chars_in_buffer', 80))
        self.chars_in_buffer = 0
        
        # Backspace tracking
        self.had_backspace = False
        self.consecutive_backspace_repeats = 0
        self.backspace_hold_detected = False
        self.backspace_hold_detected_at = 0.0
    
    def clear(self):
        """Очищает буфер событий и текстовый буфер"""
        from evdev import ecodes
        
        currently_pressed = {}
        for event in self.event_buffer:
            if event.code in (ecodes.BTN_LEFT, ecodes.BTN_RIGHT, ecodes.BTN_MIDDLE):
                continue
            if event.value == 1:
                currently_pressed[event.code] = event
            elif event.value == 0:
                currently_pressed.pop(event.code, None)
        
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
        if self.backspace_hold_detected_at and (time.time() - self.backspace_hold_detected_at) < 0.5:
            # Recent hold: preserve flag for short window
            if self.debug:
                print(f"{time.time():.6f} ▸ Preserving backspace_hold_detected (recent: {time.time() - self.backspace_hold_detected_at:.3f}s)", flush=True)
            # leave self.backspace_hold_detected as-is
        else:
            self.backspace_hold_detected = False
            self.backspace_hold_detected_at = 0.0
    
    def add_char_to_buffer(self, char: str):
        """Добавляет символ в текстовый буфер"""
        if char and char.isprintable():
            self.text_buffer.append(char)
            self.chars_in_buffer = len(self.text_buffer)
    
    def remove_char_from_buffer(self):
        """Удаляет символ из буфера (backspace)"""
        if self.text_buffer:
            self.text_buffer.pop()
            self.chars_in_buffer = len(self.text_buffer)
            self.had_backspace = True
    
    def get_text(self) -> str:
        """Возвращает текст из буфера"""
        return ''.join(self.text_buffer)
    
    def add_event(self, event):
        """Добавляет событие в буфер событий"""
        self.event_buffer.append(event)
    
    def get_events_copy(self) -> List[Any]:
        """Возвращает копию буфера событий"""
        return list(self.event_buffer)
    
    def has_content(self) -> bool:
        """Проверяет есть ли содержимое в буфере"""
        return self.chars_in_buffer > 0