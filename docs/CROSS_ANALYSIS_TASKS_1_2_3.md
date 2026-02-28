# Кросс-анализ: Совместимость решений для Задач 1, 2, 3

> Ссылка на исходное исследование: [docs/RESEARCH_ISSUES.md](RESEARCH_ISSUES.md)
> Дата анализа: 28 февраля 2026

## Рекомендованные решения (резюме)

| Задача | Вариант | Суть | Файл / метод | Строки |
|--------|---------|------|-------------|--------|
| 1. Trailing space блокирует Shift+Shift | A | Пропуск trailing `KEY_SPACE` в `_extract_last_word_events()`: флаг `skipping_trailing_spaces`, при `True` и `KEY_SPACE` → `continue`, иначе → `break` | `app.py` / `_extract_last_word_events()` | ~644 |
| 2. Автоконвертация съедает пробел | D | `tap_key(KEY_SPACE)` в finally-блок с флагом `_space_sent` + `time.sleep(0.03)` перед replay | `app.py` / `_do_auto_conversion_at_space()` | ~678-731 |
| 3. Shift+Shift не отменяет автоконвертацию | A | Добавить `word_events` и `converted_len` в `_last_auto_marker` + явный undo в Case A `_do_conversion()` (backspace `converted_len+1`, switch back, replay, space) | `app.py` / `_do_auto_conversion_at_space()` (маркер) + `_do_conversion()` Case A (undo-блок) | ~719-726, ~454-466 |

---

## Анализ совместимости

### Задачи 2 + 3: модификация `_do_auto_conversion_at_space()`

Обе задачи модифицируют один и тот же метод `_do_auto_conversion_at_space()` ([app.py](../lswitch/app.py#L678-L731)), но **разные его части**:

**Задача 2** меняет **flow-control** метода:
- Добавляет `_space_sent = False` перед `try`
- Добавляет `time.sleep(0.03)` между `switch_layout()` и `replay_events()`
- Добавляет `_space_sent = True` после `tap_key(KEY_SPACE)` в `try`
- Добавляет условную отправку пробела в `finally` (`if not _space_sent`)

**Задача 3** меняет **только словарь маркера** в `finally`:
```python
self._last_auto_marker = {
    'word': orig_word,
    'direction': direction,
    'lang': orig_lang,
    'time': _time.time(),
    'word_events': list(word_events),    # ← Задача 3 (новое)
    'converted_len': len(word_events),   # ← Задача 3 (новое)
}
```

**Вердикт: СОВМЕСТИМЫ.** Изменения ортогональны — Задача 2 модифицирует try/except/finally-конструкцию и добавляет sleep, Задача 3 добавляет два поля в словарь маркера. Никаких пересечений.

Совмещённый вид метода после обоих фиксов:

```python
def _do_auto_conversion_at_space(self, word_len, word_events, direction, ...):
    ctx = self.state_manager.context
    _space_sent = False                                          # Задача 2

    try:
        # ... find target layout ...
        self.virtual_kb.tap_key(KEY_BACKSPACE, n_times=word_len + 1)
        if target and self.xkb:
            self.xkb.switch_layout(target=target)
        import time as _time_mod
        _time_mod.sleep(0.03)                                    # Задача 2
        self.virtual_kb.replay_events(word_events)
        self.virtual_kb.tap_key(KEY_SPACE)
        _space_sent = True                                       # Задача 2
    except Exception as exc:
        logger.error("Auto-conversion at space failed: %s", exc)
    finally:
        if not _space_sent:                                      # Задача 2
            try:
                self.virtual_kb.tap_key(KEY_SPACE)
            except Exception:
                pass
        import time as _time
        if orig_word:
            self._last_auto_marker = {
                'word': orig_word,
                'direction': direction,
                'lang': orig_lang,
                'time': _time.time(),
                'word_events': list(word_events),                # Задача 3
                'converted_len': len(word_events),               # Задача 3
            }
        ctx.reset()
        ctx.state = State.IDLE
```

### Задачи 1 + 3: trailing spaces и undo

**Задача 1** модифицирует `_extract_last_word_events()`.
**Задача 3** добавляет undo-блок в `_do_conversion()` Case A.

Undo-блок Задачи 3 **не вызывает** `_extract_last_word_events()` — он использует сохранённый `word_events` из маркера. Поэтому изменение поведения `_extract_last_word_events()` **не влияет на undo**.

**Вердикт: СОВМЕСТИМЫ.** Но есть тонкий нюанс (описан в разделе «Edge cases»).

### Задачи 1 + 2: trailing spaces и space в finally

**Задача 1** изменяет поведение при ручном Shift+Shift (путь, где auto-conversion НЕ произошла).
**Задача 2** изменяет поведение при автоконвертации (путь, где auto-conversion ПРОИЗОШЛА).

Эти два пути **взаимоисключающие** в рамках одного нажатия Space:
- Если auto-conversion произошла → `ctx.reset()`, буфер пуст, Space не попадает в буфер → Задача 1 не задействована
- Если auto-conversion не произошла → Space добавляется в буфер → Задача 2 не задействована

**Вердикт: СОВМЕСТИМЫ.** Нет сценария, где оба фикса активировались бы одновременно. Двойной пробел невозможен.

---

## ⚠️ КРИТИЧЕСКАЯ НАХОДКА: Задача 1 и backspace count при trim

### Проблема

Задача 1 (Вариант A) модифицирует `_extract_last_word_events()` — теперь метод пропускает trailing `KEY_SPACE` и возвращает только буквенные события слова. Это влияет на **trim-блок** в `_do_conversion()` ([app.py](../lswitch/app.py#L498-L510)):

```python
# Текущий trim-блок:
_, last_word_events = self._extract_last_word_events(...)
if last_word_events and len(last_word_events) < saved_count:
    saved_events = last_word_events
    saved_count = len(last_word_events)                           # ← ПРОБЛЕМА
    self.state_manager.context.event_buffer = list(last_word_events)
    self.state_manager.context.chars_in_buffer = saved_count
```

После Задачи 1, при буфере `[g, h, b, d, t, n, SPACE]` (7 элементов):
- `_extract_last_word_events()` → пропускает trailing SPACE → возвращает `[g,h,b,d,t,n]` (6 событий)
- `saved_count` становится **6**, `event_buffer` = **6 событий** (без пробела)

В `RetypeMode.execute()` ([modes.py](../lswitch/core/modes.py#L64-L113)):
```python
n_chars = context.chars_in_buffer   # 6
self.virtual_kb.tap_key(KEY_BACKSPACE, n_chars)  # 6 BS
# ...
self.virtual_kb.replay_events(saved_events)      # 6 events
```

Но **курсор в приложении** стоит на позиции **7** (после пробела)! 6 backspace'ов удаляют: `SPACE`, `n`, `t`, `d`, `b`, `h` → остаётся **`g`**. Затем replay 6 событий → **`gпривет`**.

### Демонстрация на конкретных данных

| Этап | Текст на экране | Курсор |
|------|----------------|--------|
| Исходное | `ghbdtn·` (trailing space) | pos 7 |
| BS ×6 | `g` | pos 1 |
| switch + replay ×6 | `gпривет` | pos 7 |

**Результат НЕКОРРЕКТЕН.** Первая буква `g` не удалена, конвертированный текст приписан к ней.

Для мульти-слова `[h,e,l,l,o,SPACE,g,h,b,d,t,n,SPACE]` ситуация аналогична — после trim и 6 BS: `hello·g` → replay → `hello·gпривет`.

### Рекомендуемая корректировка

**Задача 1 требует расширения:** не только пропуск trailing spaces в `_extract_last_word_events()`, но и **учёт trailing spaces в trim-блоке** `_do_conversion()`.

**Вариант fix-1A: включить trailing spaces в chars_in_buffer для BS, но НЕ в event_buffer для replay:**

```python
if last_word_events and len(last_word_events) < saved_count:
    # Подсчитать trailing spaces для корректного числа backspace
    trailing_spaces = 0
    for ev in reversed(saved_events):
        if ev.code == KEY_SPACE:
            trailing_spaces += 1
        else:
            break
    n_bs = len(last_word_events) + trailing_spaces
    saved_events = last_word_events
    saved_count = n_bs
    self.state_manager.context.event_buffer = list(last_word_events)
    self.state_manager.context.chars_in_buffer = n_bs
```

Тогда RetypeMode: `n_chars=7` BS (удаляет слово + пробел), replay 6 events (только слово) → `привет` (без trailing space).

**Вариант fix-1B: включить trailing spaces и в event_buffer:**

```python
if last_word_events and len(last_word_events) < saved_count:
    trailing = []
    for ev in reversed(saved_events):
        if ev.code == KEY_SPACE:
            trailing.append(ev)
        else:
            break
    trailing.reverse()
    trimmed = last_word_events + trailing
    saved_events = trimmed
    saved_count = len(trimmed)
    self.state_manager.context.event_buffer = list(trimmed)
    self.state_manager.context.chars_in_buffer = saved_count
```

Тогда RetypeMode: `n_chars=7` BS, replay 7 events (слово + пробел) → `привет·` (с trailing space).

**Рекомендую Вариант fix-1B** — он сохраняет trailing space, который пользователь намеренно набрал. Поведение последовательно: буфер содержит `[word..., SPACE]`, backspace удаляет столько же, replay восстанавливает столько же.

### Дополнительная находка: `_try_auto_conversion_at_space()` и множественные trailing spaces

С Задачей 1 метод `_extract_last_word_events()` будет пропускать trailing spaces **и в контексте автоконвертации**. Если в буфере есть trailing space (от предыдущего нажатия, когда autodetector сказал "нет"), и пользователь нажимает ещё один Space:

- **Без Задачи 1:** `_extract_last_word_events()` → trailing SPACE → `break` → пустое слово → auto-conv пропускается → Space добавляется в буфер
- **С Задачей 1:** trailing SPACE пропускается → слово найдено → autodetector вызывается повторно

В теории autodetector детерминистичен и снова ответит «нет». Но если `_do_auto_conversion_at_space()` всё-таки сработает, `word_len + 1` не учтёт trailing spaces в буфере + новый Space от приложения.

**Рекомендуемая защита:** в `_try_auto_conversion_at_space()`, после вызова `_extract_last_word_events()`, подсчитать trailing spaces. Если `trailing_spaces > 0`, пропустить автоконвертацию (слово уже было оценено на предыдущем пробеле):

```python
# В _try_auto_conversion_at_space(), после получения word:
trailing_spaces = 0
for ev in reversed(self.state_manager.context.event_buffer):
    if ev.code == KEY_SPACE:
        trailing_spaces += 1
    else:
        break
if trailing_spaces > 0:
    return False  # слово уже оценивалось на предыдущем пробеле
```

---

## Сквозные сценарии

### Сценарий 1: Набор `"ghbdtn·"` → НЕТ автоконвертации → Shift+Shift

> `·` обозначает пробел для наглядности.

**Буфер:** `[g, h, b, d, t, n, SPACE]`, `chars_in_buffer = 7`
**Текст на экране:** `ghbdtn·` (курсор на позиции 7)

| Шаг | Что происходит | Затронутые задачи |
|-----|---------------|-------------------|
| 1. Shift+Shift → `_do_conversion()` | FSM: IDLE→CONVERTING | — |
| 2. Case A: `_last_auto_marker` | `None` → пропускаем | (Задача 3 не задействована) |
| 3. Case B: `manual_word` | Задача 1: `_extract_last_word_events()` пропускает trailing SPACE → `"ghbdtn"` | Задача 1 ✅ |
| 4. `add_confirmation("ghbdtn", "en")` | weight +1 | — |
| 5. Trim: `_extract_last_word_events()` | Возвращает `[g,h,b,d,t,n]` (6 events). **С fix-1B:** trimmed = `[g,h,b,d,t,n,SPACE]` (7 events) | Задача 1 + fix ✅ |
| 6. `context.chars_in_buffer = 7` | 7 events (слово + trailing space) | fix-1B ✅ |
| 7. `RetypeMode.execute()` | 7 BS → удаляет `ghbdtn·` → экран пуст | — |
| 8. `switch_layout()` → RU | переключение | — |
| 9. `sleep(0.05)` | пауза RetypeMode | — |
| 10. `replay_events([g,h,b,d,t,n,SPACE])` | → `привет·` | — |

**Результат: `привет·`** — слово конвертировано, trailing space сохранён. ✅

Для мульти-слова `[h,e,l,l,o,SPACE,g,h,b,d,t,n,SPACE]`:
- Trim → `[g,h,b,d,t,n,SPACE]` (7 events)
- 7 BS из позиции 13: удаляет `·ntdbhg` → `hello·` (inter-word space сохранён)
- Replay → `hello·привет·`
✅

### Сценарий 2: Набор `"ghbdtn·"` → автоконвертация → `"привет·"` → Shift+Shift (undo)

| Шаг | Что происходит | Затронутые задачи |
|-----|---------------|-------------------|
| 1. Набор `"ghbdtn"` | Буфер `[g,h,b,d,t,n]`, chars=6. Экран: `ghbdtn` | — |
| 2. Space | Приложение получает Space → экран: `ghbdtn·` | — |
| 3. `_try_auto_conversion_at_space()` | `_extract_last_word_events()` → `"ghbdtn"`, 6 events (Space ещё НЕ в буфере) | Задача 1: нет trailing spaces → без изменений |
| 4. autodetector → `(True, reason)` | — | — |
| 5. `_do_auto_conversion_at_space(6, ...)` | **Задача 2:** `_space_sent = False` | Задача 2 |
| 6. `tap_key(BS, 7)` | 7 BS → экран: (пусто) | — |
| 7. `switch_layout(target=ru)` | OK | — |
| 8. `sleep(0.03)` | **Задача 2:** пауза 30мс | Задача 2 |
| 9. `replay_events([g,h,b,d,t,n])` | экран: `привет` | — |
| 10. `tap_key(KEY_SPACE)` | экран: `привет·`, `_space_sent = True` | Задача 2 |
| 11. `finally`: маркер | `{word_events: [6 events], converted_len: 6, ...}` | Задача 3 |
| 12. `ctx.reset()` | буфер пуст, chars=0, state=IDLE | — |
| 13. **Shift+Shift** → `_do_conversion()` | FSM: CONVERTING | — |
| 14. Case A: `_last_auto_marker` ≠ None | chars_in_buffer=0 → `add_correction("ghbdtn","en")` → weight -1 | Задача 3 ✅ |
| 15. Undo: `chars_in_buffer==0 AND word_events` | `n_delete = 6+1 = 7` | Задача 3 |
| 16. `tap_key(BS, 7)` | 7 BS → удаляет `привет·` → экран: (пусто) | — |
| 17. `switch_layout(target=en)` | Обратно на EN | Задача 3 |
| 18. `replay_events([g,h,b,d,t,n])` | экран: `ghbdtn` | Задача 3 |
| 19. `tap_key(KEY_SPACE)` | экран: `ghbdtn·` | Задача 3 |
| 20. `on_conversion_complete()`, return | Undo завершён | Задача 3 |

**Результат: `ghbdtn·`** — полный undo автоконвертации. ✅

### Сценарий 3: Автоконвертация → новый ввод `"мир"` → Shift+Shift

| Шаг | Что происходит | Затронутые задачи |
|-----|---------------|-------------------|
| 1-12 | Как в Сценарии 2: автоконвертация → `привет·`, буфер пуст, маркер установлен | — |
| 13. Набор `"мир"` | Буфер `[м,и,р]`, chars=3, layout=RU | — |
| 14. **Shift+Shift** → `_do_conversion()` | Case A: `_last_auto_marker` ≠ None | — |
| 15. **Задача 3 guard:** `chars_in_buffer=3 > 0` | НЕ вызываем `add_correction()` (пользователь принял конвертацию, набрав новый текст) | Задача 3 ✅ |
| 16. `_last_auto_marker = None` | Маркер очищен | Задача 3 |
| 17. Undo check: `chars_in_buffer==0`? | **НЕТ** (chars=3) → undo НЕ выполняется | Задача 3 ✅ |
| 18. Обычная конвертация | saved_events=[м,и,р], saved_count=3 | — |
| 19. Trim: `_extract_last_word_events()` | `"мир"` (3 events = saved_count) → trim не нужен | Задача 1: без эффекта |
| 20. `RetypeMode.execute()` | 3 BS → удаляет `мир`, switch RU→EN, replay → `vbh` (или эквивалент) | — |

**Результат:** `привет·vbh` — автоконвертация сохранена, новый текст конвертирован стандартным Shift+Shift. Маркер не привёл к ложному штрафу. ✅

---

## Edge cases на стыке решений

### Edge 1: Исключение в `switch_layout()` при автоконвертации + последующий Shift+Shift (undo)

**Сценарий:** `_do_auto_conversion_at_space()` → backspace удалил `"ghbdtn·"` → `switch_layout()` бросил Exception.

**Состояние после Задачи 2:**
- `_space_sent = False` → finally отправляет Space → экран: `·` (только пробел)
- Маркер **создан** (записан в finally безусловно) с полным `word_events`

**Shift+Shift (undo Задачи 3):**
- `chars_in_buffer = 0` → undo срабатывает
- `n_delete = 6 + 1 = 7` → 7 BS от позиции 1 (один пробел на экране)
- 1-й BS удаляет пробел → далее 6 BS **удаляют предыдущий текст пользователя!**

**⚠️ ОПАСНО.** Undo пытается удалить 7 символов, когда на экране от конвертации осталось только 1 (пробел). Это разрушает данные за пределами конвертации.

**Решение:** Маркер должен создаваться **только при успешной конвертации**:

```python
conversion_ok = False                                            # НОВОЕ
try:
    self.virtual_kb.tap_key(KEY_BACKSPACE, n_times=word_len + 1)
    if target and self.xkb:
        self.xkb.switch_layout(target=target)
    _time_mod.sleep(0.03)
    self.virtual_kb.replay_events(word_events)
    self.virtual_kb.tap_key(KEY_SPACE)
    _space_sent = True
    conversion_ok = True                                         # НОВОЕ
except Exception as exc:
    logger.error("Auto-conversion at space failed: %s", exc)
finally:
    if not _space_sent:
        try: self.virtual_kb.tap_key(KEY_SPACE)
        except Exception: pass
    if orig_word and conversion_ok:                              # ИЗМЕНЕНО: + conversion_ok
        self._last_auto_marker = { ... }
    ctx.reset()
    ctx.state = State.IDLE
```

**Следствие:** при ошибке маркер не создаётся → undo невозможен → но и не нужен (конвертация не завершена). Текст повреждён (слово удалено + пробел), но хотя бы undo не усугубит ситуацию.

### Edge 2: Trailing space в буфере + undo задачи 3: подсчёт символов

**Вопрос:** При undo задачи 3 пробел удаляется через `n_delete = len(word_events) + 1`. Если Задача 1 как-то изменила подсчёт trailing spaces — не нарушится ли?

**Ответ:** Undo НЕ ИСПОЛЬЗУЕТ `_extract_last_word_events()`. Он использует `marker['word_events']` напрямую. `word_events` записаны в маркер ДО `ctx.reset()` — это те же 6 событий, которые были переданы в `_do_auto_conversion_at_space()`. Trailing spaces из `_extract_last_word_events()` никогда не попадают в маркер.

`n_delete = 6 + 1 = 7` — ровно столько, сколько символов на экране (`привет·` = 6 букв + 1 пробел). **Корректно.** ✅

### Edge 3: Повторный Shift+Shift после undo

1. Автоконвертация → `привет·`, маркер установлен
2. Shift+Shift (undo) → `ghbdtn·`, маркер очищен, `on_conversion_complete()`, return
3. Shift+Shift снова → `_do_conversion()`:
   - `_last_auto_marker = None` → Case A пропущен
   - `chars_in_buffer = 0` (undo сделал return до convert)
   - `_last_retype_events = []` (не заполнен, т.к. undo сделал return)
   - `saved_count = 0` → RetypeMode → `chars_in_buffer <= 0` → return False

**Результат:** Ничего не происходит. ✅ Но пользователь мог бы ожидать «re-do» (обратно в `привет`). Это отдельная задача — не блокирует текущие фиксы.

### Edge 4: Автоконвертация в одну сторону + undo + сразу ручная конвертация

1. Набор `"ghbdtn·"` → автоконвертация → `"привет·"`
2. Shift+Shift → undo (Задача 3) → `"ghbdtn·"`, layout вернулся на EN
3. Пользователь сразу нажимает Shift+Shift ещё раз:
   - chars_in_buffer = 0, _last_auto_marker = None
   - Ничего не происходит (буфер пуст)

Пользователь ожидает конвертацию `"ghbdtn"` → `"привет"` через ручной Shift+Shift, но буфер был сброшен при undo. **Это ограничение**, но допустимое — пользователю нужно набрать текст заново или выделить его.

### Edge 5: `_uinput is None` при undo

Если `VirtualKeyboard._uinput = None`:
- `tap_key(BS)` → `_write()` → `return` (тихо)
- `replay_events()` → `_write()` → `return` (тихо)
- Undo «выполняется», но ничего не происходит на экране
- `привет·` остаётся, маркер очищен

**Не катастрофично**, но пользователь не увидит undo. Решение этой проблемы — отдельная архитектурная задача (проверка работоспособности UInput при запуске).

---

## Общая модель событий: таблица взаимодействий

```
                    _on_key_press(SPACE)
                         │
                    ┌────▼────┐
                    │auto_det?│
                    └─┬────┬──┘
                 yes  │    │  no
        ┌─────────────┘    └──────────────┐
        ▼                                 ▼
 _try_auto_conversion()          Space → event_buffer
        │                                 │
        ▼                                 │
 _do_auto_conversion()                    │
   │ BS(word+1)                           │
   │ switch_layout                        │
   │ sleep(0.03)      [Задача 2]          │
   │ replay_events                        │
   │ tap_key(SPACE)   [Задача 2: finally] │
   │ marker={word_events} [Задача 3]      │
   │ ctx.reset()                          │
   ▼                                      ▼
 IDLE                               buffer=[...word...,SPACE]
   │                                      │
   │ Shift+Shift                          │ Shift+Shift
   ▼                                      ▼
 _do_conversion()                  _do_conversion()
  Case A:                           Case B:
   marker? + chars==0?               extract_word (skip trailing SP) [Задача 1]
   │yes → undo [Задача 3]           add_confirmation
   │  BS(word+1)                     Trim (with trailing SP) [Задача 1 + fix]
   │  switch back                    RetypeMode.execute()
   │  replay orig
   │  space
   │no (chars>0)→
   │  clear marker
   │  Case B / normal
```

---

## Вердикт

### Совместимость

**Задачи 2 + 3:** ✅ Полностью совместимы. Ортогональные изменения в одном методе.

**Задачи 1 + 3:** ✅ Совместимы. Undo не использует `_extract_last_word_events()`.

**Задачи 1 + 2:** ✅ Совместимы. Взаимоисключающие пути исполнения.

### Необходимые корректировки

| # | Что | Почему | Сложность |
|---|-----|--------|-----------|
| 1 | **Задача 1: расширить trim-блок** — включать trailing spaces в trimmed buffer (Вариант fix-1B) | Без этого backspace удаляет trailing space вместо первой буквы слова → `gпривет` вместо `привет·` | ~8 строк |
| 2 | **Задача 1: guard в `_try_auto_conversion_at_space()`** — если в буфере trailing spaces, пропустить автоконвертацию | Предотвращает повторную оценку слова при множественных пробелах | ~5 строк |
| 3 | **Задачи 2+3: `conversion_ok` флаг** — маркер создавать только при успешной конвертации | При ошибке в switch_layout undo удалит чужой текст (7 BS при 1 символе на экране) | ~3 строки |

### Без этих корректировок

- Корректировка 1: **КРИТИЧНА** — без неё Задача 1 ломает retype при trailing space.
- Корректировка 2: **НИЗКИЙ приоритет** — требует маловероятного сценария (autodetector даёт разные ответы при повторном вызове).
- Корректировка 3: **СРЕДНИЙ приоритет** — защита от edge case (exception в switch_layout + немедленный Shift+Shift).

---

## Порядок реализации

### Рекомендуемая последовательность

```
Этап 1: Задача 2 (space в finally)
    │   Изолированное изменение в _do_auto_conversion_at_space()
    │   Можно протестировать независимо
    │   ~15 строк, 2 теста
    │
Этап 2: Задача 3 (undo автоконвертации)
    │   Расширяет маркер + добавляет undo в _do_conversion()
    │   Включить conversion_ok флаг (корректировка 3)
    │   ~25 строк, 4 теста
    │
Этап 3: Задача 1 (trailing spaces)
        Самое широкое изменение: _extract_last_word_events() + trim-блок + guard
        Включить корректировки 1 и 2
        ~20 строк, 5 тестов
```

### Обоснование порядка

1. **Задача 2 первая:** Самая изолированная. Не зависит от Задач 1 и 3. Добавляет safety net для пробела. Тестируется мгновенно: mock `switch_layout` → raise → проверить `tap_key(KEY_SPACE)` в finally.

2. **Задача 3 вторая:** Зависит от формата маркера (уже формируется в `_do_auto_conversion_at_space()`). Задача 2 к этому моменту уже стабилизировала finally-блок. Конверсия `conversion_ok` флага естественно вписывается в код Задачи 2. Тестируется: mock автоконвертацию → Shift+Shift → проверить backspace+replay+space.

3. **Задача 1 последняя:** Самое «широкое» изменение — затрагивает 4 места вызова `_extract_last_word_events()`. Trim-блок в `_do_conversion()` уже стабилен после Задач 2 и 3. Guard в `_try_auto_conversion_at_space()` не конфликтует с уже реализованными Задачами 2 и 3.

### Можно ли реализовать параллельно?

**Задачи 2 и 3** можно реализовать параллельно (разные неперекрывающиеся части `_do_auto_conversion_at_space()` + `_do_conversion()`), **НО** рекомендуется последовательно для упрощения code review и отладки.

**Задача 1** должна быть последней — она меняет общий метод `_extract_last_word_events()`, от которого зависит и автоконвертация, и ручная конвертация, и debug_monitor.

### Чеклист для каждого этапа

#### Этап 1 (Задача 2)
- [ ] Добавить `_space_sent = False` перед try
- [ ] Добавить `time.sleep(0.03)` между switch и replay
- [ ] Добавить `_space_sent = True` после `tap_key(KEY_SPACE)` в try
- [ ] Добавить условную отправку Space в finally
- [ ] `pytest tests/test_auto_convert.py -q`
- [ ] Обновить `test_context_reset_on_exception`

#### Этап 2 (Задача 3)
- [ ] Добавить `conversion_ok = False` перед try
- [ ] Установить `conversion_ok = True` после полного успеха
- [ ] Маркер: добавить `word_events` и `converted_len`
- [ ] Маркер: создавать только при `conversion_ok`
- [ ] `_do_conversion()` Case A: guard `chars_in_buffer == 0` для `add_correction`
- [ ] `_do_conversion()` Case A: undo-блок (if chars==0 and word_events)
- [ ] `pytest tests/ -q`
- [ ] Новые тесты: undo сразу, undo с новым текстом, undo при пустом marker

#### Этап 3 (Задача 1)
- [ ] `_extract_last_word_events()`: добавить `skipping_trailing_spaces` логику
- [ ] Trim-блок в `_do_conversion()`: включить trailing spaces в trimmed buffer (fix-1B)
- [ ] Guard в `_try_auto_conversion_at_space()`: skip если trailing_spaces > 0
- [ ] `pytest tests/ -q`
- [ ] Новые тесты: буфер с trailing space, мульти-слово+trailing space, только пробелы
