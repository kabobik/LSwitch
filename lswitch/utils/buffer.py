"""InputBuffer: инкапсулирует поведение буфера ввода.

Содержит:
- event_buffer (deque of events)
- text_buffer (list of chars)
- chars_in_buffer (int)
- clear(), set_events(), append_event()
"""
from __future__ import annotations
import collections
from typing import Any


class InputBuffer:
    def __init__(self, maxlen: int = 1000) -> None:
        self.event_buffer: collections.deque = collections.deque(maxlen=maxlen)
        self.text_buffer: list[str] = []
        self.chars_in_buffer: int = 0

    def clear(self) -> None:
        """Очищает буфер событий и текстовый буфер, но сохраняет нажатые клавиши"""
        currently_pressed: dict[Any, Any] = {}
        for event in self.event_buffer:
            # исключаем кнопки мыши по коду (оставляем логику совместимой с LSwitch)
            code = getattr(event, 'code', None)
            if code in (1, 272, 274):  # BTN_LEFT, BTN_RIGHT, BTN_MIDDLE - коды в evdev, но мы не импортируем их
                continue
            value = getattr(event, 'value', None)
            if value == 1:
                currently_pressed[getattr(event, 'code', None)] = event
            elif value == 0:
                currently_pressed.pop(getattr(event, 'code', None), None)

        self.event_buffer.clear()
        for ev in currently_pressed.values():
            self.event_buffer.append(ev)

        self.chars_in_buffer = 0
        self.text_buffer.clear()

    def set_events(self, events: list[Any]) -> None:
        self.event_buffer = collections.deque(events, maxlen=self.event_buffer.maxlen)

    def append_event(self, event: Any) -> None:
        self.event_buffer.append(event)

    def get_events(self) -> list[Any]:
        return list(self.event_buffer)
