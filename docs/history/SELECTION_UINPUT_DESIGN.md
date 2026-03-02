# SelectionMode через UInput — дизайн

**Дата:** 27 февраля 2026  
**Статус:** обсуждение, не реализовано

---

## Проблема

Текущий `SelectionMode` работает через CLIPBOARD:

```python
# replace_selection():
old_clip = get_clipboard("clipboard")     # 1. Сохранить
set_clipboard(new_text, "clipboard")      # 2. Записать конвертированный текст
time.sleep(0.02)
xdotool_key("ctrl+v")                    # 3. Вставить
time.sleep(0.05)
set_clipboard(old_clip, "clipboard")     # 4. Восстановить
```

### Последствия

1. **CLIPBOARD портится** — clipboard manager (Cinnamon) перехватывает каждый
   `set_clipboard` и добавляет в историю. Даже после восстановления в истории
   лежит мусор.

2. **Race condition** — 50ms между `ctrl+v` и восстановлением недостаточно.
   Если приложение не успело прочитать — вставляется `old_clip`. Если успело,
   но clipboard manager нет — история всё равно засоряется.

3. **Не работает в терминале** — `ctrl+v` в терминале вставляет литерал `^V`.
   Только `ctrl+shift+v` работает в большинстве терминалов, и то не везде.

4. **Исключение при восстановлении** — если `set_clipboard(old_clip)` упадёт,
   CLIPBOARD навсегда содержит конвертированный текст.

---

## Решение: UInput (как в RetypeMode)

`RetypeMode` уже работает правильно — использует UInput (ядерный уровень):

```
1. N × Backspace  →  UInput → kernel → приложение
2. switch_layout()
3. replay_events([keycodes...])  →  UInput → kernel → приложение
```

**UInput работает везде**: терминалы, GTK, Qt, браузеры, IDE.
CLIPBOARD не трогается вообще.

Для SelectionMode нужен только обратный маппинг `char → keycode`, который
тривиально строится из уже существующего `KEYCODE_TO_CHAR_EN`.

---

## Новый алгоритм SelectionMode

```
1. PRIMARY = "ghbdtn"  (прочитали, определили язык)
2. convert("ghbdtn", "en_to_ru") → "привет"
3. BACKSPACE × len("ghbdtn") = 6  →  UInput  (удалить выделенное)
4. switch_layout() → RU
5. для каждого char в "привет":
       keycode = char_to_keycode_ru(char)   # 'п'→34, 'р'→35, ...
       UInput.tap(keycode)
6. CLIPBOARD не трогается
```

### Откуда берётся `len(original)`

SelectionMode читает PRIMARY ДО конвертации, поэтому длина исходного текста
всегда известна.

---

## Что нужно реализовать

### 1. `key_mapper.py` — добавить `char_to_keycode`

```python
# Обратный маппинг из существующего KEYCODE_TO_CHAR_EN
CHAR_TO_KEYCODE_EN: dict[str, int] = {v: k for k, v in KEYCODE_TO_CHAR_EN.items()}

def char_to_keycode(char: str, layout: str = "en") -> tuple[int, bool] | None:
    """Return (keycode, shifted) for char in given layout, or None if unknown.

    Examples (EN layout):
        'g' → (34, False)
        'G' → (34, True)   ← shifted
        ' ' → (57, False)

    Examples (RU layout via EN_TO_RU inverse):
        'п' → (34, False)   ← same keycode as 'g', just in RU layout
        'П' → (34, True)
    """
    lower = char.lower()
    is_upper = char != lower
    # EN layout: direct lookup
    if layout == "en":
        kc = CHAR_TO_KEYCODE_EN.get(lower)
        return (kc, is_upper) if kc else None
    # RU layout: inverse of EN_TO_RU table
    if layout == "ru":
        from lswitch.intelligence.maps import RU_TO_EN
        en_char = RU_TO_EN.get(lower)
        if en_char:
            kc = CHAR_TO_KEYCODE_EN.get(en_char)
            return (kc, is_upper) if kc else None
    return None
```

### 2. `VirtualKeyboard` — добавить `type_text`

```python
def type_text(self, text: str, layout: str = "en") -> list[str]:
    """Type text by replaying keycodes. Returns list of chars that failed.

    Uses char_to_keycode() for each character. Characters not in the
    keymap are skipped and returned as failures.
    """
    from lswitch.input.key_mapper import char_to_keycode
    failed = []
    for char in text:
        result = char_to_keycode(char, layout)
        if result is None:
            failed.append(char)
            continue
        keycode, shifted = result
        if shifted:
            self._write(self.KEY_LEFTSHIFT, 1)
            time.sleep(self.KEY_PRESS_DELAY)
        self.tap_key(keycode)
        if shifted:
            self._write(self.KEY_LEFTSHIFT, 0)
        time.sleep(self.KEY_REPEAT_DELAY)
    return failed
```

### 3. `SelectionMode.execute()` — заменить replace_selection

```python
def execute(self, context: "StateContext") -> bool:
    sel = self.selection.get_selection()
    if not sel.text:
        return False

    source_lang = detect_language(sel.text)
    target_lang = "ru" if source_lang == "en" else "en"
    direction = "en_to_ru" if source_lang == "en" else "ru_to_en"

    converted = convert_text(sel.text, direction)
    if not converted:
        return False

    # 1. Delete selected text (by length)
    n_delete = len(sel.text)
    self.virtual_kb.tap_key(KEY_BACKSPACE, n_delete)

    # 2. Switch layout
    self.xkb.switch_layout(target=target_lang)
    time.sleep(0.05)

    # 3. Type converted text via UInput — no CLIPBOARD involved
    failed = self.virtual_kb.type_text(converted, layout=target_lang)
    if failed:
        logger.warning("SelectionMode: could not type chars: %r", failed)
        # fallback: clipboard paste for characters outside keymap
        # (rare case: emoji, special symbols)

    return True
```

---

## Краевые случаи

| Случай | Обработка |
|--------|-----------|
| Символ не в карте (emoji, спецсимволы) | `type_text()` возвращает failed-список; fallback на `xdotool type` для этих символов |
| Пробелы и цифры | `KEYCODE_TO_CHAR_EN` уже содержит пробел (57) и цифры (2–11) |
| Знаки препинания | Большинство есть в карте; редкие символы → fallback |
| Длинный текст (>200 символов) | UInput работает быстро (~8ms/символ), 200 символов ≈ 1.6 сек — приемлемо |
| Терминалы | UInput работает, Ctrl+V проблем нет — это главный выигрыш |

---

## Сравнение подходов

| | Текущий (CLIPBOARD) | Новый (UInput) |
|---|---|---|
| Работает в терминале | ❌ | ✅ |
| Портит CLIPBOARD | ❌ | ✅ нет |
| Clipboard history загрязнение | ❌ | ✅ нет |
| Race condition | ❌ | ✅ нет |
| Зависит от приложения | ❌ (Ctrl+V) | ✅ kernel-level |
| Скорость | ~50ms overhead | ~8ms/char |
| Сложность реализации | Простая | Умеренная |

---

## Единая модель

Оба режима после рефакторинга будут работать одинаково:

```
RetypeMode:   N×BS → switch_layout → replay_events(saved_keycodes)
SelectionMode: N×BS → switch_layout → type_text(converted_chars)
```

Разница только в источнике символов: keycodes из event_buffer vs char→keycode из текста.
