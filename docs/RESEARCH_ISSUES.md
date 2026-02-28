# Исследование: Проблемы и доработки LSwitch

## Задача 1: Space в event_buffer блокирует Shift+Shift

### Анализ текущего поведения

#### Сценарий: пользователь набирает "hello ghbdtn ", autodetector говорит "нет", затем Shift+Shift

**Шаг 1. Набор текста "hello ghbdtn"**

При нажатии каждой буквенной клавиши в `_on_key_press()` ([app.py](lswitch/app.py#L275-L288)):
- `state_manager.on_key_press(data.code)` — переход в состояние `TYPING`
- `event_buffer.append(data)` — событие добавляется в буфер
- `chars_in_buffer += 1`

После набора "hello" буфер содержит 5 событий: `[h, e, l, l, o]`.

**Шаг 2. Нажатие Space после "hello"**

Обработка Space в `_on_key_press()` ([app.py](lswitch/app.py#L256-L272)):

```python
elif data.code == KEY_SPACE:
    if self.auto_detector and self.config.get('auto_switch'):
        if self._try_auto_conversion_at_space():
            return  # space was consumed by auto-conversion
    # Normal space: add to buffer
    self.state_manager.on_key_press(data.code)
    self.state_manager.context.chars_in_buffer += 1
    data.shifted = self.state_manager.context.shift_pressed
    self.state_manager.context.event_buffer.append(data)
```

`_try_auto_conversion_at_space()` ([app.py](lswitch/app.py#L547-L620)) извлекает слово "hello", вызывает `auto_detector.should_convert("hello", "en")` → возвращает `(False, ...)` → метод возвращает `False`.

Поскольку auto-conversion не сработала, **Space добавляется в event_buffer как обычное событие**. Буфер теперь: `[h, e, l, l, o, SPACE]`, `chars_in_buffer = 6`.

**Шаг 3. Набор "ghbdtn" и ещё один Space**

Буфер растёт: `[h, e, l, l, o, SPACE, g, h, b, d, t, n]`, `chars_in_buffer = 12`.

Набираем Space. `_try_auto_conversion_at_space()` извлекает слово перед пробелом — "ghbdtn" (метод `_extract_last_word_events` сканирует с конца буфера до `KEY_SPACE`). Допустим, autodetector опять говорит "нет" (или "ghbdtn" не распознаётся). Пробел добавляется в буфер.

Буфер теперь: `[h, e, l, l, o, SPACE, g, h, b, d, t, n, SPACE]`, `chars_in_buffer = 13`.

**Шаг 4. Пользователь нажимает Shift+Shift**

1. `_on_key_release()` ([app.py](lswitch/app.py#L295-L307)) распознаёт double-shift → вызывает `_do_conversion()`.
2. `state_manager.on_shift_up()` ([state_manager.py](lswitch/core/state_manager.py#L44-L57)) возвращает `True` → состояние переходит в `CONVERTING`.

3. В `_do_conversion()` ([app.py](lswitch/app.py#L425-L545)):

   a) **Извлечение слова для user_dict (строки 448-453):**
   ```python
   manual_word, _ = self._extract_last_word_events(layout_info)
   ```
   `_extract_last_word_events` сканирует с конца буфера: первый элемент — `KEY_SPACE` → **немедленный `break`** → возвращает `("", [])`.
   Значит `manual_word = ""` — словарь не обновляется (не критично для конвертации).

   b) **Сохранение буфера (строки 481-490):**
   ```python
   saved_events = list(self.state_manager.context.event_buffer)  # 13 событий
   saved_count = self.state_manager.context.chars_in_buffer       # 13
   ```

   c) **Trim to last word (строки 492-511):** ← ЗДЕСЬ ПРОБЛЕМА
   ```python
   if saved_count > 0 and not self._selection_valid:
       _, last_word_events = self._extract_last_word_events(...)
   ```
   `_extract_last_word_events` опять сканирует с конца → первый элемент `KEY_SPACE` → `break` → возвращает `("", [])`.

   `last_word_events = []` → условие `if last_word_events and ...` **ложно** (пустой список).

   **Trim не срабатывает.** Буфер остаётся `saved_count = 13`.

   d) **Вызов `convert()`** ([conversion_engine.py](lswitch/core/conversion_engine.py#L73-L83)):
   `choose_mode()` → `chars_in_buffer = 13 > 0` → режим `"retype"`.

   e) **`RetypeMode.execute()`** ([modes.py](lswitch/core/modes.py#L62-L115)):
   - Удаляет 13 символов backspace (включая пробелы!)
   - Переключает раскладку
   - Replay 13 событий (включая 2 `KEY_SPACE`) в новой раскладке

   **Результат:** Retype отправляет 13 backspace и затем replay всех 13 событий. Это **удалит** текст за пределами набранного слова если пользователь набирал что-то до "hello ghbdtn " в том же приложении. Кроме того, пробелы повторяются в новой раскладке как есть — это корректно, но удаляется ВЕСЬ буфер, а не только последнее слово.

**Однако**, если сценарий проще — буфер `[g, h, b, d, t, n, SPACE]` (7 событий) и пользователь нажал Shift+Shift:
- Trim пытается извлечь последнее слово → `("", [])` (trailing space)
- Trim не срабатывает (пустой `last_word_events`)
- Retype удаляет 7 символов и replay 7 событий (включая SPACE)
- Это **работает**, но конвертирует пробел вместе со словом

**Критический случай**: если в буфере ТОЛЬКО пробел `[SPACE]`, `chars_in_buffer = 1`:
- Trim: `("", [])` → не обрезает
- `RetypeMode.execute()`: `chars_in_buffer = 1 > 0` → удаляет 1 символ, переключает раскладку, replay 1 событие (SPACE)
- Результат: пробел удаляется и вставляется заново. Бесполезно, но не ломается.

### Корневая причина

Метод `_extract_last_word_events()` ([app.py](lswitch/app.py#L621-L668)) при обратном сканировании буфера **немедленно останавливается** на `KEY_SPACE`:

```python
for ev in reversed(self.state_manager.context.event_buffer):
    if ev.code == KEY_SPACE:
        break            # ← СТОП на первом же пробеле
    ...
```

Если последний элемент буфера — `KEY_SPACE` (trailing space), метод возвращает пустую строку и пустой список, **не дойдя до реального слова**.

Это создаёт **две проблемы**:

1. **Trim-to-last-word в `_do_conversion()`** (строки 498-510): `_extract_last_word_events()` возвращает `[]` → trim не срабатывает → retype обрабатывает весь буфер (включая несколько слов и пробелы), что приводит к удалению лишнего текста из приложения.

2. **User-dict learning** (строка 451): `manual_word` пуст → `add_confirmation()` не вызывается, пользовательский словарь не обновляется при ручной конвертации после пробела.

### Варианты решения

#### Вариант A: Пропускать trailing spaces в `_extract_last_word_events()`

**Описание:** Модифицировать `_extract_last_word_events()` — перед началом основного цикла сканирования пропускать все `KEY_SPACE` с конца буфера.

```python
def _extract_last_word_events(self, current_layout=None):
    ...
    word_events = []
    chars = []
    skipping_trailing_spaces = True
    for ev in reversed(self.state_manager.context.event_buffer):
        if ev.code == KEY_SPACE:
            if skipping_trailing_spaces:
                continue   # пропускаем trailing пробелы
            else:
                break      # пробел внутри текста = граница слова
        skipping_trailing_spaces = False
        # ... остальная логика без изменений
```

**Плюсы:**
- Элегантное решение в одном месте
- Исправляет ВСЕ места вызова: и trim, и user_dict learning, и auto-conversion
- Семантически логично: "последнее слово" — это последнее слово, даже если после него есть пробел

**Минусы:**
- **Ломает `_try_auto_conversion_at_space()`!** Этот метод вызывается В МОМЕНТ нажатия Space, **до** того как Space попадает в буфер. Пробел в буфере — это пробел от *предыдущего* слова. Так что `_try_auto_conversion_at_space()` и сейчас корректно извлекает последнее слово (пробел от предыдущего слова — валидная граница). Если мы начнём пропускать trailing spaces, то при буфере `[h, e, l, l, o, SPACE, g, h, b, d, t, n]` и вызове при следующем Space — метод всё равно правильно вернёт "ghbdtn" (SPACE стоит ПЕРЕД словом, не после). **Вывод: `_try_auto_conversion_at_space()` не ломается**, потому что Space ещё не добавлен в буфер в момент вызова.

**Затрагиваемые файлы:**
- [lswitch/app.py](lswitch/app.py) — метод `_extract_last_word_events()` (строка 621)

**Побочные эффекты:**
- При буфере `[w, o, r, d, SPACE, SPACE, SPACE]` (несколько trailing пробелов) — вернёт "word". Это корректное поведение.
- При буфере `[SPACE, SPACE, SPACE]` (только пробелы) — вернёт `("", [])`. Корректно.
- `_try_auto_conversion_at_space()`: в момент вызова Space ещё не в буфере → поведение не меняется.
- `_do_conversion()` user_dict: теперь `manual_word` будет содержать слово перед пробелом → `add_confirmation()` сработает. Это **желательный** побочный эффект.
- `_do_conversion()` trim: теперь trim извлечёт последнее слово (перед trailing space) и обрежет буфер до него. **Но!** `chars_in_buffer` будет = длине только слова, а backspace удалит только столько символов. Текст в приложении содержит ещё и пробел(ы) после слова, которые не будут удалены → после retype получится "привет текст_в_другой_раскладке" (без удаления пробела). Это может быть проблемой: пробел перед словом останется, а после слова появится текст без пробела.

**⚠️ Проблема:** Trim обрезает буфер до "ghbdtn" (6 символов), но trailing space(s) остаются в тексте приложения. Retype удалит 6 символов (букв), переключит раскладку и наберёт "привет", но пробел ПОСЛЕ слова останется: `"hello привет "` вместо `"hello привет"`. Впрочем, trailing space обычно допустим — пользователь набрал его намеренно.

**Оценка: 8/10** — решает основную проблему, минимальные побочные эффекты.

---

#### Вариант B: В trim-блоке `_do_conversion()` — если `_extract_last_word_events()` вернул пусто, не обрезать

**Описание:** В блоке trim (строки 498-510) добавить проверку: если `last_word_events` пуст, но буфер не пуст — оставить буфер как есть (не обрезать).

```python
if saved_count > 0 and not self._selection_valid:
    try:
        _, last_word_events = self._extract_last_word_events(...)
        if last_word_events and len(last_word_events) < saved_count:
            # Обрезаем до последнего слова
            ...
        # Если last_word_events пуст — ничего не делаем, буфер остаётся
    except Exception as exc:
        logger.debug("DoConversion: trim skipped: %s", exc)
```

**Плюсы:**
- Абсолютно безопасно — это уже текущее поведение! Условие `if last_word_events and ...` уже защищает от пустого результата.

**Минусы:**
- **Не решает проблему!** Trim и сейчас не обрезает при пустом результате. Проблема в том, что retype обрабатывает весь буфер (13 символов), включая пробелы и предыдущие слова. Это приводит к удалению текста за пределами текущего слова.
- Не исправляет проблему с user_dict (manual_word всё ещё пуст).

**Затрагиваемые файлы:** нет изменений

**Побочные эффекты:** нет

**Оценка: 2/10** — не решает корень проблемы.

---

#### Вариант C: Не добавлять Space в event_buffer (только как word boundary)

**Описание:** В `_on_key_press()` при обработке Space — НЕ добавлять событие в `event_buffer`, а только управлять `chars_in_buffer` или вообще не менять буферы.

```python
elif data.code == KEY_SPACE:
    if self.auto_detector and self.config.get('auto_switch'):
        if self._try_auto_conversion_at_space():
            return
    # Normal space: DON'T add to event_buffer
    self.state_manager.on_key_press(data.code)
    # Можно: обнулить буфер, зафиксировав boundary
    self.state_manager.context.event_buffer.clear()
    self.state_manager.context.chars_in_buffer = 0
```

**Плюсы:**
- Пробелы никогда не попадают в буфер → `_extract_last_word_events()` всегда видит чистое слово
- Retype после Shift+Shift обработает только последнее слово (буфер содержит только его)

**Минусы:**
- **Серьёзно ломает repeat Shift+Shift (sticky buffer):** Если пользователь нажал пробел после слова, буфер очищается. Следующий Shift+Shift не найдёт ничего для конвертации.
- **Ломает retype при конвертации через пробел:** Если пользователь набрал "hello ghbdtn" и нажал Shift+Shift (без пробела в конце), конвертация должна обработать "ghbdtn". Но если пробел между словами очистил буфер, в буфере только "ghbdtn" — это корректно. Однако, если пользователь набрал слово и НЕ нажал пробел, а сразу Shift+Shift — буфер содержит всё что набрано с последнего пробела.
- **Проблема с chars_in_buffer:** Если обнулять `chars_in_buffer` при пробеле, а retype потом пытается делать backspace по `chars_in_buffer` — он не удалит символы текущего слова (буфер пуст). Нужно тогда начинать заново с N символов нового слова.
- **Потеря контекста:** Информация о предыдущих словах теряется. Это может быть проблемой для будущих фич (конвертация нескольких слов).

**Затрагиваемые файлы:**
- [lswitch/app.py](lswitch/app.py) — `_on_key_press()`, логика обработки Space

**Побочные эффекты:**
- Ломает sticky buffer механизм
- Меняет семантику `chars_in_buffer` и `event_buffer`
- Может вызвать баги при конвертации сразу после пробела

**Оценка: 3/10** — слишком много побочных эффектов, ломает существующую логику.

---

#### Вариант D (новый): Обрезать буфер до последнего слова при добавлении Space

**Описание:** Когда Space добавляется в буфер (auto-conversion не сработала), **обрезать** буфер — оставить только текущее слово + пробел. Предыдущие слова удаляются из буфера.

```python
elif data.code == KEY_SPACE:
    if self.auto_detector and self.config.get('auto_switch'):
        if self._try_auto_conversion_at_space():
            return
    # Word boundary: trim buffer to current word + space
    # (previous words no longer needed for retype)
    self.state_manager.on_key_press(data.code)
    data.shifted = self.state_manager.context.shift_pressed
    # Trim: keep only events after last SPACE in buffer
    buf = self.state_manager.context.event_buffer
    last_space_idx = -1
    for i in range(len(buf) - 1, -1, -1):
        if buf[i].code == KEY_SPACE:
            last_space_idx = i
            break
    if last_space_idx >= 0:
        trimmed = buf[last_space_idx + 1:]  # только текущее слово
    else:
        trimmed = list(buf)
    trimmed.append(data)  # добавляем текущий Space
    self.state_manager.context.event_buffer = trimmed
    self.state_manager.context.chars_in_buffer = len(trimmed)
```

**Плюсы:**
- Буфер никогда не содержит больше одного слова + trailing space
- `_extract_last_word_events()` при вызове из `_do_conversion()` найдёт `KEY_SPACE` последним → вернёт пусто. **Не решает!**

**Минусы:**
- Trailing space всё ещё в буфере → та же проблема с `_extract_last_word_events()`
- Усложняет логику обработки Space

**Оценка: 3/10** — не решает корневую проблему.

---

#### Вариант E (новый, рекомендуемый): Комбинация — пропуск trailing spaces в `_extract_last_word_events()` + учёт пробелов при trim

**Описание:** Двухчастное исправление:

**Часть 1:** В `_extract_last_word_events()` пропускать trailing `KEY_SPACE` перед началом сканирования слова (Вариант A).

**Часть 2:** В trim-блоке `_do_conversion()` учитывать, что trim должен также включать trailing spaces в `chars_in_buffer` для корректного количества backspace. Или: при trim подсчитывать trailing spaces и добавлять их к `saved_count` для backspace, но НЕ включать в `saved_events` для replay.

```python
# В _extract_last_word_events — добавляем подсчёт пропущенных пробелов:
def _extract_last_word_events(self, current_layout=None):
    ...
    word_events = []
    chars = []
    trailing_spaces = 0
    skipping_trailing = True
    for ev in reversed(self.state_manager.context.event_buffer):
        if ev.code == KEY_SPACE:
            if skipping_trailing:
                trailing_spaces += 1
                continue
            else:
                break
        skipping_trailing = False
        # ... основная логика
    ...
    return "".join(chars), word_events  # trailing_spaces можно вернуть 3м элементом
```

**Плюсы:**
- Полностью решает проблему
- Корректная обработка backspace при trim (удаляются и буквы, и trailing пробелы)
- Не ломает `_try_auto_conversion_at_space()`

**Минусы:**
- Изменение сигнатуры `_extract_last_word_events()` (если возвращать trailing_spaces) → нужно обновить все вызовы
- Можно и без изменения сигнатуры: trailing spaces просто пропускаются, а trim-блок в `_do_conversion()` сам подсчитает разницу

**Затрагиваемые файлы:**
- [lswitch/app.py](lswitch/app.py) — `_extract_last_word_events()` и trim-блок в `_do_conversion()`

**Побочные эффекты:**
- `_try_auto_conversion_at_space()`: Space ещё не в буфере → поведение не меняется ✅
- `_do_conversion()` user_dict: `manual_word` теперь содержит слово → `add_confirmation()` работает ✅  
- `_do_conversion()` trim: корректно обрезает до последнего слова ✅
- `debug_monitor.py` (строка 447): вызывает `_extract_last_word_events(None)` → теперь пропустит trailing spaces и покажет актуальное слово ✅

**Оценка: 9/10**

---

### Карта использований `_extract_last_word_events()`

| Место вызова | Файл | Строка | Контекст | Trailing space в буфере? |
|---|---|---|---|---|
| user_dict learning | [app.py](lswitch/app.py#L451) | 451 | `_do_conversion()` — извлечение `manual_word` | Да, если Space нажат перед Shift+Shift |
| trim-to-last-word | [app.py](lswitch/app.py#L498) | 498 | `_do_conversion()` — обрезка буфера | Да, если Space нажат перед Shift+Shift |
| auto_conversion | [app.py](lswitch/app.py#L584) | 584 | `_try_auto_conversion_at_space()` — извлечение слова | **Нет** — Space ещё не добавлен в буфер |
| debug_monitor | [debug_monitor.py](lswitch/ui/debug_monitor.py#L447) | 447 | Отображение текущего слова в UI | Да, если последний символ — Space |

### Рекомендация

**Рекомендую Вариант A** (простой пропуск trailing spaces в `_extract_last_word_events()`) как оптимальный баланс между:

1. **Простотой** — изменение в одном методе, ~5 строк кода
2. **Корректностью** — исправляет все места вызова
3. **Безопасностью** — не ломает `_try_auto_conversion_at_space()` (Space ещё не в буфере при вызове)
4. **Побочными эффектами** — минимальные, все положительные (user_dict learning начинает работать при trailing space)

Вариант E (расширенная версия А с учётом trailing spaces для backspace) может понадобиться **только если** после реализации Варианта А обнаружится проблема с количеством backspace при trim. На текущем этапе trim работает следующим образом:
- `last_word_events` содержит N событий слова (без пробелов)
- `chars_in_buffer` устанавливается в N
- Retype удаляет N символов backspace и replay N событий

Trailing space(s) останутся в тексте приложения — это **допустимо**, так как пользователь их намеренно набрал. Если позже потребуется удалять trailing пробелы при Shift+Shift, это будет отдельная задача.

### Конкретный план реализации Варианта A

**Файл:** [lswitch/app.py](lswitch/app.py) — метод `_extract_last_word_events()`, строка 644.

**Изменение:** Заменить прямой цикл `for ev in reversed(...)` на версию с пропуском trailing `KEY_SPACE`:

```python
word_events: list = []
chars: list[str] = []
skipping_trailing_spaces = True                        # ← НОВОЕ
for ev in reversed(self.state_manager.context.event_buffer):
    if ev.code == KEY_SPACE:
        if skipping_trailing_spaces:                   # ← НОВОЕ
            continue                                   # ← НОВОЕ
        break
    skipping_trailing_spaces = False                   # ← НОВОЕ
    # ... остальной код без изменений
```

**Тесты для добавления:**

1. Буфер `[g, h, b, SPACE]` → `_extract_last_word_events()` → `("ghb", [g, h, b])`
2. Буфер `[h, e, l, l, o, SPACE, g, h, b, SPACE]` → `("ghb", [g, h, b])`
3. Буфер `[SPACE, SPACE, SPACE]` → `("", [])`
4. Буфер `[g, h, b]` (без trailing space) → `("ghb", [g, h, b])` — без изменений
5. Интеграционный тест: набор "ghbdtn ", Shift+Shift → retype срабатывает для "ghbdtn"
---

## Задача 2: Автоконвертация съедает пробел — слова сливаются

### Анализ текущего поведения

#### Поток выполнения при автоконвертации (пошагово)

**Сценарий:** пользователь набирает `ghbdtn` (физические клавиши для "привет" в EN-раскладке) и нажимает Space.

**Шаг 1. Набор "ghbdtn"**

Каждое нажатие обрабатывается в `_on_key_press()` ([app.py](lswitch/app.py#L227)):
- `event_buffer.append(data)` — событие (value=1, press-only) попадает в буфер
- `chars_in_buffer += 1`

После набора буфер: `[g, h, b, d, t, n]`, `chars_in_buffer = 6`.

**Шаг 2. Физическое нажатие Space**

1. Пользователь нажимает Space на физической клавиатуре.
2. Ядро Linux доставляет событие `EV_KEY, KEY_SPACE, value=1` через `/dev/input/eventN` одновременно:
   - **Приложению** (через X11/Wayland input pipeline) — приложение вставляет символ пробела: текст на экране = `"ghbdtn "`.
   - **LSwitch** (через evdev passive monitoring) — EventManager публикует `KEY_PRESS` в EventBus.

3. `_on_key_press()` ([app.py](lswitch/app.py#L256-L260)) обрабатывает `KEY_SPACE`:

```python
elif data.code == KEY_SPACE:
    if self.auto_detector and self.config.get('auto_switch'):
        if self._try_auto_conversion_at_space():
            return  # space was consumed by auto-conversion
```

4. `_try_auto_conversion_at_space()` ([app.py](lswitch/app.py#L547-L620)):
   - Вызывает `_extract_last_word_events()` — сканирует буфер с конца, находит `[g, h, b, d, t, n]` (6 событий)
   - **Space ещё НЕ в буфере** (буфер заполняется только если auto-conversion не сработала)
   - Вызывает `auto_detector.should_convert("ghbdtn", "en")` → `(True, "reason")`
   - Вызывает `_do_auto_conversion_at_space(6, word_events, "en_to_ru")`
   - Возвращает `True` → `_on_key_press` делает `return`, Space **не добавляется в буфер**.

**Шаг 3. Автоконвертация — `_do_auto_conversion_at_space()`**

Код метода ([app.py](lswitch/app.py#L678-L731)):

```python
try:
    # 1. Найти целевую раскладку
    target = next((l for l in layouts if l.name.lower().startswith("ru")), None)

    # 2. Удалить word_len+1 символов (слово + пробел, уже напечатанный в приложении)
    self.virtual_kb.tap_key(KEY_BACKSPACE, n_times=word_len + 1)  # 7 BS

    # 3. Переключить раскладку
    if target and self.xkb:
        self.xkb.switch_layout(target=target)

    # 4. Печатать слово в новой раскладке
    self.virtual_kb.replay_events(word_events)  # 6 событий

    # 5. Вернуть пробел
    self.virtual_kb.tap_key(KEY_SPACE)  # 1 Space

except Exception as exc:
    logger.error("Auto-conversion at space failed: %s", exc)
finally:
    # Записать маркер для undo + сбросить буфер
    ctx.reset()
    ctx.state = State.IDLE
```

**Что происходит в приложении** (при нормальном выполнении):

| Этап | UInput-событие | Текст в приложении | Cursor pos |
|------|---------------|-------------------|------------|
| Исходное | — | `ghbdtn ` | 7 |
| 7× BS | BACKSPACE ×7 | `(пусто)` или `hello ` (если было prev word) | 0 / 6 |
| switch | xkb_switch | — раскладка теперь RU | — |
| replay 6 | press/release ×6 | `привет` / `hello привет` | 6 / 12 |
| 1× Space | KEY_SPACE | `привет ` / `hello привет ` | 7 / 13 |

**Вывод: в нормальном случае пробел НЕ теряется.** Слова НЕ сливаются. Логика `word_len+1` корректна: Space уже в приложении → удаляем его backspace → добавляем обратно после retype.

#### Тайминги

Задержки определены в `VirtualKeyboard` ([virtual_keyboard.py](lswitch/input/virtual_keyboard.py#L32-L33)):

```python
KEY_PRESS_DELAY  = 0.001   # 1 мс между press и release
KEY_REPEAT_DELAY = 0.001   # 1 мс между последовательными tap
```

**Расчёт для слова из 6 букв:**

| Этап | Формула | Время |
|------|---------|-------|
| 7 backspaces | 7 × (1мс press + 1мс between) = ~14мс | 14 мс |
| switch_layout | XkbLockGroup + XSync (syscall) | ~1 мс |
| replay 6 events | 6 × (1мс press + 1мс release + 1мс between) ≈ ~18мс | 18 мс |
| tap Space | 1мс press + 1мс release | 2 мс |
| **Итого** | | **~35 мс** |

**Сравнение с `RetypeMode.execute()` ([modes.py](lswitch/core/modes.py#L97)):**
- RetypeMode добавляет `time.sleep(0.05)` (50 мс!) между backspaces и replay
- `_do_auto_conversion_at_space` **НЕ имеет** такой паузы

Это потенциальная проблема: при медленных приложениях (тяжёлый Electron, web-app в Firefox) backspaces могут не успеть обработаться до начала replay. Однако X11 event queue является FIFO — события от UInput обрабатываются в порядке поступления, поэтому для большинства приложений порядок гарантирован.

### Корневая причина

**Слова НЕ сливаются** в нормальном потоке выполнения. Логика `word_len+1` корректно учитывает уже напечатанный пробел.

Однако найдены **три уязвимости**, при которых пробел может быть потерян:

#### Уязвимость 1: `tap_key(KEY_SPACE)` НЕ в finally-блоке (КРИТИЧНАЯ)

```python
try:
    self.virtual_kb.tap_key(KEY_BACKSPACE, n_times=word_len + 1)  # ✅ удаляет word+space
    if target and self.xkb:
        self.xkb.switch_layout(target=target)                     # ⚠️ МОЖЕТ БРОСИТЬ ИСКЛЮЧЕНИЕ
    self.virtual_kb.replay_events(word_events)                     # replay
    self.virtual_kb.tap_key(KEY_SPACE)                             # ← НЕ БУДЕТ ВЫЗВАН при исключении выше!
except Exception as exc:
    logger.error(...)           # ← исключение съедено, Space НЕ добавлен
finally:
    ctx.reset()                 # ← буфер сброшен
```

**Сценарий:**
1. `tap_key(BACKSPACE, 7)` — успешно удаляет `"ghbdtn "` из приложения
2. `switch_layout()` → X11 ошибка → `Exception`
3. Управление переходит в `except` → лог ошибки
4. `replay_events` и `tap_key(KEY_SPACE)` — **НЕ вызваны**
5. `finally` → `ctx.reset()`

**Результат:** текст `"ghbdtn "` удалён из приложения, ничего не вставлено. Потеря данных.

**Вероятность:** Низкая в нормальных условиях. `switch_layout()` ([xkb_adapter.py](lswitch/platform/xkb_adapter.py#L277-L307)) достаточно защищён:
- Cinnamon D-Bus вызов обёрнут в try/except
- XkbLockGroup работает напрямую через ctypes
- Но при обрыве X11-соединения, при работе через VNC/SSH, при проблемах с Wayland — может бросить исключение

#### Уязвимость 2: `_write()` молча съедает ошибки (СРЕДНЯЯ)

```python
def _write(self, code: int, value: int) -> None:
    if self._uinput is None:
        return                    # ← тихо ничего не делает!
    try:
        self._uinput.write(ecodes.EV_KEY, code, value)
        self._uinput.syn()
    except Exception as e:
        logger.debug(...)         # ← ошибка на уровне DEBUG, не WARNING/ERROR
```

**Сценарий 1:** UInput-устройство закрылось (например, после hotplug-события или OOM):
- `self._uinput = None` → все `_write()` тихо возвращаются
- `tap_key(KEY_SPACE)` вызывается, но ничего не отправляется
- Пробел потерян → слова сливаются

**Сценарий 2:** `self._uinput.write()` бросает исключение (сбой устройства):
- Ошибка логируется на уровне `DEBUG` (по умолчанию скрыта)
- Пробел потерян → слова сливаются

**Вероятность:** Низкая, но возможна при нестабильной работе UInput (виртуальные машины, удалённый доступ).

#### Уязвимость 3: Отсутствие паузы между этапами (НИЗКАЯ)

`_do_auto_conversion_at_space` не содержит `time.sleep()` между backspaces и replay (в отличие от `RetypeMode.execute()`, где есть 50мс пауза).

**Сценарий:** Медленное приложение (Electron, тяжёлый web-app) не успевает обработать backspaces до получения replay-событий. Результат может быть непредсказуемым: частичное удаление, вставка символов в неправильную позицию.

**Вероятность:** Низкая для обычных приложений (GTK/Qt). Средняя для Electron-приложений (VS Code, Slack, Discord с тяжёлым DOM).

### Edge Cases

#### 1. Если `replay_events()` бросит исключение

`replay_events()` ([virtual_keyboard.py](lswitch/input/virtual_keyboard.py#L47-L84)) использует только:
- `getattr()` — не бросает
- `time.sleep()` — не бросает (delay > 0)
- `self._write()` — ловит все исключения внутри

**Вывод:** `replay_events()` практически не может бросить исключение. Это НЕ является реальным edge case.

#### 2. Пользователь продолжает печатать во время автоконвертации

Конвертация занимает ~35 мс. Средняя скорость печати: ~80 WPM ≈ ~75 мс между нажатиями. Быстрая печать: ~120 WPM ≈ ~50 мс.

При быстрой печати: пользователь может нажать следующую клавишу через 50 мс. Конвертация (35 мс) + обработка X11 (~5 мс) = 40 мс. В большинстве случаев конвертация завершится до следующего нажатия.

Однако если conver­tation задерживается (медленное приложение, задержки ввода-вывода), новые символы могут:
- Быть удалены backspace'ми (если пользователь нажал до завершения backspace-фазы)
- Вставиться между replay и space (если нажал во время replay)

LSwitch **не блокирует ввод** (evdev — read-only), поэтому физические нажатия ВСЕГДА доставляются в приложение. Виртуальные (UInput) и физические события смешиваются в X11 event queue.

#### 3. `_uinput is None` (UInput-устройство не было создано)

Если при инициализации `VirtualKeyboard._open()` произошла ошибка:
- `self._uinput = None`
- Все `_write()` возвращают `return` без действий
- `tap_key(BACKSPACE, 7)` → ничего не удалено
- `replay_events()` → ничего не印введено
- `tap_key(KEY_SPACE)` → ничего не добавлено

**Результат:** Текст в приложении не изменяется (Space уже был доставлен). Фактически ничего не происходит. Слова НЕ сливаются, но и конвертации нет. Состояние при этом сбрасывается в `finally` → user_dict marker записывается для несуществующей конвертации.

#### 4. Несколько слов в буфере: `"hello ghbdtn"`

При нажатии Space после `"hello ghbdtn"`:
- `_extract_last_word_events()` сканирует с конца буфера до первого `KEY_SPACE`
- Возвращает `word = "ghbdtn"`, `word_events = [g, h, b, d, t, n]` (6 событий)
- `_do_auto_conversion_at_space(6, ...)`:
  - 7 backspaces: удаляют `"ghbdtn "` (6 букв + trailing space)
  - Текст в приложении: `"hello "`
  - Replay → `"hello привет"`
  - Space → `"hello привет "`

**Вывод:** Корректно! Предыдущие слова не затрагиваются.

### Варианты решения

#### Вариант A: Переместить `tap_key(KEY_SPACE)` в finally-блок

**Описание:** Гарантировать добавление пробела даже при исключении.

```python
try:
    self.virtual_kb.tap_key(KEY_BACKSPACE, n_times=word_len + 1)
    if target and self.xkb:
        self.xkb.switch_layout(target=target)
    self.virtual_kb.replay_events(word_events)
except Exception as exc:
    logger.error("Auto-conversion at space failed: %s", exc)
finally:
    # ВСЕГДА возвращаем пробел — даже при ошибке
    try:
        self.virtual_kb.tap_key(KEY_SPACE)
    except Exception:
        pass
    if orig_word:
        self._last_auto_marker = { ... }
    ctx.reset()
    ctx.state = State.IDLE
```

**Плюсы:**
- Пробел гарантированно добавлен (если UInput работоспособен)
- Минимальное изменение — перемещение одной строки + обёртка в try

**Минусы:**
- При ошибке в `switch_layout` пробел будет добавлен, но слово не retyped. Текст станет: `"hello  "` (backspace удалил word+space, потом добавлен только space). Это лучше, чем полная потеря текста, хоть и удаляет слово.
- При ошибке **до** backspaces (если `tap_key(BACKSPACE)` сам бросил) — пробел будет добавлен дважды: один от приложения + один из finally. Маловероятно, т.к. `tap_key` использует `_write`, который не бросает.

**Затрагиваемые файлы:**
- [lswitch/app.py](lswitch/app.py) — метод `_do_auto_conversion_at_space()` (строка 693-731)

**Оценка: 7/10** — решает уязвимость 1, не решает уязвимости 2 и 3.

---

#### Вариант B: Добавить задержку между `replay_events()` и `tap_key(KEY_SPACE)`

**Описание:** Аналогично `RetypeMode.execute()`, добавить `time.sleep(0.05)` для гарантии обработки replay до отправки пробела.

```python
self.virtual_kb.tap_key(KEY_BACKSPACE, n_times=word_len + 1)
time.sleep(0.05)  # ← дать приложению время обработать backspaces

if target and self.xkb:
    self.xkb.switch_layout(target=target)

self.virtual_kb.replay_events(word_events)
time.sleep(0.01)  # ← дать приложению время обработать replay

self.virtual_kb.tap_key(KEY_SPACE)
```

**Плюсы:**
- Снижает вероятность проблем с медленными приложениями (уязвимость 3)
- Консистентность с `RetypeMode.execute()` (тоже имеет delay)

**Минусы:**
- Увеличивает общее время конвертации: 35мс → 35+50+10 = 95мс
- Пользователь может заметить задержку при быстрой печати
- НЕ решает уязвимости 1 и 2 (пробел всё ещё не в finally, `_write` всё ещё молчит)

**Затрагиваемые файлы:**
- [lswitch/app.py](lswitch/app.py) — метод `_do_auto_conversion_at_space()`

**Оценка: 4/10** — решает только уязвимость 3, добавляет задержку.

---

#### Вариант C: Не удалять пробел (`word_len` вместо `word_len+1`)

**Описание:** Удалять только буквы слова, оставляя пробел на месте. Убрать `tap_key(KEY_SPACE)` в конце.

```python
self.virtual_kb.tap_key(KEY_BACKSPACE, n_times=word_len)  # БЕЗ +1
if target and self.xkb:
    self.xkb.switch_layout(target=target)
self.virtual_kb.replay_events(word_events)
# tap_key(KEY_SPACE) — УДАЛЁН (пробел уже на месте)
```

**Анализ:**
Cursor стоит ПОСЛЕ пробела: `"hello ghbdtn |"` (pos 13).

`word_len = 6` backspaces удаляют:
1. `" "` (pos 12) → `"hello ghbdtn"` cursor at 12
2. `"n"` (pos 11)
3. `"t"` (pos 10)
4. `"d"` (pos 9)
5. `"b"` (pos 8)
6. `"h"` (pos 7)

Результат: `"hello g"` cursor at 7. **Удалено только 5 букв + пробел, а не 6 букв!**

Проблема: backspace удаляет символ ПЕРЕД курсором. Курсор стоит после пробела. Первый backspace удаляет пробел, а не последнюю букву. В итоге первая буква слова (`g`) остаётся, и результат: `"hello gпривет"`.

**Вывод: Вариант C НЕКОРРЕКТЕН!** Нельзя просто заменить `word_len+1` на `word_len` — это оставит одну лишнюю букву исходного слова перед сконвертированным текстом.

**Оценка: 0/10** — ломает конвертацию.

---

#### Вариант D (комбинированный, рекомендуемый): `tap_key(KEY_SPACE)` в finally + задержка перед replay

**Описание:** Объединение Вариантов A и B:

```python
def _do_auto_conversion_at_space(self, word_len, word_events, direction, ...):
    from lswitch.core.event_manager import KEY_BACKSPACE, KEY_SPACE
    from lswitch.core.states import State

    ctx = self.state_manager.context
    _space_sent = False                                              # ← НОВОЕ: флаг

    try:
        target_lang = "ru" if direction == "en_to_ru" else "en"
        try:
            layouts = self.xkb.get_layouts() if self.xkb else []
            target = next(
                (l for l in layouts if l.name.lower().startswith(target_lang)),
                None,
            )
        except Exception:
            target = None

        self.virtual_kb.tap_key(KEY_BACKSPACE, n_times=word_len + 1)

        if target and self.xkb:
            self.xkb.switch_layout(target=target)

        import time as _time_mod
        _time_mod.sleep(0.03)                                        # ← НОВОЕ: пауза 30мс

        self.virtual_kb.replay_events(word_events)
        self.virtual_kb.tap_key(KEY_SPACE)
        _space_sent = True                                           # ← НОВОЕ: пробел отправлен

    except Exception as exc:
        logger.error("Auto-conversion at space failed: %s", exc)
    finally:
        if not _space_sent:                                          # ← НОВОЕ: гарантия пробела
            try:
                self.virtual_kb.tap_key(KEY_SPACE)
            except Exception:
                pass
        import time as _time
        if orig_word:
            self._last_auto_marker = { ... }
        ctx.reset()
        ctx.state = State.IDLE
```

**Плюсы:**
- Решает уязвимость 1: пробел гарантированно добавлен через finally
- Решает уязвимость 3: пауза 30мс даёт приложению время обработать backspaces
- Флаг `_space_sent` предотвращает двойной пробел (если try успешно завершился)
- Общее время: ~35мс + 30мс = ~65мс — незаметно для пользователя (предел восприятия ~100мс)

**Минусы:**
- Не решает уязвимость 2 (`_write` молча проглатывает ошибки) — это требует отдельного рефакторинга `VirtualKeyboard`
- Добавляет ~30мс ко времени каждой автоконвертации
- При ошибке в switch_layout: текст слова удалён, не retyped, но хотя бы пробел есть → `"hello  "` (два пробела вместо `"hello привет "`)

**Затрагиваемые файлы:**
- [lswitch/app.py](lswitch/app.py) — метод `_do_auto_conversion_at_space()` (~15 строк изменений)

**Побочные эффекты:**
- Увеличение времени автоконвертации с ~35мс до ~65мс
- При ошибке: вместо потери текста — пробел сохраняется (улучшение)
- Тесты `test_auto_convert.py`: тест `test_context_reset_on_exception` нужно обновить — теперь `tap_key(KEY_SPACE)` вызывается даже при ошибке

**Оценка: 9/10**

---

#### Вариант E: Логирование _write ошибок как WARNING + верификация

**Отдельная задача** для решения уязвимости 2:

```python
def _write(self, code: int, value: int) -> bool:
    if self._uinput is None:
        logger.warning("VirtualKeyboard: _uinput is None, event dropped (code=%d)", code)
        return False
    try:
        from evdev import ecodes
        self._uinput.write(ecodes.EV_KEY, code, value)
        self._uinput.syn()
        return True
    except Exception as e:
        logger.warning("VirtualKeyboard write error (code=%d): %s", code, e)
        return False
```

**Плюсы:** Ошибки станут видимы в логах. Позволяет вызывающему коду реагировать на потерю событий.

**Минусы:** Изменение сигнатуры `_write` → обновить все вызовы. Можно отложить.

**Оценка: 5/10** — полезно для диагностики, но не предотвращает потерю пробела.

### Рекомендация

**Рекомендую Вариант D** — комбинация `tap_key(KEY_SPACE)` в finally-блоке с флагом предотвращения дупликации + пауза 30мс перед replay.

**Обоснование:**

1. **Слова НЕ сливаются в нормальном потоке** — текущая логика `word_len+1` корректна. Это не баг в happy-path, а проблема error-handling и edge cases.

2. **Главная проблема — `tap_key(KEY_SPACE)` не в finally:** Если `switch_layout()` бросает исключение (X11 сбой, VNC, Wayland fallback), пробел теряется, а слово удалено. Вариант D гарантирует добавление пробела через finally-блок.

3. **Отсутствие паузы — второстепенная проблема:** Для обычных приложений (GTK/Qt) X11 event queue обеспечивает FIFO-порядок. Но для Electron-приложений и тяжёлых web-apps пауза 30мс (аналогично 50мс в `RetypeMode`) может предотвратить гонку. 30мс — компромисс: достаточно для обработки, но незаметно для пользователя.

4. **Вариант C (word_len без +1) категорически не рекомендуется:** Он математически неверен — cursor стоит после пробела, и backspace без +1 оставит первую букву слова на месте.

5. **Уязвимость _write — отдельная задача:** Молчаливое проглатывание ошибок в `_write()` — архитектурная проблема, которая затрагивает не только автоконвертацию. Рекомендуется вынести в отдельный тикет.

### Конкретный план реализации Варианта D

**Файл:** [lswitch/app.py](lswitch/app.py) — метод `_do_auto_conversion_at_space()` (строки 678-731)

**Шаг 1:** Добавить флаг `_space_sent = False` перед try-блоком.

**Шаг 2:** После `self.virtual_kb.tap_key(KEY_SPACE)` внутри try — выставить `_space_sent = True`.

**Шаг 3:** Добавить `time.sleep(0.03)` между `switch_layout()` и `replay_events()`.

**Шаг 4:** В finally-блоке: если `not _space_sent` — вызвать `self.virtual_kb.tap_key(KEY_SPACE)` защищённый try/except.

**Тесты для обновления/добавления:**
1. `test_context_reset_on_exception` — проверить, что `tap_key(KEY_SPACE)` вызывается даже при ошибке
2. Новый тест: `test_space_restored_on_switch_layout_failure` — mock `xkb.switch_layout` = raise → проверить вызов `tap_key(KEY_SPACE)`

---

## Задача 3: Shift+Shift не отменяет ложную автоконвертацию

### Анализ текущего поведения

#### Поток автоконвертации (Space)

1. Пользователь набирает `"ghbdtn"` → `event_buffer` содержит 6 событий, `chars_in_buffer = 6`
2. Нажимает Space → `_on_key_press()` → `_try_auto_conversion_at_space()` → `return True` (пробел потреблён)
3. `_extract_last_word_events()` извлекает `word = "ghbdtn"`, `word_events = [6 событий]`
4. `AutoDetector.should_convert()` возвращает `(True, reason)`
5. `_do_auto_conversion_at_space(word_len=6, word_events, direction="en_to_ru", orig_word="ghbdtn", orig_lang="en")`

Внутри `_do_auto_conversion_at_space()` ([app.py](../lswitch/app.py#L681-L731)):
- `tap_key(KEY_BACKSPACE, n_times=7)` — удаляет 6 букв + 1 пробел
- `xkb.switch_layout(target=ru)` — переключает на русскую раскладку
- `virtual_kb.replay_events(word_events)` — воспроизводит те же keycodes → «привет»
- `virtual_kb.tap_key(KEY_SPACE)` — вставляет пробел
- **Сохраняет маркер:**
  ```python
  self._last_auto_marker = {
      'word': 'ghbdtn',
      'direction': 'en_to_ru',
      'lang': 'en',
      'time': <timestamp>,
  }
  ```
- **Вызывает `ctx.reset()`** → `event_buffer = []`, `chars_in_buffer = 0`
- **Устанавливает `ctx.state = State.IDLE`**

**Критически важно:** `word_events` НЕ сохраняются ни в маркере, ни в `_last_retype_events`.

#### Поток отмены (Shift+Shift)

1. Пользователь нажимает Shift+Shift → FSM: `IDLE → SHIFT_PRESSED → CONVERTING`
2. `_on_key_release()` вызывает `_do_conversion()`

Внутри `_do_conversion()` ([app.py](../lswitch/app.py#L428-L545)):

**Case A** (маркер установлен):
```python
if self._last_auto_marker is not None:
    marker = self._last_auto_marker
    self.user_dict.add_correction(marker['word'], marker['lang'])  # ← weight -1
    self._last_auto_marker = None
```
→ Записывается штраф в user_dict. **Это ЕДИНСТВЕННОЕ действие Case A.** Текст на экране не изменяется.

Далее в try-блоке:
- `saved_events = list(ctx.event_buffer)` → `[]` (буфер пуст после reset)
- `saved_count = ctx.chars_in_buffer` → `0`
- Проверка sticky: `saved_count == 0 and self._last_retype_events` → `_last_retype_events` пуст → **не срабатывает**
- `conversion_engine.convert(ctx, selection_valid=False)`:
  - `choose_mode()`: `chars_in_buffer=0, selection_valid=False, backspace_hold_active=False` → fallback `"retype"`
  - `RetypeMode.execute()`: `chars_in_buffer <= 0` → `return False`
- `success = False` → `_last_retype_events = []`

**Результат: текст «привет » остаётся на экране. Отмены не было.**

### Корневая причина

Проблема двойная:

1. **`_last_auto_marker` не содержит `word_events`** — при созании маркера в `_do_auto_conversion_at_space()` оригинальные события клавиатуры не сохраняются. Без них невозможно воспроизвести исходный текст.

2. **`_last_retype_events` не заполняется после автоконвертации** — sticky-буфер заполняется только в `_do_conversion()` при `success=True` и `saved_count > 0`. Автоконвертация обходит `_do_conversion()` полностью, поэтому sticky-буфер остаётся пустым.

3. **Case A в `_do_conversion()` — только user_dict, без retype** — после `add_correction()` никакой обратной конвертации не выполняется. Управление передаётся в `conversion_engine.convert()`, который видит пустой буфер и ничего не делает.

### Дополнительные обнаруженные проблемы

#### Ложный штраф при вводе нового текста

Если пользователь после автоконвертации **продолжает набирать** (например, «мир»), а потом нажимает Shift+Shift:
- `_last_auto_marker is not None` → Case A срабатывает → `add_correction()` добавляет штраф
- Но пользователь хотел конвертировать «мир», а не отменить предыдущую автоконвертацию!
- `chars_in_buffer = 3` → `conversion_engine.convert()` конвертирует «мир» через retype
- Штраф несправедлив: пользователь принял автоконвертацию (продолжил печатать)

**Причина:** Case A не проверяет `chars_in_buffer > 0` — если буфер не пуст, значит пользователь набрал новый текст и маркер следует интерпретировать как подтверждение (или просто очистить).

#### Отсутствие таймаута на маркере

Поле `'time'` сохраняется в маркере, но нигде не проверяется. Если пользователь долго думает после автоконвертации (>5 сек), а потом нажимает Shift+Shift — штраф всё равно применяется.

### Варианты решения

#### Вариант A: Сохранять `word_events` в маркере + явный undo в Case A

**Суть:** Расширить `_last_auto_marker` полем `word_events`, и в `_do_conversion()` Case A выполнять явную обратную конвертацию.

**Изменения в `_do_auto_conversion_at_space()`:**
```python
self._last_auto_marker = {
    'word': orig_word,
    'direction': direction,
    'lang': orig_lang,
    'time': _time.time(),
    'word_events': list(word_events),   # ← НОВОЕ
    'converted_len': len(word_events),  # ← НОВОЕ (длина = кол-во events)
}
```

**Изменения в `_do_conversion()` Case A:**
```python
if self._last_auto_marker is not None:
    marker = self._last_auto_marker
    # Штраф только если буфер пуст (пользователь не набрал нового текста)
    if self.user_dict and self.state_manager.context.chars_in_buffer == 0:
        self.user_dict.add_correction(marker['word'], marker['lang'])

    self._last_auto_marker = None

    # Выполнить обратную конвертацию, если буфер пуст
    if self.state_manager.context.chars_in_buffer == 0 and marker.get('word_events'):
        word_events = marker['word_events']
        n_delete = len(word_events) + 1  # сконвертированное слово + пробел
        # Удалить сконвертированный текст + пробел
        self.virtual_kb.tap_key(KEY_BACKSPACE, n_times=n_delete)
        # Найти и переключить на оригинальную раскладку
        orig_lang = marker['lang']  # "en" или "ru"
        layouts = self.xkb.get_layouts()
        orig_layout = next(
            (l for l in layouts if l.name.lower().startswith(orig_lang)), None
        )
        if orig_layout:
            self.xkb.switch_layout(target=orig_layout)
        # Воспроизвести оригинальные события
        self.virtual_kb.replay_events(word_events)
        # Вернуть пробел
        self.virtual_kb.tap_key(KEY_SPACE)
        # Не вызывать conversion_engine.convert() — undo выполнен
        self.state_manager.on_conversion_complete()
        return
```

**Плюсы:**
- Самодостаточный: вся информация для undo хранится в маркере
- Не затрагивает sticky-буфер (который служит другой цели — повтор Shift+Shift)
- Явно управляет количеством удаляемых символов (word + space)
- Можно добавить защиту от edge-cases прямо в код undo
- Обратная конвертация идентична по логике `_do_auto_conversion_at_space()`, только в обратном направлении

**Минусы:**
- Дублирование логики retype (удаление → switch → replay → space)
- Дополнительный код в `_do_conversion()`, который и так сложен

#### Вариант B: Заполнять `_last_retype_events` после автоконвертации

**Суть:** В `_do_auto_conversion_at_space()` после конвертации записать `self._last_retype_events = word_events`. Тогда при Shift+Shift sticky-буфер подхватится.

**Изменения в `_do_auto_conversion_at_space()`:**
```python
# В finally-блоке, после ctx.reset():
self._last_retype_events = list(word_events)
```

**Проблемы:**
1. **Несовпадение количества символов:** Sticky-буфер восстанавливает `chars_in_buffer = len(word_events)`, но на экране `len(word_events) + 1` символов (слово + пробел). RetypeMode удалит `len(word_events)` символов → пробел останется.
2. **Направление переключения раскладки:** `RetypeMode.execute()` вызывает `xkb.switch_layout()` без `target` — просто циклическое переключение. Если раскладок больше 2, может переключить не на ту.
3. **Обходной путь для пробела:** Можно добавить фиктивное Space-событие в sticky-буфер, но тогда после undo будет дополнительный пробел (replay Space → 2 пробела: один от retype, один от undo). Требуется сложная логика.

**Плюсы:**
- Минимальные изменения в коде (1 строка)
- Использует существующий механизм

**Минусы:**
- Не работает корректно из-за проблемы с пробелом и направлением switch
- Потребует модификации RetypeMode для обработки «undo после auto» — нарушает SRP
- Sticky-буфер задуман для повтора конвертации, а не для undo — семантическое несоответствие

#### Вариант C: Hybrid — маркер + доработка RetypeMode

**Суть:** Сохранить `word_events` в маркере. В Case A восстановить events в context (+1 для пробела), установить специальный флаг `undo_auto=True`, и передать в `conversion_engine.convert()`. `RetypeMode` проверяет флаг и корректирует поведение.

**Плюсы:**
- Единая точка retype-логики (в RetypeMode)

**Минусы:**
- Усложняет RetypeMode флагом, который нужен только для undo
- Требует изменения интерфейса convert() для передачи флага
- Пробел всё равно нужно обрабатывать отдельно

#### Вариант D: Сохранять undo-информацию в отдельной структуре

**Суть:** Ввести `_undo_info: dict | None` — отдельный буфер для undo, содержащий всё необходимое:
```python
self._undo_info = {
    'word_events': word_events,
    'delete_count': len(word_events) + 1,
    'target_lang': orig_lang,  # куда переключаться
    'time': time.time(),
}
```
В `_do_conversion()`, если `_undo_info` установлен — выполнять undo из него (не из маркера).

**Плюсы:**
- Чёткое разделение ответственности: маркер отвечает за user_dict, undo_info — за обратную конвертацию
- Легко добавить таймаут
- Не загрязняет маркер дополнительными полями

**Минусы:**
- Ещё одно состояние для отслеживания (нужно сбрасывать в тех же местах, что и маркер)

### Анализ edge-cases

| Сценарий | Ожидание | Обработка |
|----------|----------|-----------|
| Undo сразу после auto-conv (пустой буфер) | Текст возвращается к оригиналу | Это основной кейс — undo + штраф в user_dict |
| Undo после набора нового текста | Конвертировать новый текст (не undo) | Если `chars_in_buffer > 0`: очистить маркер, обработать как Case B |
| Повторный Shift+Shift после undo | Нет действия (буфер пуст) | Маркер уже очищен, sticky пуст → ничего не происходит |
| Навигация / Enter / мышь после auto-conv | Маркер сбрасывается | Уже реализовано: `_last_auto_marker = None` при navigation/enter/mouse |
| Длительная пауза (>5 сек) | Спорно: undo или нет? | Рекомендуется: добавить timeout-проверку (маркер имеет поле `time`) |
| Несовпадение длины слов (EN→RU) | Одинаковая | Не проблема: replay_events воспроизводит те же keycodes, каждый keycode → ровно 1 символ в любой раскладке. Длина всегда = `len(word_events)` |
| После undo раскладка не та | Должна вернуться к оригинальной | Вариант A явно переключает на `marker['lang']` |

### Рекомендация

**Рекомендуется Вариант A** (сохранение `word_events` в маркере + явный undo в Case A) по следующим причинам:

1. **Простота и надёжность:** Вся информация для отмены хранится в одном месте (маркер). Логика undo — зеркальное отражение автоконвертации, она понятна и предсказуема.

2. **Минимальное влияние на существующий код:** Не затрагивает `RetypeMode`, `ConversionEngine`, `SelectionMode`. Изменения локализованы в двух методах одного файла (`_do_auto_conversion_at_space` и `_do_conversion`).

3. **Корректная обработка пробела:** Явное удаление `word_len + 1` символов гарантирует, что пробел после сконвертированного слова тоже удаляется.

4. **Исправление бага с ложным штрафом:** Добавление условия `chars_in_buffer == 0` в Case A решает проблему несправедливого штрафа, когда пользователь продолжил ввод после автоконвертации.

5. **Готовность к расширениям:** Легко добавить timeout-проверку на `marker['time']` и другие защитные механизмы.

**Объём изменений (оценка):**
- `_do_auto_conversion_at_space()` — добавить 2 поля в маркер (~2 строки)
- `_do_conversion()` — добавить блок undo после Case A (~15-20 строк)
- Добавить guard `chars_in_buffer == 0` в Case A для штрафа (~1 строка)
- Тесты: 3-4 новых теста для undo-сценариев

**Файлы для изменения:**
- [lswitch/app.py](../lswitch/app.py) — `_do_auto_conversion_at_space()` (строки ~719-726), `_do_conversion()` (строки ~454-466)

---

## Задача 4: SelectionMode — PRIMARY вместо CLIPBOARD

### Анализ текущего поведения

#### Текущая реализация SelectionMode ([modes.py](../lswitch/core/modes.py#L119-L153))

`SelectionMode.execute()` выполняет следующую последовательность:

```python
sel = self.selection.get_selection()          # 1. Читает PRIMARY selection
source_lang = detect_language(sel.text)       # 2. Определяет язык
converted = convert_text(sel.text, direction) # 3. Конвертирует текст
self.selection.replace_selection(converted)   # 4. Вставляет через CLIPBOARD
self.xkb.switch_layout(target=target_layout)  # 5. Переключает раскладку
```

Критический шаг — `replace_selection()` — делегирован в `X11SelectionAdapter`.

#### Текущая реализация replace_selection ([selection_adapter.py](../lswitch/platform/selection_adapter.py#L82-L96))

```python
def replace_selection(self, new_text: str) -> bool:
    old_clip = self._system.get_clipboard(selection="clipboard")   # 1. Сохранить CLIPBOARD
    self._system.set_clipboard(new_text, selection="clipboard")    # 2. Записать в CLIPBOARD
    time.sleep(0.02)                                               # 3. 20мс пауза
    self._system.xdotool_key("ctrl+v")                             # 4. Ctrl+V (вставка)
    time.sleep(0.05)                                               # 5. 50мс пауза
    if old_clip is not None:
        self._system.set_clipboard(old_clip, selection="clipboard") # 6. Восстановить CLIPBOARD
    return True
```

**Проблемы текущей реализации:**

1. **CLIPBOARD загрязняется.** Clipboard manager (Cinnamon, KDE Klipper, CopyQ и пр.) перехватывает каждый вызов `set_clipboard()` и добавляет текст в историю. Даже если мы восстанавливаем CLIPBOARD после вставки, история уже засорена — в ней лежит конвертированный текст.

2. **Race condition при восстановлении.** Между `xdotool_key("ctrl+v")` (шаг 4) и восстановлением (шаг 6) проходит 50мс. Если приложение не успело прочитать CLIPBOARD за 50мс — оно прочитает уже восстановленный `old_clip` вместо `new_text`. Медленные Electron-приложения (VS Code, Slack, Discord) могут не уложиться в этот таймаут.

3. **Не работает в терминалах.** `Ctrl+V` в xterm, gnome-terminal, mate-terminal и большинстве терминалов вставляет литерал `^V`, а не содержимое CLIPBOARD. Требуется `Ctrl+Shift+V`, но и это поддерживается не всеми терминалами.

4. **Исключение при восстановлении.** Если `set_clipboard(old_clip)` бросит исключение (X11 disconnect, timeout xclip), CLIPBOARD навсегда содержит конвертированный текст. Обёртки try/except нет — исключение поднимается выше (правда, `replace_selection` обёрнут в общий try/except, возвращающий False).

5. **Двойная запись в clipboard.** `set_clipboard(new_text)` + `set_clipboard(old_clip)` — два вызова `xclip -i -selection clipboard`, каждый из которых порождает subprocess и может занять до 300мс (timeout по умолчанию). Общий overhead: ~370мс (20мс sleep + 50мс sleep + 2×xclip).

#### Текущая реализация ISystemAdapter ([system_adapter.py](../lswitch/platform/system_adapter.py), [subprocess_impl.py](../lswitch/platform/subprocess_impl.py))

```python
class ISystemAdapter(ABC):
    def run_command(self, args: list[str], timeout: float = 1.0) -> CommandResult: ...
    def xdotool_key(self, sequence: str, timeout: float = 0.3) -> None: ...
    def get_clipboard(self, selection: str = "primary") -> str: ...
    def set_clipboard(self, text: str, selection: str = "clipboard") -> None: ...
```

`get_clipboard` и `set_clipboard` поддерживают параметр `selection`, который передаётся в `xclip -selection <value>`. Допустимые значения: `"primary"`, `"clipboard"`, `"secondary"`. Таким образом, **инфраструктура для работы с PRIMARY уже есть** — достаточно передать `selection="primary"`.

`xdotool_key` оборачивает `xdotool key <sequence>` — может отправить любую последовательность клавиш. Для эмуляции нажатия мыши потребуется `xdotool click 2` (отдельная команда) или `run_command(["xdotool", "click", "2"])`.

#### Что уже умеет VirtualKeyboard ([virtual_keyboard.py](../lswitch/input/virtual_keyboard.py))

`VirtualKeyboard` работает через UInput (ядерный уровень evdev):
- `tap_key(keycode, n_times)` — нажатие/отпускание клавиши
- `replay_events(events)` — replay списка событий с поддержкой Shift
- `_write(code, value)` — низкоуровневая запись evdev-событий

UInput поддерживает не только клавиатурные, но и мышиные события: `BTN_LEFT (272)`, `BTN_RIGHT (273)`, `BTN_MIDDLE (274)`. Однако текущий `VirtualKeyboard` создаёт UInput-устройство без регистрации мышиных кнопок — потребуется расширение `_open()` для поддержки `BTN_MIDDLE`.

В `event_manager.py` уже определены: `MOUSE_BUTTONS = {272, 273, 274}  # BTN_LEFT, BTN_RIGHT, BTN_MIDDLE`.

### Техническая feasibility

#### Подход A: PRIMARY + Middle Click (`xdotool click 2`)

**Алгоритм:**
1. `old_primary = xclip -o -selection primary` — сохранить текущий PRIMARY
2. `xclip -i -selection primary <<< converted_text` — записать конвертированный текст в PRIMARY
3. `xdotool click 2` — эмулировать нажатие средней кнопки мыши (вставка из PRIMARY)
4. `xclip -i -selection primary <<< old_primary` — восстановить PRIMARY

**Совместимость xdotool click 2:**

| Приложение | Работает? | Примечания |
|------------|-----------|------------|
| gedit, pluma, xed | ✅ | Стандартное X11-поведение |
| Firefox, Chromium | ✅ | В текстовых полях; в основном окне — может открыть ссылку/прокрутку |
| gnome-terminal, xterm | ✅ | Middle-click вставляет из PRIMARY |
| mate-terminal | ✅ | Аналогично |
| VS Code (Electron) | ⚠️ | Работает, но вставка в позицию мыши, не текстового курсора |
| LibreOffice | ✅ | Вставка из PRIMARY по Middle Click |
| Kate, KWrite (KDE) | ✅ | Стандартное поведение |
| Wayland (wl-roots) | ❌ | xdotool не работает в чистом Wayland |

**КРИТИЧЕСКАЯ ПРОБЛЕМА: Middle Click вставляет в позицию курсора МЫШИ, а не текстового курсора.**

Это фундаментальное ограничение: в X11 Middle Click отправляет `ButtonPress` + `ButtonRelease` в окно под указателем мыши, и приложение вставляет текст в позицию, определяемую координатами мыши. Если пользователь:
1. Выделил текст (текстовый курсор в конце выделения)
2. Мышь осталась в конце выделения → ОК, вставка в правильное место
3. Мышь переместилась → вставка в НЕПРАВИЛЬНОЕ место

Это делает Middle Click **непригодным** как универсальную замену Ctrl+V для нашего use-case. SelectionMode часто вызывается через Shift+Shift, и к моменту нажатия Shift+Shift курсор мыши может быть где угодно.

#### Подход B: PRIMARY + Shift+Insert

**Алгоритм:**
1. Сохранить PRIMARY
2. Записать конвертированный текст в PRIMARY
3. `xdotool key shift+Insert` — вставка из PRIMARY
4. Восстановить PRIMARY

**Совместимость Shift+Insert:**

| Приложение | Вставляет из | Примечания |
|------------|-------------|------------|
| xterm | PRIMARY | ✅ Стандартное поведение |
| gnome-terminal | CLIPBOARD | ❌ В GNOME-terminal Shift+Insert вставляет CLIPBOARD, не PRIMARY |
| mate-terminal | CLIPBOARD | ❌ Аналогично |
| gedit, pluma | CLIPBOARD | ❌ GTK-приложения вставляют из CLIPBOARD по Shift+Insert |
| Firefox, Chromium | CLIPBOARD | ❌ |
| VS Code | CLIPBOARD | ❌ |

**Вывод:** `Shift+Insert` вставляет из PRIMARY **только в xterm и его производных**. В подавляющем большинстве приложений Shift+Insert вставляет из CLIPBOARD. Этот подход **НЕ решает** проблему — мы по-прежнему будем вынуждены записывать текст в CLIPBOARD.

#### Подход C: UInput-based SelectionMode (из docs/SELECTION_UINPUT_DESIGN.md)

**Алгоритм:**
1. Прочитать PRIMARY → `text = "ghbdtn"`
2. `convert_text(text) → "привет"`
3. `tap_key(KEY_BACKSPACE, len(text))` — удалить выделенный текст через UInput
4. `switch_layout()` → RU
5. Для каждого символа: `char_to_keycode(char) → (keycode, shifted)` → `tap_key(keycode)`
6. CLIPBOARD не трогается

**Ключевое требование:** обратный маппинг `char → keycode`. Дизайн-документ ([SELECTION_UINPUT_DESIGN.md](../docs/SELECTION_UINPUT_DESIGN.md)) описывает реализацию через инверсию `KEYCODE_TO_CHAR_EN` из [key_mapper.py](../lswitch/input/key_mapper.py).

**Совместимость:**

| Приложение | Работает? | Примечания |
|------------|-----------|------------|
| GTK (gedit, pluma, xed) | ✅ | UInput — ядерный уровень, работает везде |
| Qt (Kate, KWrite) | ✅ | Аналогично |
| Терминалы (все) | ✅ | **Главный выигрыш** — Ctrl+V не работает в терминалах, UInput работает |
| Electron (VS Code) | ✅ | Вставка в позицию ТЕКСТОВОГО курсора (не мыши!) |
| Firefox, Chromium | ✅ | |
| Wayland | ⚠️ | UInput работает через ядро, но XKB layout switch может потребовать адаптации |

**Проблема с Backspace при активном выделении:** `KEY_BACKSPACE × len(text)` работает не так, как ожидается, при выделенном тексте:

- В GTK/Qt: **первый** Backspace удаляет всё выделение целиком, остальные удаляют символы перед бывшим началом выделения → **перебор**
- Решение: отправить **1** Backspace (или Delete) для удаления выделения, затем набирать через UInput

Ещё проще: поскольку текст выделен, можно **просто начать печатать** — выделение будет автоматически заменено набираемым текстом (стандартное поведение GUI-приложений «typing replaces selection»). Тогда:
1. Прочитать PRIMARY → определить текст и язык
2. `switch_layout()` → target
3. `type_text(converted, layout=target)` → набранные символы ЗАМЕНЯТ выделение

Это самый элегантный вариант, но требует чтобы приложение поддерживало «typing replaces selection». Это стандартное поведение во всех современных GUI-приложениях, **НО**:
- В **vim/nvim**: не работает (другая парадигма редактирования)
- В терминалах: заменяется ввод в командной строке, но не во всех контекстах

#### Подход D: Исправить CLIPBOARD-подход (текущий), минимизировать загрязнение

**Алгоритм:**
1. `old_clip = get_clipboard("clipboard")` — сохранить
2. `set_clipboard(new_text, "clipboard")` — записать
3. `xdotool_key("ctrl+v")` — вставить
4. **Увеличить** таймаут перед восстановлением (100-200мс вместо 50мс)
5. `set_clipboard(old_clip, "clipboard")` — восстановить
6. **Попытаться очистить историю clipboard manager** (специфично для DE)

**Проблемы:** Увеличение таймаута не решает проблему clipboard manager — он перехватывает текст мгновенно при записи в CLIPBOARD. Единственный способ — записывать и восстанавливать быстрее, чем clipboard manager успеет прочитать, но это гонка, которую мы не можем гарантированно выиграть.

#### Race condition анализ для PRIMARY-подхода

```
Поток LSwitch:                    Другие приложения:
────────────────                   ──────────────────
old = read PRIMARY                 
write PRIMARY ← converted         
                                   ← приложение X читает PRIMARY 
                                     (получает converted вместо оригинала!)
xdotool click 2                    
                                   ← целевое приложение читает PRIMARY
                                     (получает converted — OK)
restore PRIMARY ← old              
                                   ← приложение X читает PRIMARY
                                     (получает old — OK)
```

**Окно гонки:** между `write PRIMARY` и `restore PRIMARY` любое приложение, читающее PRIMARY, получит наш конвертированный текст. Это менее критично, чем загрязнение CLIPBOARD:
- PRIMARY используется реже, чем CLIPBOARD
- Clipboard managers обычно НЕ мониторят PRIMARY (только CLIPBOARD)
- Но Middle Click вставка всё ещё прочитает «наш» текст, если пользователь кликнет средней кнопкой в это окно

#### Эмуляция BTN_MIDDLE через UInput

Можно отправить `BTN_MIDDLE` напрямую через `VirtualKeyboard._write(274, 1)` + `_write(274, 0)`. Для этого нужно расширить `VirtualKeyboard._open()`:

```python
import evdev
cap = {ecodes.EV_KEY: list(range(1, 249)) + [272, 273, 274]}  # клавиатура + мышь
self._uinput = evdev.UInput(cap, name=self.DEVICE_NAME)
```

Но проблема та же: BTN_MIDDLE вставляет в позицию мыши, не текстового курсора. UInput vs xdotool — тот же результат.

### Варианты решения

#### Вариант A: PRIMARY + Middle Click

| Параметр | Оценка |
|----------|--------|
| Не загрязняет CLIPBOARD | ✅ |
| Не загрязняет clipboard history | ✅ (clipboard managers не мониторят PRIMARY) |
| Вставка в правильную позицию | ❌ **КРИТИЧНО** — вставка в позицию мыши |
| Работает в терминалах | ✅ |
| Race conditions | ⚠️ Окно гонки при восстановлении PRIMARY |
| Сложность реализации | Низкая (~15 строк) |

**Оценка: 3/10** — непригоден из-за проблемы с позицией вставки.

#### Вариант B: PRIMARY + Shift+Insert

| Параметр | Оценка |
|----------|--------|
| Не загрязняет CLIPBOARD | ❌ (Shift+Insert из CLIPBOARD в большинстве приложений) |
| Вставка в правильную позицию | ✅ (текстовый курсор) |
| Работает в терминалах | ⚠️ Только xterm |
| Универсальность | ❌ Работает корректно с PRIMARY только в xterm |
| Сложность | Низкая |

**Оценка: 2/10** — не решает проблему, т.к. Shift+Insert в большинстве приложений вставляет из CLIPBOARD.

#### Вариант C: UInput-based SelectionMode (рекомендуемый)

| Параметр | Оценка |
|----------|--------|
| Не загрязняет CLIPBOARD | ✅ CLIPBOARD не используется вообще |
| Не загрязняет clipboard history | ✅ |
| Вставка в правильную позицию | ✅ Текстовый курсор (UInput = реальная клавиатура) |
| Работает в терминалах | ✅ UInput работает на ядерном уровне |
| Race conditions | ✅ Нет — clipboard не участвует |
| Универсальность | ✅ Ядерный уровень, не зависит от toolkit |
| Сложность | Умеренная (~50-70 строк нового кода) |

**Что нужно реализовать** (по дизайн-документу [SELECTION_UINPUT_DESIGN.md](../docs/SELECTION_UINPUT_DESIGN.md)):

1. **`char_to_keycode()`** в [key_mapper.py](../lswitch/input/key_mapper.py) — обратный маппинг из `KEYCODE_TO_CHAR_EN`
2. **`type_text()`** в [virtual_keyboard.py](../lswitch/input/virtual_keyboard.py) — набор текста по символам
3. **Обновление `SelectionMode.execute()`** — замена `replace_selection()` на: UInput-набор с заменой выделения

**Ограничения:**
- Символы вне карты (emoji, спецсимволы) → fallback на `xdotool type` или clipboard
- Скорость: ~8мс/символ, для 200 символов ≈ 1.6 сек — приемлемо для типичных слов/фраз
- Требуется, чтобы выделение было активно — если пользователь снял выделение, набранный текст попадёт после курсора

**Оценка: 9/10**

#### Вариант D: Исправить текущий CLIPBOARD-подход

| Параметр | Оценка |
|----------|--------|
| Не загрязняет CLIPBOARD | ❌ Загрязняет, пытается восстановить |
| Не загрязняет clipboard history | ❌ Clipboard manager перехватывает мгновенно |
| Вставка в правильную позицию | ✅ Ctrl+V вставляет в текстовый курсор |
| Работает в терминалах | ❌ Ctrl+V не работает в терминалах |
| Race conditions | ⚠️ Увеличение таймаута снижает, но не устраняет |
| Сложность | Минимальная (увеличить sleep) |

**Оценка: 4/10** — паллиатив, не решает корневых проблем.

#### Вариант E: Гибридный — UInput с clipboard-fallback

**Суть:** По умолчанию использовать Вариант C (UInput). Если `type_text()` не может набрать символ (нет в keymap), fallback на clipboard для ЭТОГО символа:

```python
def execute_uinput(self, context, sel_text, converted):
    # 1. Переключить раскладку
    self.xkb.switch_layout(target=target_layout)
    time.sleep(0.05)

    # 2. Набрать через UInput (при активном выделении текст заменит его)
    failed = self.virtual_kb.type_text(converted, layout=target_lang)

    # 3. Fallback для символов вне keymap
    if failed:
        for char in failed:
            self.system.set_clipboard(char, "clipboard")
            self.system.xdotool_key("ctrl+v")
            time.sleep(0.02)
```

**Оценка: 9/10** — лучший из всех вариантов с graceful degradation.

### Сравнительная таблица всех вариантов

| | A: PRIMARY+MClick | B: PRIMARY+Shift+Ins | C: UInput | D: Fix CLIPBOARD | E: UInput+fallback |
|---|---|---|---|---|---|
| Не портит CLIPBOARD | ✅ | ❌ | ✅ | ❌ | ✅* |
| Clipboard history чистая | ✅ | ❌ | ✅ | ❌ | ✅* |
| Позиция вставки | ❌ мыши | ✅ | ✅ | ✅ | ✅ |
| Терминалы | ✅ | ⚠️ xterm | ✅ | ❌ | ✅ |
| Race conditions | ⚠️ | ⚠️ | ✅ | ⚠️ | ✅ |
| Универсальность | ⚠️ | ❌ | ✅ | ⚠️ | ✅ |
| Сложность | Низкая | Низкая | Средняя | Минимальная | Средняя |
| **Итого** | **3/10** | **2/10** | **9/10** | **4/10** | **9/10** |

\* — fallback загрязняет clipboard только для символов вне keymap (редкий случай).

### Дополнительные находки

#### 1. SelectionMode.execute() не использует VirtualKeyboard

Текущий `SelectionMode.__init__()` принимает `selection`, `xkb`, `system`, но **НЕ** `virtual_kb`. Для реализации Варианта C/E потребуется расширить конструктор:

```python
class SelectionMode(BaseMode):
    def __init__(self, selection, xkb, system, virtual_kb=None, debug=False):
        ...
        self.virtual_kb = virtual_kb
```

Это потребует обновления всех мест создания `SelectionMode` (в [conversion_engine.py](../lswitch/core/conversion_engine.py) и тестах).

#### 2. Проблема «выделение уже снято»

Если пользователь снял выделение (кликнул мышью) перед нажатием Shift+Shift, `get_selection()` вернёт **предыдущее** содержимое PRIMARY (X11 не очищает PRIMARY при снятии выделения). `SelectionMode` прочитает и конвертирует старый текст, а UInput-подход начнёт удалять/вводить символы в неожиданном месте.

Защита: `has_fresh_selection()` проверяет freshness через `(owner_id, text)` пару. В `_do_conversion()` проверяется `self._selection_valid` — если False, SelectionMode не вызывается. Это **уже защищено** в текущей реализации.

#### 3. Единая архитектурная модель RetypeMode + SelectionMode

После реализации Варианта C оба режима работают через UInput:

```
RetypeMode:     N×BS → switch_layout → replay_events(keycodes из event_buffer)
SelectionMode:  type_text(converted) → замена выделения → switch_layout
```

Разница только в источнике данных — event_buffer vs текстовая конвертация. Это упрощает архитектуру и устраняет класс проблем, связанных с clipboard.

#### 4. Поведение «typing replaces selection» в разных приложениях

При активном текстовом выделении набор символов заменяет выделение в:
- ✅ GTK (gedit, pluma, Xed, TextEditor)
- ✅ Qt (Kate, KWrite, Dolphin rename)
- ✅ Electron (VS Code, Slack, Discord)
- ✅ Firefox/Chromium (текстовые поля и contenteditable)
- ✅ LibreOffice (Writer, Calc)
- ⚠️ Терминалы: работает в командной строке (bash readline), но не при выделении текста в viewport
- ❌ Vim/Neovim: Insert mode не заменяет Visual selection при наборе

Для 95%+ use-cases «typing replaces selection» работает корректно.

### Рекомендация

**Рекомендуется Вариант E** (UInput с clipboard-fallback) по следующим причинам:

1. **Полностью устраняет загрязнение CLIPBOARD** в 99%+ случаев (обычные буквы EN/RU) — clipboard используется только для символов вне keymap (emoji, спецсимволы).

2. **Работает в терминалах** — главная боль текущей реализации. UInput на ядерном уровне не зависит от того, как приложение обрабатывает Ctrl+V.

3. **Нет race conditions** — clipboard не участвует в основном потоке. Нет окна гонки между записью и восстановлением.

4. **Вставка в правильную позицию** — UInput = реальная клавиатура. Символы набираются в позицию текстового курсора, а не мыши. При активном выделении текст заменяет его.

5. **Graceful degradation** — при невозможности набрать символ через UInput, fallback на clipboard для отдельных символов (минимальное загрязнение).

6. **Уже есть дизайн-документ** — [SELECTION_UINPUT_DESIGN.md](../docs/SELECTION_UINPUT_DESIGN.md) детально описывает `char_to_keycode()` и `type_text()`. Реализация — ~50-70 строк нового кода.

7. **Консистентность** — оба режима (Retype и Selection) будут использовать UInput, что упрощает архитектуру и тестирование.

**Принципиальное решение по Middle Click:** **НЕ использовать.** Вставка в позицию курсора мыши — фундаментальный дефект, делающий подход ненадёжным. UInput-набор через `type_text()` решает все проблемы без этого ограничения.

**Объём изменений (оценка):**
- [lswitch/input/key_mapper.py](../lswitch/input/key_mapper.py) — `char_to_keycode()`, обратный маппинг (~20 строк)
- [lswitch/input/virtual_keyboard.py](../lswitch/input/virtual_keyboard.py) — `type_text()` (~25 строк)
- [lswitch/core/modes.py](../lswitch/core/modes.py) — обновить `SelectionMode.__init__()` и `execute()` (~20 строк)
- [lswitch/core/conversion_engine.py](../lswitch/core/conversion_engine.py) — передать `virtual_kb` в `SelectionMode` (~3 строки)
- Тесты: 5-8 новых тестов для `char_to_keycode`, `type_text`, обновлённый `SelectionMode`

**Ход реализации (рекомендуемый):**
1. Реализовать `char_to_keycode()` в key_mapper.py + тесты
2. Реализовать `type_text()` в virtual_keyboard.py + тесты
3. Обновить `SelectionMode` — заменить `replace_selection()` на UInput-подход
4. Обновить wiring (conversion_engine, app.py) для передачи `virtual_kb`
5. Интеграционные тесты: конвертация выделенного текста без загрязнения clipboard

---

## Задача 5: Запись слов в словарь при Shift+Shift

### Анализ текущего поведения

#### Точки записи в user_dictionary

В текущем коде есть **три** точки, где слова записываются в `UserDictionary`:

| # | Где | Метод | Вес | Когда срабатывает |
|---|-----|-------|-----|-------------------|
| 1 | [app.py](../lswitch/app.py#L455-L466) `_do_conversion()` Case A | `add_correction(marker['word'], marker['lang'])` | **-1** | Shift+Shift сразу после авто-конвертации (отмена). `_last_auto_marker` указывает на слово, которое было авто-конвертировано |
| 2 | [app.py](../lswitch/app.py#L469-L474) `_do_conversion()` Case B | `add_confirmation(manual_word, manual_lang)` | **+1** | Ручная конвертация Shift+Shift по непустому буферу **без** предшествующей авто-конвертации |
| 3 | [app.py](../lswitch/app.py#L605-L607) `_try_auto_conversion_at_space()` | `add_confirmation(old['word'], old['lang'])` | **+1** | Авто-конвертация произошла, пользователь продолжил набор до следующего пробела (принятие) |

#### Детальный разбор Case A (строки 455-466)

```python
if self._last_auto_marker is not None:
    marker = self._last_auto_marker
    if self.user_dict:
        self.user_dict.add_correction(
            marker['word'], marker['lang'], debug=self.debug,
        )
    self._last_auto_marker = None
```

**Что происходит:** AutoDetector авто-конвертировал `"ghbdtn"` (EN) → `"привет"` (RU). Пользователь нажимает Shift+Shift — это означает «отмена, я хотел именно `ghbdtn`». Маркер содержит `{word: "ghbdtn", lang: "en"}`. Вызывается `add_correction("ghbdtn", "en")` → ключ `en:ghbdtn`, weight **-1**.

**Что записывается:** Штраф для пары `(en, ghbdtn)` — «не конвертируй это слово, когда набрано в EN-раскладке».

**Что НЕ записывается:** Оригинальное слово (`"ghbdtn"`) не подтверждается как «правильное написание в EN». Впрочем, это и не требуется — штраф уже решает задачу.

#### Детальный разбор Case B (строки 469-474)

```python
elif manual_word and manual_lang and self.user_dict:
    self.user_dict.add_confirmation(manual_word, manual_lang, debug=self.debug)
```

**Что происходит:** Пользователь набрал `"ghbdtn"` в EN-раскладке, AutoDetector НЕ сработал (ни по пробелу, ни иным образом) — `_last_auto_marker is None`. Пользователь нажимает Shift+Shift для ручной конвертации.

**Что записывается:**
- `manual_word` — результат `_extract_last_word_events(layout_info)`, т.е. последнее слово из буфера: `"ghbdtn"`
- `manual_lang` — текущая раскладка через `_layout_to_lang()`: `"en"`
- Ключ: `en:ghbdtn`, weight **+1**

**Какое влияние на AutoDetector:** **Никакого.** Вот ключевая проблема (см. ниже).

#### Детальный разбор Case 3 (строки 605-607)

```python
if self._last_auto_marker is not None and self.user_dict:
    old = self._last_auto_marker
    self.user_dict.add_confirmation(old['word'], old['lang'], debug=self.debug)
    self._last_auto_marker = None
```

**Что происходит:** AutoDetector конвертировал слово, пользователь продолжил набор и нажал пробел (следующее слово). Это интерпретируется как «принятие» — авто-конвертация была правильной. Weight **+1** для исходного слова.

**Какое влияние на AutoDetector:** Тоже **никакого** в текущей логике (см. ниже).

#### Как AutoDetector использует user_dict

В [auto_detector.py](../lswitch/intelligence/auto_detector.py#L74-L81):

```python
# Priority 1.5: UserDictionary protection
if self.user_dict:
    w_lower = word_clean.lower()
    if self.user_dict.is_protected(w_lower, current_layout):
        return (False, "user_dict: temporarily protected")
    weight = self.user_dict.get_weight(w_lower, current_layout)
    min_w = self.user_dict.data.get('settings', {}).get('min_weight', 2)
    if weight <= -min_w:
        return (False, f"user_dict: weight={weight} <= -{min_w}")
```

AutoDetector проверяет:
1. **Temporary protection** (`is_protected`) — 5 секунд после `add_correction()` слово не конвертируется
2. **Negative weight** — если `weight <= -min_weight` (по умолчанию -2), конвертация подавляется

**Критическое наблюдение: положительные веса ИГНОРИРУЮТСЯ.** AutoDetector не содержит проверки `if weight >= +min_w: return (True, ...)`. Положительный вес от `add_confirmation()` записывается в JSON, но **никогда не используется** для принятия решений.

Это означает:
- Case B (`add_confirmation` при ручной конвертации): вес +1 **не влияет** на будущие решения AutoDetector
- Case 3 (`add_confirmation` при принятии авто-конвертации): вес +1 **не влияет** на будущие решения

Комментарий в `_do_conversion()` line 435 вводит в заблуждение:
> «Weight accumulates across sessions; once |weight| >= min_weight AutoDetector will handle this word automatically.»

Это описывает только negative path (подавление). Positive path (поощрение конвертации) **не реализован**.

#### Формат хранения в user_dict

```python
@staticmethod
def _key(word: str, lang: str) -> str:
    return f"{lang}:{word.lower().strip()}"
```

Ключ: `"en:ghbdtn"` — конкатенация языка и слова в нижнем регистре. Запись **однонаправленная** — при ручной конвертации `"ghbdtn"` (EN→RU) записывается ТОЛЬКО `en:ghbdtn`, но НЕ `ru:привет`.

#### Персистентность

В [persistence.py](../lswitch/intelligence/persistence.py):
- `save_json()` — атомарная запись через temp file + `os.replace()`
- `flush()` вызывается **при каждой** операции `add_correction()` / `add_confirmation()`
- Данные не теряются при аварийном завершении

**Потенциальная проблема:** при частых Shift+Shift (например, серия слов) — каждое слово вызывает `flush()` = запись на диск. При SSD это не критично, но на медленных носителях может замедлять ввод.

### Корневая причина

Логика user_dict learning имеет **три архитектурных дефекта**:

#### Дефект 1: Положительные веса бесполезны

`add_confirmation()` записывает weight +1, но AutoDetector никогда не проверяет положительные веса. Метод существует «на будущее», но сейчас это мёртвый код с точки зрения влияния на поведение.

**Следствие:** Когда пользователь 10 раз вручную конвертирует `"ghbdtn"` → `"привет"`, словарь содержит `en:ghbdtn → weight: +10`, но AutoDetector по-прежнему может не конвертировать это слово (если dictionary_service и ngrams не видят его).

#### Дефект 2: Однонаправленная запись

При ручной конвертации записывается только `(word, source_lang)`, но не `(converted_word, target_lang)`. AutoDetector, проверяя слово в целевой раскладке, не найдёт соответствующей записи.

**Пример:**
- Пользователь конвертирует `"ghbdtn"` (en) → `"привет"` (ru)
- Записывается: `en:ghbdtn` → +1
- Если потом набирает `"привет"` в ru-раскладке — записи `ru:привет` нет
- AutoDetector не может использовать эту информацию

#### Дефект 3: В Case A не записывается «обратное подтверждение»

При отмене авто-конвертации (Case A) записывается штраф для авто-конвертированного слова, но НЕ записывается подтверждение для оригинального написания. Это неоптимально: пользователь явно сказал «я хочу именно это слово в этой раскладке», но этот факт не фиксируется.

**Пример:**
- AutoDetector конвертирует `"ghbdtn"` (en) → `"привет"` (ru)
- Пользователь отменяет: `add_correction("ghbdtn", "en")` → weight -1
- Но `"ghbdtn"` как EN-слово не получает +1 в обратном направлении
- Это не критично (штраф уже работает), но при более сложных сценариях обратное подтверждение ускорило бы обучение

### Взаимосвязь с Задачей 1 (trailing space)

Если в буфере есть trailing space (Задача 1), то `_extract_last_word_events()` возвращает `("", [])`, и Case B не срабатывает:

```python
manual_word, _ = self._extract_last_word_events(layout_info)
# manual_word = "" → условие elif manual_word and manual_lang не выполнится
```

**Следствие:** Ручная конвертация после пробела **не записывается** в user_dict. Решение Задачи 1 (пропуск trailing spaces в `_extract_last_word_events()`) автоматически исправит эту проблему.

### Варианты решения

#### Вариант A: Увеличить вес manual confirmation до +2 или +3

**Описание:** Изменить `add_confirmation()` или вызов в `_do_conversion()` Case B — передавать больший вес.

```python
# Вариант: в _do_conversion Case B
self.user_dict.add_confirmation(manual_word, manual_lang, weight=3, debug=self.debug)
```

**Плюсы:** Минимальное изменение кода.
**Минусы:** **Бесполезно** без решения Дефекта 1 — положительные веса не используются AutoDetector. Пока AutoDetector не научится использовать positive weights, увеличение веса ничего не даст.

**Вердикт:** ❌ Не решает проблему без сопутствующих изменений в AutoDetector.

#### Вариант B: Использовать положительные веса в AutoDetector

**Описание:** Добавить в `should_convert()` проверку положительного веса — если `weight >= +min_weight`, конвертировать даже если dictionary_service и ngrams не уверены.

```python
# В auto_detector.py, после проверки negative weight:
if weight >= min_w:
    return (True, f"user_dict: weight={weight} >= +{min_w}, user confirmed")
```

**Плюсы:**
- Заставляет `add_confirmation()` реально работать
- Пользователь «обучает» AutoDetector: после N ручных конвертаций слово будет конвертироваться автоматически
- Учитывает накопленный опыт

**Минусы:**
- Нужен аккуратный порядок проверки: positive weight должен быть ПОСЛЕ «already correct» (чтобы не конвертировать корректные слова), но ПЕРЕД dictionary-based и ngram
- Один пользователь может создать словарь, который сломает поведение на другом (решается: словарь per-user, уже так)

**Риски:**
- Если вставить проверку ПЕРЕД «already correct», может конвертировать слова, которые уже корректны в текущей раскладке. Нужно size guard: `weight >= +min_w` и слово НЕ в словаре текущей раскладки
- Нужно учесть, что для Case 3 (принятие авто-конвертации) positive weight тоже записывается — это означает, что после 2 успешных авто-конвертаций слово будет конвертироваться через user_dict даже если dictionary/ngrams перестанут его распознавать. Это может быть и плюсом (устойчивость), и минусом (жёсткость)

**Размещение проверки (рекомендуемое):**
```python
# Priority 1: already correct → no convert (без изменений)
# Priority 1.5a: protected → no convert (без изменений)  
# Priority 1.5b: negative weight → no convert (без изменений)
# Priority 1.5c: НОВОЕ — positive weight → convert
if weight >= min_w:
    return (True, f"user_dict: weight={weight} >= +{min_w}")
# Priority 2: dictionary → convert (без изменений)
# Priority 3: ngrams (без изменений)
```

Таким образом positive weight будет после «already correct» (не сломает корректные слова) и после negative weight, но перед dictionary/ngram.

**Вердикт:** ✅ Ключевое изменение, которое делает весь user_dict learning осмысленным.

#### Вариант C: Двунаправленная запись (source + target)

**Описание:** При ручной конвертации записывать слово в обоих направлениях:
1. `(manual_word, source_lang)` → +N (как сейчас)
2. `(converted_word, target_lang)` → +N (новое)

```python
# В _do_conversion Case B:
self.user_dict.add_confirmation(manual_word, manual_lang, debug=self.debug)
# Дополнительно: конвертировать слово и записать в target
from lswitch.intelligence.maps import EN_TO_RU, RU_TO_EN
mapping = EN_TO_RU if manual_lang == "en" else RU_TO_EN
converted = "".join(mapping.get(c, c) for c in manual_word.lower())
target_lang = "ru" if manual_lang == "en" else "en"
self.user_dict.add_confirmation(converted, target_lang, debug=self.debug)
```

**Плюсы:**
- AutoDetector получает информацию в обоих направлениях
- Если пользователь переключится на другую раскладку и наберёт то же слово — system знает об обоих вариантах

**Минусы:**
- Увеличивает размер словаря в 2 раза
- Конвертированное слово может не совпадать с реальным написанием (maps-конвертация приблизительная для edge cases)
- Два `flush()` вместо одного — двойная запись на диск

**Вердикт:** ⚠️ Полезно, но вторично по отношению к Варианту B. Без Варианта B двунаправленная запись тоже бесполезна (положительные веса не используются).

#### Вариант D: Обратное подтверждение при Case A (correction + reverse confirmation)

**Описание:** В Case A, помимо штрафа за авто-конвертированное слово, записывать подтверждение для оригинала в целевой раскладке.

```python
# Case A: undo auto-conversion
if self._last_auto_marker is not None:
    marker = self._last_auto_marker
    if self.user_dict:
        # Штраф за неправильную конвертацию
        self.user_dict.add_correction(marker['word'], marker['lang'])
        # НОВОЕ: подтверждение оригинала в target lang
        target_lang = "ru" if marker['lang'] == "en" else "en"
        from lswitch.intelligence.maps import EN_TO_RU, RU_TO_EN
        mapping = EN_TO_RU if marker['lang'] == "en" else RU_TO_EN
        converted = "".join(mapping.get(c, c) for c in marker['word'].lower())
        self.user_dict.add_confirmation(converted, target_lang)
```

**Плюсы:** Ускоряет обучение — одна отмена создаёт два сигнала.
**Минусы:**
- Сложнее логика
- Зависит от Варианта B (иначе confirmation бесполезна)
- Конвертированное слово — это то, что AutoDetector пытался получить, оно может быть валидным словом целевого языка. Подтверждение `ru:привет` при отмене конвертации `en:ghbdtn → привет` — семантически неверно (пользователь НЕ хотел "привет")

**Вердикт:** ❌ Семантически спорно. Пользователь отменяет конвертацию — значит, «привет» не нужен. Записывать +1 для `ru:привет` вводит словарь в заблуждение.

#### Вариант E: Настраиваемый вес в конфиге

**Описание:** Добавить параметр `manual_conversion_weight` в `config.json`.

```json
{
  "manual_conversion_weight": 2,
  "auto_confirmation_weight": 1,
  "correction_weight": -1
}
```

**Плюсы:**
- Гибкость: агрессивное обучение для опытных пользователей
- Не требует изменения логики AutoDetector

**Минусы:**
- Без Варианта B — бесполезно (positive weights не используются)
- Усложняет конфигурацию

**Вердикт:** ⚠️ Имеет смысл как дополнение к Варианту B, но не самостоятельно.

#### Вариант F (комбинированный): B + E + увеличенный вес

**Описание:** Комплексное решение:
1. **Вариант B:** Добавить проверку positive weight в `AutoDetector.should_convert()`
2. **Увеличить вес** manual conversion до +2 (или настраиваемый через конфиг, Вариант E)
3. Оставить вес auto-confirmation (Case 3) на +1 — авто-конвертация «подтверждённая молчанием» менее надёжна, чем явное ручное действие

```
Manual Shift+Shift (Case B):   weight +2    (быстрое обучение, 1 действие = auto на будущее)
Auto-conv accepted (Case 3):   weight +1    (слабый сигнал, нужно 2 подтверждения)
Correction (Case A):           weight -1    (нужно 2 отмены для подавления)
```

**Плюсы:**
- Одна ручная конвертация сразу обучает AutoDetector (при `min_weight=2`, weight +2 ≥ min_weight)
- Разграничены уровни «уверенности»: ручное действие > молчаливое принятие
- Настраиваемость через конфиг для продвинутых пользователей

**Минусы:**
- Если min_weight=2 и manual weight=2, одна ошибочная ручная конвертация сразу обучит AutoDetector неправильно. Но пользователь может отменить через Shift+Shift (correction -1 → итого +1, ещё не достигает порога)
- Нужно обновить комментарий/docstring в `_do_conversion()`

### Таблица затронутых файлов

| Файл | Что менять | Строки |
|------|-----------|--------|
| [auto_detector.py](../lswitch/intelligence/auto_detector.py) | Добавить проверку `weight >= +min_w` в `should_convert()` | ~82 (после negative weight check) |
| [app.py](../lswitch/app.py) | Увеличить вес в Case B (или передавать `weight` параметром) | ~470 |
| [user_dictionary.py](../lswitch/intelligence/user_dictionary.py) | Добавить параметр `weight` в `add_confirmation()` | ~70 |
| [config.py](../lswitch/config.py) | (опционально) `manual_conversion_weight` | ~30 |
| Тесты | Проверить что positive weight вызывает конвертацию | Новые тесты |

### Рекомендация

**Рекомендуемый вариант: F (B + E + увеличенный вес)**

**Приоритет реализации:**

1. **Этап 1 (критический):** Вариант B — добавить в `AutoDetector.should_convert()` проверку positive weight. Это ключевое изменение, без которого вся система `add_confirmation()` бессмысленна. ~5 строк кода + тесты.

2. **Этап 2 (быстрое обучение):** Увеличить вес Case B (manual conversion) до +2. Добавить параметр `weight` в `add_confirmation()`. ~3 строки кода.

3. **Этап 3 (опционально):** Настраиваемые веса в конфиге. Низкий приоритет — можно добавить позже.

**Зависимость от Задачи 1:** Решение Задачи 1 (trailing space) необходимо для корректной работы Case B — иначе `manual_word` будет пустым при наличии пробела в конце буфера.

**Оценка трудозатрат:** ~20-30 строк кода + ~30-40 строк тестов. Изменения минимальны и локализованы.
