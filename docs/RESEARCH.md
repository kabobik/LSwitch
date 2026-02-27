# Исследование проекта LSwitch — полный отчёт

**Дата:** 27 февраля 2026  
**Автор:** Вася (opus-agent)  
**Версия проекта:** LSwitch 2.0

---

## Часть 1: Полное исследование логики работы программы

---

### 1. Конвертация текста

#### 1.1. Общая архитектура

Конвертация управляется классом `ConversionEngine` (`lswitch/core/conversion_engine.py`). У него два основных метода:

- **`choose_mode(context, selection_valid)`** — выбирает режим конвертации
- **`convert(context, selection_valid)`** — выполняет конвертацию

#### 1.2. Алгоритм выбора режима (`choose_mode`)

Приоритеты (от высшего к низшему):

| Приоритет | Условие | Режим | Логика |
|-----------|---------|-------|--------|
| 1 | `context.backspace_hold_active` | selection | Удержание Backspace — явный жест |
| 2 | `context.chars_in_buffer > 0` | retype | Есть набранные символы — **всегда побеждает** |
| 3 | `selection_valid == True` | selection | Пустой буфер + новое выделение |
| 4 | fallback | retype | RetypeMode пропустит (skip gracefully) |

**Ключевой момент:** если пользователь набрал текст (`chars_in_buffer > 0`), ВСЕГДА используется retype, даже если есть выделение. Selection mode активируется только при пустом буфере.

#### 1.3. RetypeMode (`lswitch/core/modes.py`)

**Принцип:** удалить набранные символы → переключить раскладку → воспроизвести те же нажатия в новой раскладке.

**Пошаговый алгоритм:**

```
1. Проверить chars_in_buffer > 0 — если 0, skip (return False)
2. Сохранить копию event_buffer
3. Отправить N backspace через VirtualKeyboard.tap_key(KEY_BACKSPACE, n_chars)
4. Переключить раскладку через xkb.switch_layout()
5. Пауза 50мс (чтобы приложение успело обработать backspace)
6. Воспроизвести сохранённые события через virtual_kb.replay_events(saved_events)
```

**Важная деталь v2:** в v1 был баг — безусловный Shift release в finally-блоке вызывал XKB Shift+Shift toggle, что приводило к дублированию переключения. В v2 Shift release отправляется только если в буфере событий реально были Shift press.

**Поддержка Shift (uppercase):** каждое событие хранит флаг `shifted` (был ли Shift зажат). При replay, если `shifted=True`, VirtualKeyboard оборачивает нажатие в Shift press/release.

#### 1.4. SelectionMode (`lswitch/core/modes.py`)

**Принцип:** прочитать PRIMARY selection → определить язык → конвертировать текст → вставить обратно.

**Пошаговый алгоритм:**

```
1. Прочитать выделение: self.selection.get_selection()
2. Определить язык исходного текста: detect_language(sel.text) — 'en' или 'ru'
3. Определить направление конвертации: en→ru или ru→en
4. Конвертировать текст: convert_text(sel.text, direction)
5. Заменить выделение: self.selection.replace_selection(converted)
6. Переключить раскладку на целевую: xkb.switch_layout(target=target_layout)
```

**`replace_selection`** работает так:
```
1. Сохранить CLIPBOARD: old_clip = get_clipboard("clipboard")
2. Записать конвертированный текст в CLIPBOARD: set_clipboard(new_text, "clipboard")
3. Имитировать Ctrl+V через xdotool
4. Восстановить CLIPBOARD: set_clipboard(old_clip, "clipboard")
```

#### 1.5. Текстовая конвертация (`lswitch/core/text_converter.py`)

Посимвольная замена по таблице `EN_TO_RU` / `RU_TO_EN` из `lswitch/intelligence/maps.py`. Сохраняет регистр:

```python
for ch in text:
    lower = ch.lower()
    converted = table.get(lower)
    if converted is None:
        result.append(ch)  # символ не в таблице — оставить как есть
    else:
        result.append(converted.upper() if ch.isupper() else converted)
```

Определение языка (`detect_language`): если в тексте есть хотя бы один кириллический символ (`\u0400`–`\u04ff`), это `ru`, иначе `en`.

---

### 2. Сочетания клавиш

#### 2.1. Shift+Shift (двойной Shift)

**Основной триггер конвертации.** Измеряется как время между ПЕРВЫМ release и ВТОРЫМ release (не press→release).

**Механизм (StateManager.on_shift_up):**

```python
delta = now - self.context.last_shift_time
if last_shift_time > 0 and delta < double_click_timeout:   # default 0.3s
    # Двойной Shift обнаружен!
    self._transition("shift_up_double")  # → State.CONVERTING
    return True
else:
    self.context.last_shift_time = now  # запомнить первый release
    return False
```

**Обработка в `_on_key_release`:**
```python
is_double = self.state_manager.on_shift_up()
if is_double:
    self._do_conversion()
```

#### 2.2. Backspace Hold (удержание Backspace)

При авто-повторе Backspace (value=2 от evdev):
```python
ctx.backspace_repeats += 1
if ctx.event_buffer:
    ctx.event_buffer.pop()     # удалить последнее событие из буфера
if ctx.chars_in_buffer > 0:
    ctx.chars_in_buffer -= 1   # уменьшить счётчик
if ctx.backspace_repeats >= 3:
    self.state_manager.on_backspace_hold()  # → State.BACKSPACE_HOLD
```

Из состояния `BACKSPACE_HOLD` доступен переход `shift_up_double → CONVERTING`, что активирует selection mode (через `choose_mode`: `backspace_hold_active → "selection"`).

#### 2.3. Navigation Keys

Клавиши `стрелки`, `Home`, `End`, `PgUp`, `PgDn`, `Tab` (коды 103, 108, 105, 106, 102, 107, 104, 109, 15):
- Сбрасывают `_last_auto_marker`
- Сбрасывают `_selection_valid`
- Очищают `_last_retype_events` (sticky buffer)
- Переводят автомат в `IDLE` через `state_manager.on_navigation()`

#### 2.4. Enter

Аналогично navigation: полный сброс состояния.

#### 2.5. Space

Если включена авто-конвертация (`auto_switch`), при пробеле вызывается `_try_auto_conversion_at_space()`. Если авто-конвертация не сработала, пробел добавляется в буфер как обычный символ.

#### 2.6. MODIFIER_KEYS — фильтрация

Модификаторы **полностью игнорируются** при key_press:

```python
elif data.code in MODIFIER_KEYS:
    pass  # modifiers don't produce text — ignore entirely
```

**Состав MODIFIER_KEYS:**
- `KEY_LEFTCTRL (29)`, `KEY_RIGHTCTRL (97)`
- `KEY_LEFTALT (56)`, `KEY_RIGHTALT (100)`
- `KEY_LEFTMETA (125)`, `KEY_RIGHTMETA (126)`
- `KEY_CAPSLOCK (58)`
- `KEY_INSERT (110)`, `KEY_DELETE (111)`
- `KEY_SYSRQ/PrintScreen (99)`, `KEY_PAUSE (119)`
- `F1–F12 (59–68, 87–88)`

Они не добавляются в `event_buffer`, не увеличивают `chars_in_buffer`, не вызывают transition в StateManager.

---

### 3. Буферы

#### 3.1. event_buffer (`StateContext.event_buffer`)

**Тип:** `list` (список `KeyEventData` объектов)  
**Хранит:** все нажатия клавиш (KEY_PRESS, value=1), кроме Shift, модификаторов и Backspace.

Каждый элемент — `KeyEventData`:
```python
@dataclass
class KeyEventData:
    code: int               # evdev keycode
    value: int              # 0=release, 1=press, 2=repeat
    device_name: str = ""
    shifted: bool = False   # True если Shift был зажат
```

**Добавление:** при обычном key_press:
```python
data.shifted = self.state_manager.context.shift_pressed
self.state_manager.context.event_buffer.append(data)
```

**Удаление:**
- Backspace press: `ctx.event_buffer.pop()` (один элемент)
- Backspace repeat: `ctx.event_buffer.pop()` (один на каждый repeat)
- `context.reset()`: полная очистка

#### 3.2. chars_in_buffer (`StateContext.chars_in_buffer`)

**Тип:** `int`  
**Назначение:** счётчик символов в буфере. Может расходиться с `len(event_buffer)` теоретически, но на практике синхронизирован.

- `+1` при обычном key_press (не Shift, не модификатор, не Backspace)
- `-1` при Backspace release (если > 0)
- `-1` при Backspace repeat (если > 0)
- `= 0` при `context.reset()`

**Используется для:**
- `choose_mode()`: chars_in_buffer > 0 → retype
- `RetypeMode.execute()`: skip если chars_in_buffer ≤ 0
- Auto-conversion: skip если chars_in_buffer == 0

#### 3.3. _last_retype_events (sticky buffer)

**Тип:** `list` (в `LSwitchApp`)  
**Назначение:** позволяет повторный Shift+Shift работать после конвертации.

**Логика:**
```
1. Пользователь набирает "руддщ" → event_buffer = [...], chars_in_buffer = 5
2. Shift+Shift → RetypeMode → event_buffer очищается reset()
3. НО: перед reset(), saved_events сохраняются в _last_retype_events
4. Повторный Shift+Shift → chars_in_buffer == 0 → проверяем _last_retype_events
5. Если не пуст → восстанавливаем буфер из _last_retype_events
6. Конвертация выполняется повторно (обратно)
```

**Сброс _last_retype_events:**
- При любом key_press обычного символа: `self._last_retype_events = []`
- При Backspace: `self._last_retype_events = []`
- При Space: `self._last_retype_events = []`
- При navigation/Enter: `self._last_retype_events = []`
- При mouse_click: `self._last_retype_events = []`
- После SelectionMode конвертации: `self._last_retype_events = []`

**Сохраняется только** после успешного RetypeMode (не SelectionMode).

#### 3.4. PRIMARY selection (X11)

**Чтение:** `xclip -o -selection primary` (через `SubprocessSystemAdapter`)  
**Запись:** только через `replace_selection()` — записывает в CLIPBOARD (не PRIMARY) и Ctrl+V  
**Owner ID:** через `Xlib.display.Display().get_selection_owner(Xatom.PRIMARY).id`

**Взаимодействие буферов:**

```
event_buffer + chars_in_buffer → retype mode (прямая конвертация буфера)
PRIMARY selection              → selection mode (конвертация выделенного текста)
_last_retype_events            → повторный retype (sticky конвертация)
```

Буферы **не взаимодействуют** друг с другом напрямую. `choose_mode()` выбирает один из двух путей.

---

### 4. Автомат состояний

#### 4.1. Состояния (State)

```python
class State(Enum):
    IDLE = auto()           # Ожидание ввода
    TYPING = auto()         # Пользователь печатает
    SHIFT_PRESSED = auto()  # Shift нажат (ожидание второго)
    CONVERTING = auto()     # Выполняется конвертация
    BACKSPACE_HOLD = auto() # Удержание Backspace
```

#### 4.2. Таблица переходов (transitions.py)

```
IDLE:
  key_press      → TYPING
  shift_down     → SHIFT_PRESSED     (SelectionMode из IDLE)

TYPING:
  shift_down     → SHIFT_PRESSED
  backspace_hold → BACKSPACE_HOLD
  navigation     → IDLE
  mouse_click    → IDLE
  enter          → IDLE

SHIFT_PRESSED:
  shift_up_single  → TYPING           (один Shift — вернулись к набору)
  shift_up_double  → CONVERTING       (двойной Shift — конвертация!)
  key_press        → TYPING           (нажали другую клавишу — отмена)

BACKSPACE_HOLD:
  key_press        → TYPING
  shift_up_double  → CONVERTING       (двойной Shift после удержания BS)
  navigation       → IDLE
  mouse_click      → IDLE

CONVERTING:
  complete  → IDLE
  cancelled → IDLE
```

#### 4.3. StateContext

```python
@dataclass
class StateContext:
    state: State = State.IDLE
    text_buffer: list[str]     # не используется в текущем коде
    event_buffer: list         # основной буфер нажатий
    chars_in_buffer: int = 0   # счётчик символов
    last_shift_time: float     # время последнего Shift release
    backspace_hold_at: float   # время начала удержания BS
    shift_pressed: bool        # Shift сейчас зажат?
    backspace_repeats: int     # счётчик авто-повторов BS
    backspace_hold_active: bool # BS hold активен?
    current_layout: str = "en" # не используется (раскладка из XKB)
```

#### 4.4. Диаграмма переходов

```
                          key_press
              ┌──────────────────────────────────┐
              │                                  │
              ▼          shift_down               │
           ┌──────┐  ──────────────► ┌───────────────┐
           │ IDLE │                  │ SHIFT_PRESSED │
           └──────┘  ◄────────────── └───────────────┘
              ▲      shift_up_single       │
              │                            │ shift_up_double
              │      key_press             ▼
              │  ┌──────────► ┌────────────────┐
              │  │            │  CONVERTING    │
              │  │            └────────────────┘
              │  │                  │ complete/cancelled
     nav/mouse│  │                 │
     click    │  │                 │
              │  │                 ▼
           ┌──────┐  ◄────────── IDLE
           │TYPING│
           └──────┘
              │
              │ backspace_hold (3+ repeats)
              ▼
           ┌───────────────┐
           │ BACKSPACE_HOLD│──── shift_up_double ──► CONVERTING
           └───────────────┘
```

---

### 5. Event System

#### 5.1. EventBus (`lswitch/core/event_bus.py`)

Лёгкий синхронный pub/sub:

```python
class EventBus:
    subscribe(event_type, handler)   # подписка
    unsubscribe(event_type, handler) # отписка
    publish(event)                   # вызвать всех подписчиков синхронно
```

Все handlers вызываются **синхронно** в том же потоке. Исключения ловятся и логируются.

#### 5.2. EventType (`lswitch/core/events.py`)

```python
class EventType(Enum):
    KEY_PRESS           # Нажатие клавиши
    KEY_RELEASE         # Отпускание клавиши
    KEY_REPEAT          # Авто-повтор (зажатая клавиша)
    DOUBLE_SHIFT        # Двойной Shift (не используется для dispatch, обрабатывается в on_shift_up)
    BACKSPACE_HOLD      # Удержание Backspace
    MOUSE_CLICK         # Клик мышью (button press, value=1)
    MOUSE_RELEASE       # Отпускание кнопки мыши (button release, value=0)
    CONVERSION_START    # Начало конвертации
    CONVERSION_COMPLETE # Конвертация завершена
    CONVERSION_CANCELLED # Конвертация отменена
    LAYOUT_CHANGED      # Раскладка изменилась
    CONFIG_CHANGED      # Конфигурация изменена
    APP_QUIT            # Завершение приложения
```

#### 5.3. EventManager (`lswitch/core/event_manager.py`)

**Принимает** сырые evdev события → **классифицирует** → **публикует** типизированные события в EventBus.

```
evdev event (type=EV_KEY) → EventManager.handle_raw_event()
    │
    ├── code ∈ MOUSE_BUTTONS:
    │   ├── value==1 → publish(MOUSE_CLICK)
    │   └── value==0 → publish(MOUSE_RELEASE)
    ├── value == 1 (press)              → publish(KEY_PRESS)
    ├── value == 0 (release)            → publish(KEY_RELEASE)
    └── value == 2 (repeat)             → publish(KEY_REPEAT)
```

#### 5.4. Подписки в app.py (`_wire_event_bus`)

```python
EventType.KEY_PRESS     → _on_key_press
EventType.KEY_RELEASE   → _on_key_release
EventType.KEY_REPEAT    → _on_key_repeat
EventType.MOUSE_CLICK   → _on_mouse_click
EventType.MOUSE_RELEASE → _on_mouse_release
```

#### 5.5. Цепочка обработки evdev события

```
evdev device → DeviceManager.get_events() → (device, event)
    → EventManager.handle_raw_event(event, device.name)
        → EventBus.publish(Event(KEY_PRESS/KEY_RELEASE/KEY_REPEAT/MOUSE_CLICK/MOUSE_RELEASE, data, ts))
            → LSwitchApp._on_key_press / _on_key_release / _on_key_repeat / _on_mouse_click / _on_mouse_release
                → StateManager transitions
                    → ConversionEngine.convert() (при CONVERTING)
                        → RetypeMode / SelectionMode

Параллельно:
_SelectionLoggerThread (polling 500ms):
    → get_selection() → сравнение с предыдущим
        → если изменилось → callback _on_poller_primary_changed → _selection_valid = True
```

---

### 6. Автоматическое переключение

#### 6.1. AutoDetector (`lswitch/intelligence/auto_detector.py`)

Решает, нужно ли конвертировать слово автоматически при пробеле.

**Цепочка приоритетов:**

```
1. Слово уже правильное в текущей раскладке (словарь) → НЕ конвертировать
2. UserDictionary.is_protected() → НЕ конвертировать (временная защита)
3. UserDictionary.get_weight() ≤ -min_weight → НЕ конвертировать (пользователь отменял)
4. Конвертированное слово найдено в словаре целевой раскладки → КОНВЕРТИРОВАТЬ
5. N-gram score целевого языка значительно лучше → КОНВЕРТИРОВАТЬ
6. N-gram score исходного = 0 и длина слова ≥ 4 → КОНВЕРТИРОВАТЬ
7. Иначе → НЕ конвертировать
```

#### 6.2. DictionaryService (`lswitch/intelligence/dictionary_service.py`)

Лениво загружает множества слов `RUSSIAN_WORDS` и `ENGLISH_WORDS`.

```python
should_convert("ghbdtn", "en"):
    1. "ghbdtn" в ENGLISH_WORDS? → Нет
    2. convert("ghbdtn") → "привет". "привет" в RUSSIAN_WORDS? → Да!
    → (True, "converted to Russian word 'привет'")
```

#### 6.3. NgramAnalyzer (`lswitch/intelligence/ngram_analyzer.py`)

Биграмный/триграмный анализ. Score = среднее значение частот биграмм + триграмм*3.

#### 6.4. UserDictionary (`lswitch/intelligence/user_dictionary.py`)

Самообучающийся словарь:

- **add_confirmation(word, lang):** вес +1 (слово конвертировалось правильно)
- **add_correction(word, lang):** вес -1 + временная защита (5 секунд)
- **is_protected(word, lang):** временная защита от авто-конвертации
- **get_weight(word, lang):** текущий вес слова

Хранение: `~/.config/lswitch/user_dict.json`

#### 6.5. Авто-конвертация при пробеле (`_try_auto_conversion_at_space`)

**Алгоритм:**

```
1. Проверить chars_in_buffer > 0
2. Проверить порог (auto_switch_threshold)
3. Получить текущую раскладку через XKB
4. Извлечь последнее слово из event_buffer (_extract_last_word_events)
5. Спросить AutoDetector.should_convert(word, current_lang)
6. Если предыдущая авто-конвертация была принята → user_dict +1
7. Если should → выполнить _do_auto_conversion_at_space()
```

**`_do_auto_conversion_at_space`:**
```
1. Удалить word_len+1 символов (слово + пробел, который уже попал в приложение)
2. Переключить раскладку
3. Воспроизвести оригинальные keycodes (в новой раскладке = конвертированный текст)
4. Добавить пробел
5. Сохранить _last_auto_marker для возможной отмены
6. Сбросить контекст (reset + IDLE)
```

#### 6.6. `_last_auto_marker`

Маркер последней авто-конвертации:
```python
{'word': 'ghbdtn', 'direction': 'en_to_ru', 'lang': 'en', 'time': 1234567890.0}
```

**Используется для:**
- Если после авто-конвертации пользователь сразу нажал Shift+Shift → это ОТМЕНА → `user_dict.add_correction()`
- Если продолжил печатать до следующего пробела → авто-конвертация принята → `user_dict.add_confirmation()`

#### 6.7. `_extract_last_word_events`

Сканирует `event_buffer` с конца до пробела или не-буквенного символа. Использует реальное XKB mapping для определения символов (важно для RU раскладки, где `,` → `б`, `.` → `ю`).

---

### 7. Флаг `_selection_valid` (fresh)

#### 7.1. Назначение

Указывает, есть ли **свежее** выделение текста, которое можно использовать для SelectionMode. Реализован как property с setter-логированием.

#### 7.2. Установка в True (два источника)

**1. `_on_mouse_release`** — при отпускании кнопки мыши:
```python
# Читает PRIMARY (безопасно — GTK закончила обработку release)
info = self.selection.get_selection()
# Сравнивает с baseline (_prev_sel_text / _prev_sel_owner_id)
if info.text and (info.text != old_text or owner changed):
    self._selection_valid = True
```
Покрывает **быстрый drag-select** (< 500ms), который поллер не успевает поймать.

**2. `_on_poller_primary_changed`** — callback от `_SelectionLoggerThread` (каждые 500ms):
```python
self._selection_valid = True
# НЕ обновляет baseline! Baseline трогает только mouse_release и _do_conversion.
```
Покрывает **клавиатурное выделение** (Shift+стрелки) и **медленный drag-select**.

#### 7.3. Сброс в False

| Место | Когда |
|-------|-------|
| `_on_key_press` | Обычный символ, Backspace, Space |
| `_on_key_release` | Navigation (стрелки, Home/End/PgUp/PgDn), Enter |
| `_on_mouse_click` | Любой клик мыши (button press) |
| `_do_conversion` finally | После конвертации (consumed) |

**Ключевой инвариант:** клик мыши **всегда** сбрасывает fresh. Поэтому стale PRIMARY из другого окна не конвертируется: поллер ставит True → клик сбрасывает → Shift+Shift видит False.

#### 7.4. Baseline (`_prev_sel_text`, `_prev_sel_owner_id`)

Baseline — запомненное состояние PRIMARY для сравнения. Обновляется **только** в двух местах:

| Место | Когда |
|-------|-------|
| `_on_mouse_release` | Всегда (независимо от fresh) |
| `_do_conversion` finally | После конвертации (чтобы следующий Shift+Shift не считал результат за новое выделение) |

Поллер (`_on_poller_primary_changed`) **НЕ обновляет baseline** — это принципиально: иначе mouse_release не увидит разницу.

#### 7.5. Как используется

```python
# В _do_conversion (метод _check_selection_changed удалён):
success = self.conversion_engine.convert(
    context, selection_valid=self._selection_valid
)

# choose_mode проверяет:
if context.chars_in_buffer > 0:  return "retype"    # приоритет!
if selection_valid:              return "selection"
```

#### 7.6. Property setter с логированием

```python
@_selection_valid.setter
def _selection_valid(self, value: bool) -> None:
    if value != self.__selection_valid:
        logger.debug("fresh=%s → %s", self.__selection_valid, value)
        self.__selection_valid = value
    if logger.isEnabledFor(5):  # TRACE = 5 (guard от overhead extract_stack)
        caller = traceback.extract_stack(limit=3)[-2]
        logger.trace("fresh=%s (set by %s:%d)", self.__selection_valid, caller.name, caller.lineno)
```

---

### 8. _on_mouse_click и _on_mouse_release

#### 8.1. `_on_mouse_click` (button press)

```python
def _on_mouse_click(self, event):
    self._last_auto_marker = None       # сброс маркера авто-конвертации
    self._selection_valid = False        # сброс флага выделения
    self._last_retype_events = []       # сброс sticky buffer
    # НЕ читаем PRIMARY здесь! xclip -o отправляет XConvertSelection,
    # что может заставить GTK-приложение сбросить PRIMARY (race condition).
    # Baseline обновляется в _on_mouse_release.
    self.state_manager.on_mouse_click()  # state → IDLE, context.reset()
```

**Ключевое изменение:** PRIMARY **НЕ читается** при клике. Это устраняет race condition с GTK/Cinnamon, когда `xclip -o` при клике сбрасывает PRIMARY.

#### 8.2. `_on_mouse_release` (button release)

```python
def _on_mouse_release(self, event):
    if self.selection is None:
        return
    try:
        info = self.selection.get_selection()    # безопасно — GTK закончила
        old_text = self._prev_sel_text
        old_owner = self._prev_sel_owner_id
        # Всегда обновляем baseline
        self._prev_sel_text = info.text or ""
        self._prev_sel_owner_id = info.owner_id
        # Если PRIMARY изменился → свежее выделение (drag-select)
        if info.text and (info.text != old_text or
                          (info.owner_id != old_owner and info.owner_id != 0)):
            self._selection_valid = True
    except Exception:
        pass
```

**Почему release безопасен:** к моменту отпускания кнопки GTK-приложение уже обработало событие и зафиксировало выделение в PRIMARY. Race condition не возникает.

#### 8.3. Цепочка click → release

```
Button press → _on_mouse_click:
    fresh = False, sticky = [], auto_marker = None
    State → IDLE

Drag (пользователь тянет мышь, выделяя текст)

Button release → _on_mouse_release:
    Читает PRIMARY → сравнивает с baseline
    Если текст изменился → fresh = True
    Всегда обновляет baseline
```

#### 8.4. Сценарии

| Сценарий | click | release | fresh |
|----------|-------|---------|-------|
| Простой клик (без drag) | False | PRIMARY не изменился → нет | False |
| Drag-select | False | PRIMARY изменился → True | True |
| Клик в другом окне | False | PRIMARY тот же → нет | False |

---

### 9. Практические примеры

#### Пример 1: Пользователь набирает "ghbdtn", нажимает Shift+Shift

Пользователь на **EN** раскладке набирает клавиши, которые в RU дают "привет": `g-h-b-d-t-n` → в текстовом поле `ghbdtn`. Нажимает Shift+Shift.

Пошаговый сценарий для "ghbdtn" → "привет":

```
Шаг  Событие                        Состояние      event_buffer    chars
1    Key press: g (code=34)         IDLE→TYPING    [g]             1
2    Key press: h (code=35)         TYPING         [g,h]           2
3    Key press: b (code=48)         TYPING         [g,h,b]         3
4    Key press: d (code=32)         TYPING         [g,h,b,d]       4
5    Key press: t (code=20)         TYPING         [g,h,b,d,t]     5
6    Key press: n (code=49)         TYPING         [g,h,b,d,t,n]   6
7    Shift press (code=42)          TYPING→SHIFT_P [g,h,b,d,t,n]   6
8    Shift release (code=42)        SHIFT_P→TYPING last_shift_time=T₁
9    Shift press (code=54)          TYPING→SHIFT_P
10   Shift release (code=54)        delta < 0.3s → SHIFT_P→CONVERTING
                                    → _do_conversion()
```

**_do_conversion:**
```
1. State == CONVERTING ✓
2. selection_valid = False (не было drag-select или поллера)
3. saved_events = [g,h,b,d,t,n], saved_count = 6
4. _last_retype_events пуст → не восстанавливаем
5. conversion_engine.convert(context, selection_valid=False)
6. choose_mode: chars_in_buffer=6 > 0 → "retype"
```

**RetypeMode.execute:**
```
1. chars_in_buffer = 6 ✓
2. Отправить 6 backspace → "ghbdtn" удаляется из текстового поля
3. switch_layout() → EN → RU (через Cinnamon D-Bus или XkbLockGroup)
4. Пауза 50мс
5. replay_events([g,h,b,d,t,n]) → нажатия g,h,b,d,t,n теперь в RU раскладке
   g → п, h → р, b → и, d → в, t → е, n → т → "привет"
```

**Результат:** "ghbdtn" заменено на "привет", раскладка переключена на RU.

**After:** `_last_retype_events = [g,h,b,d,t,n]`, context.reset(), state → IDLE.

#### Пример 2: Пользователь выделяет текст, нажимает Shift+Shift

**Предусловие:** пользователь выделил мышью слово "ghbdtn" в текстовом поле.

```
Шаг  Событие                        Состояние
1    Mouse click (button press)      IDLE, fresh=False
2    Mouse drag (выделение)          Пользователь тянет мышь
                                     PRIMARY = "ghbdtn", owner изменился
3    Mouse release (button release)  _on_mouse_release:
                                     PRIMARY изменился → fresh=True
                                     baseline обновлён
4    Shift press                     IDLE→SHIFT_PRESSED
     (chars_in_buffer == 0, event_buffer пуст)
5    Shift release                   last_shift_time = T₁
6    Shift press                     (уже в SHIFT_PRESSED)
7    Shift release                   delta < 0.3s → SHIFT_P→CONVERTING
                                     → _do_conversion()
```

**_do_conversion:**
```
1. State == CONVERTING ✓
2. selection_valid = True (установлено mouse_release)
3. saved_count = 0, _last_retype_events пуст
4. conversion_engine.convert(context, selection_valid=True)
5. choose_mode: chars_in_buffer=0, selection_valid=True → "selection"
```

**SelectionMode.execute:**
```
1. get_selection() → text="ghbdtn"
2. detect_language("ghbdtn") → "en" (нет кириллицы)
3. direction = "en_to_ru"
4. convert_text("ghbdtn", "en_to_ru") → "привет"
5. replace_selection("привет"):
   a. Сохранить CLIPBOARD
   b. CLIPBOARD = "привет"
   c. xdotool Ctrl+V → вставляет "привет" вместо выделения
   d. Восстановить CLIPBOARD
6. switch_layout → RU
```

#### Пример 3: Повторный Shift+Shift (sticky buffer)

```
Шаг  Событие                        Прим.
1    Набрал "ghbdtn"                 event_buffer = [g,h,b,d,t,n], chars=6
2    Shift+Shift                     → retype → "привет"
                                     _last_retype_events = [g,h,b,d,t,n]
                                     context.reset() → event_buffer=[], chars=0
3    Shift+Shift (сразу, без нового ввода)
     → _do_conversion()
     saved_count = 0, _last_retype_events не пуст!
     → восстановить event_buffer из _last_retype_events
     → chars_in_buffer = 6
     → choose_mode → "retype"
     → RetypeMode: удалить 6 символов, switch_layout (RU→EN), replay
     → "привет" обратно в "ghbdtn"
     → _last_retype_events = [g,h,b,d,t,n] (снова сохранён)
```

**Результат:** каждый повторный Shift+Shift чередует "ghbdtn" ↔ "привет".

#### Пример 4: Авто-конвертация при пробеле

**Предусловие:** раскладка EN, `auto_switch = true`.

```
Шаг  Событие                        Прим.
1    Набрал "ghbdtn"                 event_buffer = [g,h,b,d,t,n], chars=6
2    Space press:
     → _try_auto_conversion_at_space()
     → current_lang = "en"
     → _extract_last_word_events() → word="ghbdtn", events=[g,h,b,d,t,n]
     → AutoDetector.should_convert("ghbdtn", "en"):
       a. "ghbdtn" in ENGLISH_WORDS? → Нет
       b. convert → "привет". "привет" in RUSSIAN_WORDS? → Да!
       → (True, "converted to Russian word 'привет'")
     → _do_auto_conversion_at_space(6, [...], "en_to_ru"):
       a. tap_key(BACKSPACE, 7)  — 6 символов + 1 пробел (уже попал в приложение)
       b. switch_layout(target=ru)
       c. replay_events([g,h,b,d,t,n]) → "привет" (в RU раскладке)
       d. tap_key(SPACE) → добавить пробел
       e. _last_auto_marker = {word:"ghbdtn", lang:"en", ...}
       f. context.reset(), state = IDLE
```

**Если потом Shift+Shift (отмена):**
```
_last_auto_marker != None → user_dict.add_correction("ghbdtn", "en") → weight -1
```

---

## Часть 2: Проблема PRIMARY буфера в Linux Mint (Cinnamon)

---

### Описание проблемы

**Нативное поведение Linux Mint (Cinnamon):**
- Пользователь выделяет текст → текст попадает в PRIMARY
- Пользователь кликает мышью (снимает выделение) → PRIMARY **НЕ очищается**
- Текст всё ещё можно вставить средней кнопкой мыши
- PRIMARY обновляется только при **новом** выделении

**Поведение с LSwitch:**
- Пользователь выделяет текст → PRIMARY = "текст"
- Пользователь кликает мышью → **PRIMARY очищается** ← БАГО
- Средняя кнопка мыши не вставляет ничего

---

### Анализ кода

#### 1. `_on_mouse_click` в app.py

```python
def _on_mouse_click(self, event):
    self._last_auto_marker = None
    self._selection_valid = False
    self._last_retype_events = []
    if self.selection is not None:
        try:
            info = self.selection.get_selection()        # ← ЧТЕНИЕ PRIMARY
            self._prev_sel_text = info.text
            self._prev_sel_owner_id = info.owner_id
        except Exception:
            pass
    self.state_manager.on_mouse_click()
```

**Вызов `get_selection()` при каждом клике мыши.**

#### 2. `X11SelectionAdapter.get_selection()`

```python
def get_selection(self) -> SelectionInfo:
    text = self._system.get_clipboard(selection="primary")     # xclip -o -selection primary
    owner_id = _get_selection_owner_id()                       # Xlib PRIMARY owner
    return SelectionInfo(text=text, owner_id=owner_id, timestamp=time.time())
```

**Вызывает `xclip -o -selection primary`.**

#### 3. `SubprocessSystemAdapter.get_clipboard()`

```python
def get_clipboard(self, selection: str = "primary") -> str:
    result = self.run_command(
        ["xclip", "-o", "-selection", selection], timeout=0.3
    )
    return result.stdout
```

Просто запускает `xclip -o -selection primary`.

#### 4. `SelectionMode.execute()`

```python
sel = self.selection.get_selection()    # чтение PRIMARY
...
self.selection.replace_selection(converted)  # запись через CLIPBOARD + Ctrl+V
```

#### 5. `replace_selection()`

```python
def replace_selection(self, new_text: str) -> bool:
    old_clip = self._system.get_clipboard(selection="clipboard")      # сохранить CLIPBOARD
    self._system.set_clipboard(new_text, selection="clipboard")       # записать в CLIPBOARD
    self._system.xdotool_key("ctrl+v")                                # Ctrl+V
    if old_clip is not None:
        self._system.set_clipboard(old_clip, selection="clipboard")   # восстановить CLIPBOARD
```

**ВАЖНО:** `replace_selection` НЕ трогает PRIMARY. Она работает через CLIPBOARD.

---

### Корневая причина проблемы

#### Проблема НЕ в `_on_mouse_click` напрямую

Метод `_on_mouse_click` только **читает** PRIMARY через `xclip -o`. Сам `xclip -o` не модифицирует PRIMARY.

Однако, `_get_selection_owner_id()` использует Xlib:

```python
def _get_selection_owner_id() -> int:
    try:
        from Xlib import display as xdisplay, Xatom, X
        d = xdisplay.Display()                         # открывает новое соединение!
        owner = d.get_selection_owner(Xatom.PRIMARY)
        owner_id = owner.id if owner and owner != X.NONE else 0
        d.close()                                      # закрывает соединение
        return owner_id
    except Exception:
        return 0
```

**Это открывает и закрывает X11 Display соединение при КАЖДОМ вызове.** Но это тоже только чтение.

#### Настоящая причина: `xclip -o` при пустом выделении

Проблема связана с поведением `xclip` в Cinnamon/X11:

1. В Cinnamon при клике мышью (отмена выделения) **owner PRIMARY не меняется** — предыдущее окно остаётся владельцем PRIMARY selection.
2. Но **LSwitch вызывает `xclip -o -selection primary` при каждом клике** (`_on_mouse_click` → `get_selection()`).
3. `xclip -o` выполняет **ConvertSelection** запрос к X серверу, что может побудить приложение-владелец PRIMARY обновить/сбросить содержимое selection.
4. Некоторые X11 приложения (особенно на GTK) при получении SelectionRequest после снятия выделения **отвечают пустой строкой или теряют владение PRIMARY**.

**Конкретный механизм:**

Когда `xclip -o -selection primary` выполняется **сразу после клика мыши** (который снял выделение):
- xclip отправляет `XConvertSelection` request для PRIMARY
- Приложение-владелец получает `SelectionRequest`
- Если выделение уже снято (пользователь только что кликнул), приложение **может ответить пустыми данными** или **отказаться от владения** (XSetSelectionOwner(None))
- Это "забирает" PRIMARY навсегда, пока не будет нового выделения

**Это race condition:** LSwitch вызывает `xclip -o` слишком рано после клика, когда приложение ещё обрабатывает событие снятия выделения.

#### Места чтения PRIMARY (актуальные)

| Метод | Файл | Когда |
|-------|------|-------|
| `_on_mouse_release` | app.py | Отпускание кнопки мыши (button release) |
| `_SelectionLoggerThread.run` | app.py | Поллинг каждые 500ms (фоновый поток) |
| `_do_conversion` finally | app.py | После конвертации (обновление baseline) |
| `SelectionMode.execute` | modes.py | При конвертации выделения |

**Убрано:** `_on_mouse_click` больше НЕ читает PRIMARY (устранён race condition).

---

### Реализованное решение

Архитектура была переработана: PRIMARY больше **НЕ читается при клике мыши**. Вместо одного метода `_check_selection_changed()` теперь два независимых источника fresh-флага.

#### Архитектура: два источника + сброс

```
┌─────────────────────────────────────────────────────────┐
│               fresh = True (готово к SelectionMode)     │
│                                                         │
│  Источник 1: _on_mouse_release                          │
│    → Читает PRIMARY при отпускании кнопки мыши          │
│    → Сравнивает с baseline → если изменился → True       │
│    → Всегда обновляет baseline                          │
│    → Покрывает: drag-select (любая скорость)            │
│                                                         │
│  Источник 2: _on_poller_primary_changed (каждые 500ms)  │
│    → Только ставит True, НЕ трогает baseline            │
│    → Покрывает: Shift+стрелки, медленный drag-select    │
├─────────────────────────────────────────────────────────┤
│               fresh = False (сброс)                     │
│                                                         │
│  - _on_mouse_click (кнопка нажата)                      │
│  - _on_key_press (символ, Backspace, Space)             │
│  - _on_key_release (Navigation, Enter)                  │
│  - _do_conversion finally (после конвертации)           │
├─────────────────────────────────────────────────────────┤
│               Baseline обновляется                      │
│                                                         │
│  - _on_mouse_release (всегда)                           │
│  - _do_conversion finally (после конвертации)           │
│  - Поллер НЕ обновляет baseline!                        │
└─────────────────────────────────────────────────────────┘
```

#### Что было удалено

- **`_check_selection_changed()`** — метод полностью удалён. Его роль разделена между `_on_mouse_release` и поллером.
- **`_mouse_clicked_since_last_check`** — промежуточный флаг больше не нужен.
- **Чтение PRIMARY в `_on_mouse_click`** — убрано (устраняет race condition с GTK).

#### Что было добавлено

- **`MOUSE_RELEASE`** — новый EventType в events.py.
- **`_on_mouse_release`** — обработчик, читает PRIMARY при отпускании кнопки.
- **`_SelectionLoggerThread`** — фоновый daemon-поток, поллит PRIMARY каждые 500ms.
- **Baseline update в `_do_conversion` finally** — предотвращает повторную конвертацию того же текста.
- **Property setter для `_selection_valid`** — логирует изменения (DEBUG) и каждое присвоение (TRACE с guard'ом).

#### Проверка сценариев

| Сценарий | Результат |
|----------|-----------|
| **Cross-window stale:** выделил в A → поллер True → кликнул в B → False → Shift+Shift | ✅ НЕ конвертирует (fresh=False) |
| **Drag-select быстрый (<500ms):** клик → тянет → отпустил | ✅ mouse_release → fresh=True |
| **Drag-select медленный (>500ms):** клик → тянет → поллер + release | ✅ fresh=True от обоих источников |
| **Клавиатурное выделение (Shift+стрелки):** | ✅ поллер → fresh=True (с задержкой ≤500ms) |
| **Простой клик (без drag):** | ✅ fresh=False (PRIMARY не изменился) |
| **Повторный Shift+Shift (sticky retype):** | ✅ _last_retype_events восстанавливает буфер |
| **Повторный Shift+Shift (selection):** | ✅ поллер видит изменение PRIMARY → fresh=True (задержка ≤500ms) |

#### Почему поллер НЕ обновляет baseline

Если бы поллер обновлял baseline, то к моменту `_on_mouse_release` baseline уже совпадал бы с PRIMARY → mouse_release не увидел бы разницу → быстрый drag-select (<500ms) не обнаруживался бы.

Без обновления baseline поллером, mouse_release всегда видит актуальную разницу между «до клика» и «после drag-select».

---

## Приложения

### A. Полная карта файлов проекта

| Файл | Назначение |
|------|------------|
| `lswitch/app.py` | Главный класс приложения, координатор |
| `lswitch/core/conversion_engine.py` | Выбор режима и запуск конвертации |
| `lswitch/core/modes.py` | RetypeMode + SelectionMode |
| `lswitch/core/state_manager.py` | Автомат состояний |
| `lswitch/core/states.py` | State enum + StateContext dataclass |
| `lswitch/core/transitions.py` | Таблица переходов |
| `lswitch/core/event_bus.py` | Pub/sub шина событий |
| `lswitch/core/event_manager.py` | evdev → typed EventBus events |
| `lswitch/core/events.py` | Типы событий |
| `lswitch/core/text_converter.py` | Чистая посимвольная конвертация |
| `lswitch/platform/selection_adapter.py` | X11 PRIMARY selection |
| `lswitch/platform/xkb_adapter.py` | XKB раскладки через libX11 |
| `lswitch/platform/system_adapter.py` | Интерфейс для subprocess |
| `lswitch/platform/subprocess_impl.py` | xclip, xdotool обёртки |
| `lswitch/input/device_manager.py` | evdev устройства + hot-plug |
| `lswitch/input/device_filter.py` | Фильтрация виртуальных устройств |
| `lswitch/input/virtual_keyboard.py` | UInput виртуальная клавиатура |
| `lswitch/input/key_mapper.py` | keycode → char |
| `lswitch/input/udev_monitor.py` | udev мониторинг hot-plug |
| `lswitch/intelligence/auto_detector.py` | Авто-определение языка |
| `lswitch/intelligence/dictionary_service.py` | Словари EN/RU |
| `lswitch/intelligence/ngram_analyzer.py` | Биграммы/триграммы |
| `lswitch/intelligence/user_dictionary.py` | Самообучение |
| `lswitch/intelligence/maps.py` | EN↔RU таблицы перекодировки |
| `lswitch/intelligence/persistence.py` | Атомарное сохранение JSON |

### B. Потоковая модель

```
Main thread:
  ├── QApplication.exec_() (если GUI)
  └── Qt event loop

evdev-loop thread (daemon):
  ├── DeviceManager.get_events(timeout=0.1)
  ├── EventManager.handle_raw_event()
  ├── EventBus.publish() → все обработчики синхронно
  ├── StateManager transitions
  └── ConversionEngine (retype/selection) — тоже в этом потоке

_SelectionLoggerThread "sel-logger" (daemon):
  ├── Polling get_selection() каждые 500ms
  ├── Сравнивает text + owner_id с предыдущими значениями
  ├── При изменении → callback _on_poller_primary_changed(text, owner_id)
  └── НЕ обновляет app baseline (только свой внутренний _prev_text/_prev_owner_id)

UdevMonitor thread (daemon):
  └── pyudev polling → on_added/on_removed callbacks
```

**Важно:** все EventBus handlers работают в evdev-loop потоке. ConversionEngine (включая xdotool_key, xclip) тоже вызывается из этого потока. `_on_poller_primary_changed` вызывается из sel-logger потока, но `_selection_valid` — простой bool (atomic в CPython GIL), поэтому thread-safe.
