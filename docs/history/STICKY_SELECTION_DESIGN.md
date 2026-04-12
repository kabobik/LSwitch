# Sticky buffer для SelectionMode — дизайн

**Дата:** 27 февраля 2026  
**Статус:** обсуждение, не реализовано

---

## Проблема

После selection conversion ("ghbdtn" → "привет") повторный Shift+Shift **ничего не делает**:
- `chars_in_buffer == 0`
- `_last_retype_events` пуст
- `fresh == False`

Хочется toggle-чередование как в retype mode.

---

## Почему event_buffer не подойдёт

`event_buffer` хранит `KeyEventData(code, value, shifted)` — реальные keycodes с evdev.
Для текста из PRIMARY ("ghbdtn") потребовалось бы обратное маппирование `char → keycode`,
а это нетривиально (Shift-зависимость, разные раскладки).
Плюс `replay_events()` отправляет keycodes — в другой раскладке получим мусор.

---

## Варианты

### Вариант A: `_last_selection_pair` + backspace + clipboard (рекомендуемый)

Самый простой и консистентный с текущим retype-подходом:

```python
# После SelectionMode.execute():
self._last_selection_pair = ("ghbdtn", "привет")  # (original, converted)

# При повторном Shift+Shift:
# chars_in_buffer==0, _last_retype_events пуст, но _last_selection_pair есть:
original, converted = self._last_selection_pair
1. Backspace × len(converted)     # удалить "привет"
2. Clipboard ← original           # записать "ghbdtn"
3. Ctrl+V                         # вставить
4. Восстановить clipboard
5. switch_layout()
6. self._last_selection_pair = (converted, original)  # swap для следующего toggle
```

**Плюсы:** простота, toggle-чередование, не нужен reverse keycode mapping.  
**Минусы:** тот же, что у retype — если курсор ушёл, backspace удалит не то.
Но для retype это уже принято как ограничение, так что поведение консистентно.

### Вариант B: Re-select + SelectionMode

```
1. Shift+Left × len("привет")  — выделить конвертированный текст
2. SelectionMode.execute()      — автоматически обнаружит "привет", конвертирует обратно
```

**Минусы:** нажатия Shift+Left попадут в наш же EventManager → сломают стейт-машину.
Плюс не во всех контекстах Shift+Left работает одинаково.

### Вариант C: Генерировать синтетические KeyEventData

Создать reverse-mapping `char → (keycode, shifted)`, конвертировать текст
в `_last_retype_events`, и пусть существующий механизм работает.

**Минусы:** сложный reverse-mapping, зависимость от раскладки, дополнительная хрупкость.

---

## Рекомендация: Вариант A

Он зеркально повторяет логику retype sticky: тот же принцип
"помни что было → на повторный Shift+Shift откати".

Сброс `_last_selection_pair` — в тех же местах, что и `_last_retype_events`
(клик, символ, навигация, Enter).

Реализация — ~20 строк в `_do_conversion`.

---

## Изменения при реализации

### `_do_conversion` в app.py

```python
# После успешной selection conversion:
if success and self._selection_valid:
    # Запомнить пару для toggle
    original_text = ...   # текст до конвертации (из SelectionMode)
    converted_text = ...  # текст после конвертации
    self._last_selection_pair = (original_text, converted_text)

# При повторном Shift+Shift (chars==0, retype_events пуст):
if saved_count == 0 and not self._last_retype_events and self._last_selection_pair:
    original, converted = self._last_selection_pair
    # backspace × len(converted), clipboard ← original, Ctrl+V, swap pair
```

### Сброс `_last_selection_pair`

Те же места, что и `_last_retype_events`:
- `_on_key_press` (символ, Backspace, Space)
- `_on_key_release` (Navigation, Enter)
- `_on_mouse_click`

### Тесты

- Повторный Shift+Shift после selection → toggle обратно
- Сброс при наборе текста
- Сброс при клике мыши
- Многократный toggle (A→B→A→B)
