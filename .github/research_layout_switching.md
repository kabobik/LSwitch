# Исследование LSwitch: Переключение раскладок и баги

**Дата:** 2026-02-18  
**Исследователь:** research-agent

## 1. Архитектура переключения раскладок

### 1.1 Текущая реализация

#### Обнаружение раскладок
**Файл:** [lswitch/xkb.py](../lswitch/xkb.py#L67-L107)

```python
def get_layouts_from_xkb(runtime_dir: str | None = None, debug: bool = False) -> list:
```

Раскладки определяются по приоритету:
1. Из файла `{XDG_RUNTIME_DIR}/lswitch_layouts.json` (if fresh < 60 сек)
2. Через `setxkbmap -query` (парсится строка `layout:`)
3. Fallback: `['en', 'ru']`

**Важно:** Раскладки `us` автоматически маппятся в `en` (строка 99):
```python
result_list = ['en' if l == 'us' else l for l in layouts]
```

#### Определение текущей раскладки
**Файл:** [lswitch/xkb.py](../lswitch/xkb.py#L110-L132)

```python
def get_current_layout(layouts: list, debug: bool = False) -> str:
```

Использует libX11 XkbGetState:
- Читает `state.group` — индекс текущей группы XKB
- Возвращает `layouts[group]`

#### Функция переключения
**Файл:** [lswitch/core.py](../lswitch/core.py#L833-L888)

```python
def switch_keyboard_layout(self):
    # ...
    next_index = (current_index + 1) % len(self.layouts)
    ret = libX11.XkbLockGroup(display_ptr, 0x100, next_index)
```

**КРИТИЧНО:** Текущая реализация — **только циклический перебор**!
- Нет API для переключения на конкретную раскладку по имени
- Нет поиска совместимых раскладок

#### Карты конвертации
**Файл:** [lswitch/conversion_maps.py](../lswitch/conversion_maps.py)

```python
EN_TO_RU = {
    'q': 'й', 'w': 'ц', 'e': 'у', ...
}
RU_TO_EN = {v: k for k, v in EN_TO_RU.items()}
```

**Ограничение:** Поддерживаются только EN↔RU. Нет ESP, DE, FR и других.

### 1.2 Как перейти к переключению по имени раскладки

Для реализации переключения на конкретную раскладку (Ru, Us, Es) нужно:

**1. Добавить функцию в `lswitch/xkb.py`:**

```python
def switch_to_layout(target_name: str, layouts: list, debug: bool = False) -> bool:
    """Переключает на конкретную раскладку по имени.
    
    Args:
        target_name: Имя раскладки ('ru', 'en', 'es')
        layouts: Список доступных раскладок
        
    Returns:
        True если переключение успешно
    """
    if not XKB_AVAILABLE or not libX11:
        return False
    
    # Нормализация имени
    normalized = 'en' if target_name.lower() in ('us', 'en') else target_name.lower()
    
    # Поиск индекса целевой раскладки
    target_index = None
    for i, layout in enumerate(layouts):
        if layout.lower() == normalized:
            target_index = i
            break
    
    if target_index is None:
        if debug:
            print(f"⚠️ Layout '{target_name}' not found in {layouts}")
        return False
    
    try:
        display_ptr = libX11.XOpenDisplay(None)
        if display_ptr:
            try:
                ret = libX11.XkbLockGroup(display_ptr, 0x100, target_index)
                libX11.XFlush(display_ptr)
                return ret == True or ret == 1
            finally:
                libX11.XCloseDisplay(display_ptr)
    except Exception:
        pass
    return False
```

**2. Добавить метод в `LSwitch` (core.py):**

```python
def switch_to_layout(self, target_layout: str) -> bool:
    """Переключиться на конкретную раскладку."""
    from lswitch.xkb import switch_to_layout
    success = switch_to_layout(target_layout, self.layouts, self.config.get('debug'))
    if success:
        self.current_layout = target_layout
    return success
```

### 1.3 Совместимые раскладки и fallback

Для поддержки fallback (если us нет — искать es), нужно:

**1. Определить группы совместимости:**

```python
# В новом файле lswitch/layout_compatibility.py
LAYOUT_GROUPS = {
    'latin': ['us', 'en', 'es', 'de', 'fr', 'it', 'pt'],
    'cyrillic': ['ru', 'ua', 'by', 'bg'],
    'arabic': ['ar', 'fa'],
    'cjk': ['zh', 'ja', 'ko'],
}

def find_compatible_layout(target: str, available: list) -> str | None:
    """Находит совместимую раскладку или None."""
    normalized = target.lower()
    
    # Прямое совпадение
    if normalized in [l.lower() for l in available]:
        return normalized
    
    # Поиск в группах совместимости
    for group, layouts in LAYOUT_GROUPS.items():
        if normalized in layouts:
            # Ищем любую раскладку из той же группы
            for layout in layouts:
                if layout in [l.lower() for l in available]:
                    return layout
    
    return None
```

**2. Использовать в конвертации:**

```python
def convert_text(self, text, target_layout=None):
    """Конвертирует текст, при необходимости ищет совместимую раскладку."""
    if target_layout:
        actual = find_compatible_layout(target_layout, self.layouts)
        if actual and actual != self.current_layout:
            self.switch_to_layout(actual)
```

**3. Расширить карты конвертации:**

Для поддержки испанского и других раскладок нужно добавить карты в `conversion_maps.py`:

```python
EN_TO_ES = {
    'q': 'q', 'w': 'w', 'e': 'e', ...
    # Специфичные символы
    ';': 'ñ', "'": '´',
}
```

---

## 2. Механизм отслеживания ввода

### 2.1 Накопление текста

**Файлы:**
- [lswitch/utils/buffer.py](../lswitch/utils/buffer.py) — InputBuffer
- [lswitch/core.py](../lswitch/core.py#L113-L130) — proxy properties

#### Структура буфера:
```python
class InputBuffer:
    event_buffer: deque  # evdev события для replay
    text_buffer: list    # символы для словаря/конвертации
    chars_in_buffer: int # счётчик символов
```

#### Потоки данных:
1. **Нажатие клавиши** → `event_buffer.append(event)` 
2. **Отпускание (value=0)** → `chars_in_buffer += 1` + `text_buffer.append(char)`
3. **Shift** → только в `event_buffer` (не считается как символ)

### 2.2 Обработка Backspace

**Файл:** [lswitch/input.py](../lswitch/input.py#L255-L282)

#### Обычное нажатие (value=0):
```python
if event.code == ecodes.KEY_BACKSPACE:
    self.ls.had_backspace = True
    self.ls.consecutive_backspace_repeats = 0
    if self.ls.chars_in_buffer > 0:
        self.ls.chars_in_buffer -= 1
        if self.ls.text_buffer:
            self.ls.text_buffer.pop()
```

#### Удержание (value=2, repeat):
```python
elif event.value == 2:
    if event.code == ecodes.KEY_BACKSPACE:
        self.ls.consecutive_backspace_repeats += 1
        if self.ls.consecutive_backspace_repeats >= 3:
            if not self.ls.backspace_hold_detected:
                self.ls.backspace_hold_detected = True
                self.ls.backspace_hold_detected_at = time.time()
```

#### Флаг сохраняется в `clear_buffer()`:
**Файл:** [lswitch/core.py](../lswitch/core.py#L805-L816)

```python
if getattr(self, 'backspace_hold_detected_at', 0) and (time.time() - self.backspace_hold_detected_at) < 0.5:
    # Сохраняем флаг в течение 0.5 сек
    pass
else:
    self.backspace_hold_detected = False
```

### 2.3 Обработка навигации

**Файл:** [lswitch/input.py](../lswitch/input.py#L155-L168)

```python
# Navigation keys - clear buffer
if getattr(event, 'code', None) in getattr(self.ls, 'navigation_keys', set()) and event.value == 0:
    try:
        self.ls.clear_buffer()
    except Exception:
        pass
    if self.ls.backspace_hold_detected:
        self.ls.backspace_hold_detected = False
        self.ls.backspace_hold_detected_at = 0.0
```

**Навигационные клавиши определены в** [lswitch/core.py](../lswitch/core.py#L445-L449):
```python
self.navigation_keys = {
    ecodes.KEY_LEFT, ecodes.KEY_RIGHT, ecodes.KEY_UP, ecodes.KEY_DOWN,
    ecodes.KEY_HOME, ecodes.KEY_END, ecodes.KEY_PAGEUP, ecodes.KEY_PAGEDOWN,
    ecodes.KEY_TAB
}
```

---

## 3. Найденные баги и проблемы

### 3.1 Bug: Удержание Backspace

#### Проблема
При удержании Backspace счётчик `chars_in_buffer` становится неточным:
- `value=2` (repeat) события НЕ декрементируют счётчик
- После удержания `chars_in_buffer` может быть больше реального числа символов

**Файл:** [lswitch/input.py](../lswitch/input.py#L272-L281)

Комментарий в коде подтверждает:
```python
# НЕ трогаем счетчики - они не точные при repeats!
# Будем использовать выделение слова при конвертации
```

#### Условия воспроизведения
1. Набрать "привет мир" (10 символов)
2. Зажать Backspace на 2-3 секунды
3. Нажать двойной Shift
4. **Результат:** конвертация может удалить лишний текст или не сработать

#### Место в коде
[lswitch/input.py](../lswitch/input.py#L272-L281)

#### Текущий workaround
При `backspace_hold_detected=True` система переключается на режим `selection` вместо `retype`:

**Файл:** [lswitch/conversion.py](../lswitch/conversion.py#L100-L103)
```python
if backspace_hold or getattr(buffer, 'chars_in_buffer', 0) == 0:
    return 'selection'
```

#### Предложения по исправлению

**Вариант 1 (консервативный):** Очищать буфер при первом repeat-событии:
```python
elif event.value == 2:
    if event.code == ecodes.KEY_BACKSPACE:
        # При первом repeat очищаем буфер — он всё равно неточен
        if self.ls.consecutive_backspace_repeats == 0:
            self.ls.clear_buffer()
        self.ls.consecutive_backspace_repeats += 1
```

**Вариант 2 (точный):** Декрементировать счётчик при каждом repeat:
```python
elif event.value == 2:
    if event.code == ecodes.KEY_BACKSPACE:
        if self.ls.chars_in_buffer > 0:
            self.ls.chars_in_buffer -= 1
            if self.ls.text_buffer:
                self.ls.text_buffer.pop()
```

### 3.2 Bug: Навигация стрелками

#### Проблема
При навигации стрелками НЕ обновляется `cursor_moved_at`, что влияет на определение "свежего" выделения.

**Файл:** [lswitch/core.py](../lswitch/core.py#L897-L909)

```python
def has_selection(self):
    # ...
    recent_cursor_move = (
        getattr(self, 'cursor_moved_at', 0.0)
        and (now - self.cursor_moved_at) < self.selection_freshness_window
    )
```

`cursor_moved_at` устанавливается ТОЛЬКО при клике мыши:

**Файл:** [lswitch/core.py](../lswitch/core.py#L1638-L1642)
```python
if event.type == ecodes.EV_KEY and event.code in (
    ecodes.BTN_LEFT, ecodes.BTN_RIGHT, ecodes.BTN_MIDDLE
) and event.value == 1:
    # ...
    self.cursor_moved_at = time.time()
```

#### Условия воспроизведения
1. Выделить текст мышкой
2. Конвертировать (двойной Shift)
3. Нажать стрелку (выделение снимается, но `cursor_moved_at` не обновляется)
4. Снова выделить тот же текст manually или Shift+стрелки
5. Двойной Shift — `has_selection()` может вернуть False

#### Тест подтверждает
**Файл:** [tests/test_selection_freshness_cursor_moved.py](../tests/test_selection_freshness_cursor_moved.py#L67-L95)

```python
def test_arrow_navigation_does_not_make_selection_fresh(monkeypatch):
    """Test that arrow navigation does NOT make selection fresh."""
    # ...
    ev_arrow = SimpleNamespace(type=ecodes.EV_KEY, code=ecodes.KEY_LEFT, value=0)
    ls.input_handler.handle_event(ev_arrow)
    
    # cursor_moved_at should NOT be set by navigation
    assert ls.has_selection() is False
```

#### Предложения по исправлению

**Вариант 1:** Обновлять `cursor_moved_at` при навигации:

В [lswitch/input.py](../lswitch/input.py#L155-L168):
```python
if getattr(event, 'code', None) in getattr(self.ls, 'navigation_keys', set()) and event.value == 0:
    try:
        self.ls.clear_buffer()
    except Exception:
        pass
    # ДОБАВИТЬ: обновление cursor_moved_at
    self.ls.cursor_moved_at = time.time()
```

**Вариант 2:** Отслеживать изменение PRIMARY selection напрямую:
```python
def has_selection(self):
    current_selection = self.system.xclip_get(selection='primary').stdout
    # Выделение считается свежим если:
    # 1. Текст изменился
    # 2. ИЛИ текст не пустой И есть любое недавнее движение курсора
    return bool(current_selection) and (
        current_selection != self.last_known_selection
        or (time.time() - self.cursor_moved_at) < self.selection_freshness_window
    )
```

### 3.3 Другие потенциальные проблемы

#### 3.3.1 Race condition в replay событий

**Файл:** [lswitch/core.py](../lswitch/core.py#L1054-L1062)

При replay событий есть риск повторного срабатывания double-shift:

```python
self.suppress_shift_detection = True
try:
    self.replay_events(events_to_replay)
finally:
    time.sleep(0.05)
    self.suppress_shift_detection = False
    # ...
    self._post_replay_suppress_until = time.time() + max(0.1, self.double_click_timeout)
```

**Проблема:** Между `suppress=False` и установкой `_post_replay_suppress_until` есть микроскопическое окно, когда shift-release может быть обработан.

**Исправление:** Установить `_post_replay_suppress_until` ДО сброса `suppress`:
```python
finally:
    time.sleep(0.05)
    self._post_replay_suppress_until = time.time() + max(0.1, self.double_click_timeout)
    self.suppress_shift_detection = False  # После!
```

#### 3.3.2 Потеря контекста при быстром вводе

При очень быстром наборе может возникнуть ситуация:
1. Набрали слово
2. Нажали пробел (вызывает auto_convert)
3. Пока auto_convert работает, нажата новая буква
4. `is_converting=True` блокирует событие
5. Буква теряется

**Файл:** [lswitch/input.py](../lswitch/input.py#L139-L143)

```python
if self.ls.is_converting:
    if self.ls.config.get('debug'):
        print(f"{time.time():.6f} ▸ Event ignored: is_converting=True", flush=True)
    return True  # События игнорируются!
```

#### 3.3.3 Нет поддержки многобайтовых символов

Карты конвертации работают только с однобайтовыми символами. 
Emoji и специальные символы не конвертируются.

---

## 4. Рекомендации

### 4.1 Приоритет 1 (высокий)

1. **Реализовать `switch_to_layout(target_name)`** — позволит конвертировать ru→en даже если текущая раскладка es

2. **Исправить navigation + cursor_moved_at** — добавить `self.ls.cursor_moved_at = time.time()` в обработчик навигации

3. **Исправить race condition в replay** — переставить строки в finally блоке

### 4.2 Приоритет 2 (средний)

1. **Добавить карты ES↔EN, ES↔RU** в conversion_maps.py

2. **Улучшить обработку backspace hold** — очищать буфер при первом repeat

3. **Добавить layout compatibility groups** для fallback поиска

### 4.3 Приоритет 3 (низкий)

1. **Буферизация событий во время is_converting** — чтобы не терять нажатия

2. **Расширить keycode_to_char для unicode** — поддержка emoji

3. **Рефакторинг:** вынести логику переключения раскладок в отдельный LayoutManager (частично уже есть в `lswitch/managers/layout_manager.py`, но не интегрирован полностью)

---

## Сводная таблица ключевых файлов

| Компонент | Файл | Строки |
|-----------|------|--------|
| Обнаружение раскладок | lswitch/xkb.py | 67-107 |
| Переключение раскладок | lswitch/core.py | 833-888 |
| Карты конвертации | lswitch/conversion_maps.py | 1-28 |
| Обработка backspace | lswitch/input.py | 255-282 |
| Обработка навигации | lswitch/input.py | 155-168 |
| Выбор режима конвертации | lswitch/conversion.py | 90-150 |
| Selection manager | lswitch/selection.py | 1-150 |
| Layout monitor | lswitch/monitor.py | 1-100 |

---

## TODO для реализации

- [ ] Добавить `switch_to_layout()` в xkb.py
- [ ] Добавить метод `switch_to_layout()` в LSwitch класс
- [ ] Создать layout_compatibility.py с группами совместимости
- [ ] Исправить cursor_moved_at при навигации
- [ ] Исправить race condition в replay
- [ ] Добавить тесты для новой функциональности
