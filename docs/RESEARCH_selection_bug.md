# Исследование: Баг с конвертацией выделенного текста по Shift+Shift

**Дата:** 2026-02-27  
**Статус:** Исследование завершено, фикс не применялся

---

## 1. Описание бага

При выделении текста мышью и последующем нажатии Shift+Shift конвертация не происходит.
`ConversionEngine.choose_mode()` выбирает `retype` вместо `selection`, а `RetypeMode` пропускает выполнение (`chars_in_buffer=0`).

Лог:
```
State: IDLE → SHIFT_PRESSED (on 'shift_down')
State: SHIFT_PRESSED → TYPING (on 'shift_up_single')
State: TYPING → SHIFT_PRESSED (on 'shift_down')
State: SHIFT_PRESSED → CONVERTING (on 'shift_up_double')
Converting in mode: retype
RetypeMode: skip — chars_in_buffer=0
State: CONVERTING → IDLE (on 'complete')
```

---

## 2. Полная трасировка цепочки событий

### Сценарий: пользователь выделяет текст drag-select мышью, затем нажимает Shift+Shift

#### Шаг 1 — Mouse button DOWN (начало drag-select)

evdev генерирует: `code=272 (BTN_LEFT), value=1 (press)`

**event_manager.py:74** — `code in MOUSE_BUTTONS` → True, `value == 1` → True  
→ Публикуется `Event(EventType.MOUSE_CLICK, ...)`

**app.py:259 `_on_mouse_click()`:**
```python
self._last_auto_marker = None
self._selection_valid = False          # ← сброс
self._last_retype_events = []
self._mouse_clicked_since_last_check = True   # ← КЛЮЧЕВОЙ ФЛАГ
self.state_manager.on_mouse_click()    # → context.reset(), state → IDLE
```

**Состояние после:**
- `_selection_valid = False`
- `_mouse_clicked_since_last_check = True`
- `_prev_sel_text` = (прежнее значение, не обновляется)
- `chars_in_buffer = 0`
- State: `IDLE`

#### Шаг 2 — Mouse drag (перемещение мыши с зажатой кнопкой)

evdev генерирует события `EV_REL` / `EV_ABS` (тип != `EV_KEY`).

**event_manager.py:63** — `event_type != self._ev_key` → return  
Никаких событий не публикуется. X11 обновляет PRIMARY selection по мере выделения.

#### Шаг 3 — Mouse button UP (конец drag-select)

evdev генерирует: `code=272 (BTN_LEFT), value=0 (release)`

**event_manager.py:74** — `code in MOUSE_BUTTONS` → True, но `value == 1` → **False** (value=0)  
→ **MOUSE_CLICK НЕ публикуется для release!** Только для press.

**Состояние после:** PRIMARY теперь содержит выделенный текст. Но LSwitch не знает об этом — никакого события не было.

#### Шаг 4 — Первый Shift press

**app.py:176 `_on_key_press()`:** `data.code in SHIFT_KEYS` → True  
→ `state_manager.on_shift_down()`

**state_manager.py:42 `on_shift_down()`:**
```python
self.context.shift_pressed = True
self._transition("shift_down")    # IDLE → SHIFT_PRESSED
```

**Важно:** Shift press НЕ сбрасывает `_selection_valid`, НЕ трогает `_mouse_clicked_since_last_check`, НЕ меняет `chars_in_buffer`.

#### Шаг 5 — Первый Shift release

**app.py:213 `_on_key_release()`:** `data.code in SHIFT_KEYS` → True  
→ `is_double = state_manager.on_shift_up()`

**state_manager.py:47 `on_shift_up()`:**
```python
self.context.shift_pressed = False
now = time.time()
delta = now - self.context.last_shift_time   # last_shift_time=0 → delta ≈ 1.7 млрд
# delta >> timeout → НЕ double
self.context.last_shift_time = now           # запоминаем время первого release
self._transition("shift_up_single")          # SHIFT_PRESSED → TYPING
return False
```

`is_double = False` → `_do_conversion()` **НЕ вызывается**.

**Состояние после:**
- State: `TYPING`
- `chars_in_buffer = 0` (ничего не набирали!)
- `_selection_valid = False`
- `_mouse_clicked_since_last_check = True`

#### Шаг 6 — Второй Shift press

**app.py:176:** `state_manager.on_shift_down()`  
→ transition: `TYPING → SHIFT_PRESSED`

#### Шаг 7 — Второй Shift release

**state_manager.py:47 `on_shift_up()`:**
```python
delta = now - self.context.last_shift_time   # малое значение (< 0.3с)
# delta < timeout → DOUBLE!
self.context.last_shift_time = 0
self._transition("shift_up_double")          # SHIFT_PRESSED → CONVERTING
return True
```

`is_double = True` → вызывается **`_do_conversion()`**

#### Шаг 8 — `_do_conversion()` (app.py:305)

```python
if self.state_manager.state != State.CONVERTING:
    return                                    # state == CONVERTING ✓
```

- `chars_in_buffer == 0` → `manual_word = ""` (пропуск user_dict логики)
- `_last_auto_marker is None` → пропуск Case A

**app.py:362:**
```python
self._check_selection_changed()             # ← ВЫЗОВ КЛЮЧЕВОЙ ФУНКЦИИ
```

#### Шаг 9 — `_check_selection_changed()` (app.py:273) — КОРЕНЬ БАГА

```python
info = self.selection.get_selection()
# info.text = "выделенный текст" (PRIMARY содержит текст)
# info.owner_id = <ID окна> (ненулевой)

if not info.text:            # False — текст есть
    ...

# >>> ЭТОТ БЛОК — КОРЕНЬ ПРОБЛЕМЫ <<<
if self._mouse_clicked_since_last_check:     # True! (установлен на шаге 1)
    self._mouse_clicked_since_last_check = False
    self._prev_sel_text = info.text          # обновляем baseline
    self._prev_sel_owner_id = info.owner_id  # обновляем baseline
    return False                             # ← ВОЗВРАЩАЕТ FALSE!
```

**`_check_selection_changed()` возвращает False** и НЕ устанавливает `_selection_valid = True`.

Логика этого блока: "после клика мыши обновить baseline, но НЕ помечать selection как свежий". Это было сделано для избежания race condition при чтении PRIMARY сразу после клика.

Но побочный эффект: при сценарии drag-select → Shift+Shift единственная проверка selection — именно эта, и она **всегда** возвращает False.

#### Шаг 10 — Обратно в `_do_conversion()` (app.py:365-380)

```python
saved_events = list(self.state_manager.context.event_buffer)   # = []
saved_count = self.state_manager.context.chars_in_buffer       # = 0
# _last_retype_events = [] → нет sticky buffer

success = self.conversion_engine.convert(
    self.state_manager.context,
    selection_valid=self._selection_valid,     # = False!
)
```

#### Шаг 11 — `choose_mode()` (conversion_engine.py:47)

```python
if context.backspace_hold_active:   # False
    return "selection"
if context.chars_in_buffer > 0:     # 0 — False
    return "retype"
if selection_valid:                  # False!
    return "selection"
return "retype"                     # ← FALLBACK: "retype"
```

→ Возвращает **"retype"**

#### Шаг 12 — `RetypeMode.execute()` (modes.py:76)

```python
if context.chars_in_buffer <= 0:
    logger.debug("RetypeMode: skip — chars_in_buffer=%d", context.chars_in_buffer)
    return False                    # ← ПРОПУСК — ничего не происходит
```

**Конец цепочки. Конвертация не выполнена.**

---

## 3. Корневая причина

### Механизм

`_check_selection_changed()` в app.py:290-293 содержит "baseline refresh" логику:

```python
if self._mouse_clicked_since_last_check:
    self._mouse_clicked_since_last_check = False
    self._prev_sel_text = info.text
    self._prev_sel_owner_id = info.owner_id
    return False    # ← НИКОГДА не помечает selection как valid!
```

Этот код был добавлен как фикс race condition (чтение PRIMARY через xclip сразу после клика в `_on_mouse_click` могло заставить selection owner сбросить PRIMARY в Cinnamon/GTK-приложениях). Решение: перенести чтение PRIMARY из `_on_mouse_click` на момент конвертации (Shift+Shift).

**Проблема:** при отложенном чтении PRIMARY (в `_check_selection_changed()`) код обновляет baseline, но **возвращает False**, не устанавливая `_selection_valid = True`. Это означает:

1. MOUSE_CLICK (button DOWN) → `_mouse_clicked_since_last_check = True`
2. Drag-select → PRIMARY обновляется (LSwitch не знает)
3. Shift+Shift → `_check_selection_changed()` → флаг True → baseline refresh → return **False**
4. `_selection_valid` остаётся **False** → `choose_mode()` → "retype" → skip

**Нет ни одного code path, который установил бы `_selection_valid = True`** в сценарии "mouse-select → Shift+Shift".

### Дополнительный нюанс: почему повторный Shift+Shift тоже не работает

После первого (неудачного) Shift+Shift:
- `_prev_sel_text` = выделенный текст (установлен baseline refresh'ем)
- `_prev_sel_owner_id` = id окна
- `_mouse_clicked_since_last_check = False`

При повторном Shift+Shift:
```python
# Сравнение с baseline
owner_changed = info.owner_id != self._prev_sel_owner_id   # False (то же окно)
text_changed = info.text != self._prev_sel_text             # False (тот же текст)
# → return False
```

Baseline совпадает → selection не fresh → `_selection_valid` не ставится → **тоже не работает**.

### Почему до фикса PRIMARY тоже не работало (по словам пользователя)

До фикса `_on_mouse_click()` вызывал `self.selection.get_selection()` и записывал результат в `_prev_sel_text`. При drag-select MOUSE_CLICK срабатывает при button DOWN (до начала drag), поэтому `_prev_sel_text` записывал ПРЕДЫДУЩЕЕ содержимое PRIMARY (того, что было ДО нового выделения). Тогда при Shift+Shift `_check_selection_changed()` видел бы изменение (`info.text != _prev_sel_text`) → **должен был работать**.

Если же не работало, возможная причина: в некоторых сценариях (click без drag, повторное выделение того же текста), baseline и текущий PRIMARY совпадали.

---

## 4. О MOUSE_CLICK и evdev событиях

### Когда генерируется MOUSE_CLICK

**event_manager.py:73-75:**
```python
if code in MOUSE_BUTTONS:
    if value == 1:    # value=1 → press only
        self.bus.publish(Event(EventType.MOUSE_CLICK, ...))
    return
```

- `BTN_LEFT press (value=1)` → MOUSE_CLICK **публикуется**
- `BTN_LEFT release (value=0)` → MOUSE_CLICK **НЕ публикуется**

Это значит:
- При **click** (нажал-отпустил): 1 событие MOUSE_CLICK (при нажатии)
- При **drag-select**: 1 событие MOUSE_CLICK (при начале drag, button DOWN)
- Button UP **никогда** не генерирует MOUSE_CLICK

### Следствие для drag-select

MOUSE_CLICK приходит в НАЧАЛЕ выделения, когда PRIMARY ещё содержит СТАРЫЙ текст. Новый текст попадает в PRIMARY только после button UP (когда X11 завершает выделение). LSwitch не получает никакого уведомления о завершении выделения.

---

## 5. Варианты решения

### Вариант A: Пометить selection valid в baseline-refresh блоке

**Изменение:** в `_check_selection_changed()`, когда `_mouse_clicked_since_last_check = True` и `info.text` непуст — установить `_selection_valid = True` и вернуть True.

```python
if self._mouse_clicked_since_last_check:
    self._mouse_clicked_since_last_check = False
    self._prev_sel_text = info.text
    self._prev_sel_owner_id = info.owner_id
    if info.text:                    # ← ДОБАВЛЕНО
        self._selection_valid = True
        return True
    return False
```

**Плюсы:**
- Минимальное изменение (2 строки)
- Сохраняет флаговый механизм
- Решает основной сценарий drag-select → Shift+Shift

**Минусы:**
- Если пользователь кликнул (deselect), но PRIMARY содержит стale текст от предыдущего выделения → ложное срабатывание (маловероятный сценарий)
- Флаговый механизм остаётся сложным для понимания
- Не защищает от stale PRIMARY контента (некоторые приложения не очищают PRIMARY при deselect)

### Вариант B: Сброс baseline на клике мыши, убрать флаг

**Изменение:** в `_on_mouse_click()` — сбросить baseline в пустые значения. В `_check_selection_changed()` — убрать проверку `_mouse_clicked_since_last_check`.

```python
# _on_mouse_click:
def _on_mouse_click(self, event):
    self._last_auto_marker = None
    self._selection_valid = False
    self._last_retype_events = []
    # Сброс baseline — любой непустой PRIMARY при Shift+Shift будет "новым"
    self._prev_sel_text = ""
    self._prev_sel_owner_id = 0
    self.state_manager.on_mouse_click()

# _check_selection_changed: убрать блок _mouse_clicked_since_last_check
```

**Плюсы:**
- Убирает сложность флагового механизма
- Чистая семантика: "после клика baseline = пусто, любой текст = новый"
- Не читает PRIMARY при клике (race condition не возникает)

**Минусы:**
- Stale PRIMARY по-прежнему может дать ложное срабатывание
- Если приложение не очищает PRIMARY при deselect, baseline="" → stale text ≠ "" → false positive
- Поле `_mouse_clicked_since_last_check` в `__init__` станет неиспользуемым (need cleanup)

### Вариант C: Двухфазная check — baseline + валидация owner

**Изменение:** при проверке в `_check_selection_changed()` использовать комбинацию: сброс baseline И проверку `owner_id != 0` (наличие активного владельца selection).

```python
if self._mouse_clicked_since_last_check:
    self._mouse_clicked_since_last_check = False
    self._prev_sel_text = info.text
    self._prev_sel_owner_id = info.owner_id
    # Если есть текст И есть живой owner → selection валидно
    if info.text and info.owner_id != 0:
        self._selection_valid = True
        return True
    return False
```

**Плюсы:**
- Минимальное изменение
- Дополнительная защита: `owner_id != 0` подтверждает, что selection владеет окно (не stale)
- Если пользователь кликнул и deselect'нул, а приложение корректно сбросило owner → owner_id = 0 → false positive не произойдёт

**Минусы:**
- Не все приложения корректно сбрасывают owner_id при deselect
- Флаговый механизм остаётся

---

## 5. Рекомендуемый вариант

### Вариант C — Baseline refresh + проверка owner_id

**Обоснование:**

1. **Минимальная инвазивность** — изменение 3 строк в одной функции
2. **Двойная проверка** (`info.text` + `info.owner_id != 0`) снижает риск ложных срабатываний при stale PRIMARY
3. **Сохраняет архитектуру** — флаговый механизм остаётся, что позволяет в будущем добавить дополнительные проверки
4. **Race condition по-прежнему предотвращён** — PRIMARY не читается в `_on_mouse_click()`, только при Shift+Shift

**Файл:** `lswitch/app.py`, функция `_check_selection_changed()`, строки ~290-293

**Строка изменения (текущий код):**
```python
if self._mouse_clicked_since_last_check:
    self._mouse_clicked_since_last_check = False
    self._prev_sel_text = info.text
    self._prev_sel_owner_id = info.owner_id
    return False
```

**Предлагаемый код:**
```python
if self._mouse_clicked_since_last_check:
    self._mouse_clicked_since_last_check = False
    self._prev_sel_text = info.text
    self._prev_sel_owner_id = info.owner_id
    if info.text and info.owner_id != 0:
        self._selection_valid = True
        return True
    return False
```

---

## Дополнительные наблюдения

### Навигационные клавиши/стрелки с Shift

Shift+Arrow (для выделения с клавиатуры) в текущем коде трактуется как ввод символа: `chars_in_buffer += 1`, `event_buffer.append(data)`. Это потенциально вызовет проблему при Shift+Shift после Shift+Arrow выделения (RetypeMode попытается "перепечатать" стрелки). Но это отдельный баг, не связанный с текущим исследованием.

### Повторный Shift+Shift после фикса

После применения фикса (вариант C), первый Shift+Shift сработает корректно (SelectionMode). При повторном Shift+Shift baseline уже равен текущему тексту → `_selection_valid` не установится → RetypeMode skip. Это **корректное поведение** (нет смысла конвертировать дважды без нового выделения).
