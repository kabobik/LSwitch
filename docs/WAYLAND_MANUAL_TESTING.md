# Wayland manual testing guide

Этот файл - пошаговый чеклист ручного тестирования LSwitch на KDE Wayland.
Он нужен для тонкой проверки поведения после того, как базовая диагностика
`lswitch --diagnose-wayland-switch-test` уже проходит.

Целевая среда MVP:

- KDE Plasma Wayland;
- layouts: `us`, `ru`;
- запуск из проекта через `.venv/bin/python`;
- `evdev`, `pyudev`, `PyQt6` установлены в том Python, которым запускается
  приложение;
- пользователь имеет доступ к `/dev/input/event*` и `/dev/uinput`.

## 1. Что сейчас отправляет `Ctrl+C`

На Wayland `Ctrl+C` отправляется только через `WaylandSelectionAdapter`.
Технически это вызов `selection.get_selection()`: адаптер сохраняет текущий
clipboard, отправляет `ctrl+c`, ждет изменения clipboard и возвращает
скопированный текст.

Текущие входы в `selection.get_selection()`:

1. `SelectionMode` без expand:
   - выбирается, когда `chars_in_buffer == 0` и `selection_valid == True`;
   - на Wayland штатный poller/mouse-release tracking отключены, поэтому этот
     путь обычно не должен включаться сам.

2. `selection_expand` fallback:
   - выбирается при Double Shift, если `chars_in_buffer == 0`,
     `selection_valid == False`, `backspace_hold_active == False`;
   - сначала отправляет `ctrl+shift+Left`, потом `ctrl+c`;
   - это главный ожидаемый источник `ctrl+c` при Double Shift на пустом буфере.

3. Backspace-hold selection mode:
   - удержать Backspace до `backspace_hold_active`, затем Double Shift;
   - тоже идет через `expand_selection_to_word()`: `ctrl+shift+Left`, затем
     `ctrl+c`.

4. Baseline update после conversion:
   - на X11 baseline чтение нужно для PRIMARY selection tracking;
   - на KDE Wayland passive tracking отключен, поэтому retype conversion не
     должен вызывать `selection.get_selection()` и не должен отправлять `ctrl+c`
     после `RetypeMode`;
   - если после обычного retype снова виден `ctrl+c`, это регрессия.

5. User dictionary learning для selection:
   - если `user_dict_enabled == true`, `chars_in_buffer == 0`,
     `selection_valid == True`, `_last_auto_marker is None`;
   - перед конвертацией читает selection для обучения;
   - на Wayland обычно не должен срабатывать без fresh-selection флага.

6. Debug Monitor:
   - если открыть Debug Monitor из tray, его внутренний selection poller вызывает
     `app.selection.get_selection()` каждые 500 ms;
   - на Wayland это будет периодически отправлять `ctrl+c`;
   - для тестов спама `ctrl+c` Debug Monitor лучше держать закрытым.

`Auto-conversion на Space` не использует `ctrl+c`: там путь через backspace,
layout switch, replay events и отложенный space.

## 2. Подготовка запуска

Проверить зависимости именно в используемом Python:

```bash
.venv/bin/python -c "import evdev, pyudev, PyQt6; print('ok')"
```

Проверить Wayland/KDE backend:

```bash
.venv/bin/python -m lswitch --diagnose-wayland-switch-test
```

Ожидаемые ключевые строки:

```text
[ok] session: wayland
[ok] compositor: kde
[ok] D-Bus methods: ... setLayout(u)->b ...
[ok] switch test switch: ... via setLayout(uint32)
[ok] switch test restore: ... via setLayout(uint32)
```

Запуск для ручных тестов:

```bash
.venv/bin/python -m lswitch --replace --debug
```

Для максимально подробного разбора:

```bash
.venv/bin/python -m lswitch --replace --trace
```

Важные лог-маркеры:

- `LSwitch 2.0 запущен ... N устройств`;
- `DoubleShift detected -> _do_conversion() [sel_valid=..., chars=...]`;
- `DoConversion: selection_valid=..., chars_in_buffer=...`;
- `choose_mode: ... -> retype|selection|selection_expand`;
- `Converting in mode: ...`;
- `RetypeMode: start`;
- `SelectionMode: expanding selection...`;
- `VirtualKeyboard: send_combo sequence=ctrl+c`;
- `VirtualKeyboard: send_combo sequence=ctrl+v`;
- `Auto-convert at space: ...`;
- `Wayland selection replace failed: ...`.

## 3. Базовый startup

Что сделать:

1. Запустить `.venv/bin/python -m lswitch --replace --debug`.
2. Не нажимать клавиши 5 секунд.
3. Проверить tray icon.
4. Закрыть Debug Monitor, если он открыт.

Ожидать:

- в логе есть `LSwitch 2.0 запущен`;
- количество устройств больше `0`;
- нет повторяющихся `ctrl+c`;
- нет warnings `No module named 'evdev'`, `evdev not available`,
  `pyudev not installed`;
- если устройств `0`, дальнейшие keyboard tests невалидны.

## 4. Auto-conversion на Space

EN -> RU:

1. Переключить систему на EN.
2. В любом текстовом поле набрать `ghbdtn`.
3. Нажать Space.

Ожидать:

- текст становится `привет `;
- layout переключается на RU;
- в логе есть `Auto-convert at space: 'ghbdtn' -> en_to_ru`;
- не должно быть `send_combo sequence=ctrl+c`.

RU -> EN:

1. Переключить систему на RU.
2. Набрать `руддщ`.
3. Нажать Space.

Ожидать:

- текст становится `hello `;
- layout переключается на EN;
- в логе есть `Auto-convert at space: 'руддщ' -> ru_to_en`;
- не должно быть `ctrl+c`.

Negative case:

1. На EN набрать нормальное слово `hello`.
2. Нажать Space.

Ожидать:

- текст остается `hello `;
- нет auto-conversion;
- нет `ctrl+c`.

## 5. Manual Retype через Double Shift

EN -> RU:

1. Переключить систему на EN.
2. Набрать `ghbdtn`.
3. Быстро нажать Shift, отпустить, еще раз Shift, отпустить.

Ожидать:

- текст становится `привет`;
- layout переключается на RU;
- в логе:
  - `DoubleShift detected ... chars=6`;
  - `choose_mode: chars_in_buffer=6 > 0 -> retype`;
  - `RetypeMode: start`;
- не должно быть `send_combo sequence=ctrl+c` после `RetypeMode: done`.

RU -> EN:

1. Переключить систему на RU.
2. Набрать `руддщ`.
3. Double Shift.

Ожидать:

- текст становится `hello`;
- layout переключается на EN;
- логи аналогичны `RetypeMode`.

Проверка last-word trimming:

1. На EN набрать `test ghbdtn`.
2. Double Shift.

Ожидать:

- меняется только последнее слово: `test привет`;
- первое слово не удаляется.

## 6. Sticky repeat Double Shift

Что сделать:

1. На EN набрать `ghbdtn`.
2. Double Shift -> получить `привет`.
3. Не печатать ничего нового.
4. Еще раз Double Shift.
5. Еще раз Double Shift.

Ожидать:

- текст чередуется `ghbdtn` <-> `привет`;
- в логе видно восстановление sticky buffer:
  `DoConversion: restored sticky buffer`;
- если после второго/третьего Double Shift начинается серия `ctrl+c`, отметить
  точное значение `chars=` и `choose_mode`.

## 7. Empty-buffer Double Shift

Этот тест проверяет основной подозреваемый источник лишнего `ctrl+c`.

Что сделать:

1. Поставить курсор в пустое текстовое поле.
2. Не печатать символы.
3. Нажать Double Shift один раз.
4. Повторить 3-5 раз с паузой 1 секунда.

Ожидать по текущей реализации:

- `chars=0`;
- `choose_mode: fallback -> selection_expand`;
- `SelectionMode: expanding selection...`;
- отправляется `ctrl+shift+Left`, затем `ctrl+c`;
- если выделять нечего, конвертация не должна менять текст;
- не должно быть дополнительного baseline `ctrl+c` после завершения conversion.

Нежелательно:

- `ctrl+c` продолжает идти сам после прекращения Double Shift;
- `ctrl+c` идет чаще, чем количество сделанных Double Shift;
- активное приложение теряет clipboard без явной selection conversion.

## 8. Selection conversion

Подготовка clipboard restore:

1. Скопировать в clipboard строку `CLIPBOARD_SENTINEL`.
2. В другом месте вставить ее и убедиться, что clipboard содержит sentinel.

Mouse selection:

1. В текстовом поле написать `ghbdtn`.
2. Мышью выделить ровно `ghbdtn`.
3. Нажать Double Shift.

Ожидать:

- выделенный текст заменяется на `привет`;
- layout переключается на RU;
- в логе есть `SelectionMode`;
- есть `ctrl+c` и `ctrl+v`;
- после операции clipboard снова содержит `CLIPBOARD_SENTINEL`.

Keyboard selection:

1. Написать `ghbdtn`.
2. Выделить слово через Shift+Arrow.
3. Double Shift.

Ожидать:

- поведение как выше;
- если вместо выделения сработал `selection_expand`, записать лог `choose_mode`.

Проверить в разных приложениях:

- Kate/KWrite или другой Qt editor;
- Firefox/Chromium;
- VS Code/Electron;
- terminal editor, где `Ctrl+C` может иметь специальное значение.

## 9. Backspace-hold selection mode

Что сделать:

1. В поле написать или выделить слово `ghbdtn`.
2. Удерживать Backspace до auto-repeat минимум 3 повторов.
3. Быстро нажать Double Shift.

Ожидать:

- `backspace_hold_active=True`;
- `choose_mode: backspace_hold_active=True -> selection`;
- `SelectionMode: expanding selection...`;
- отправляется `ctrl+shift+Left`, затем `ctrl+c`;
- если есть выделяемое слово, оно конвертируется и вставляется через `ctrl+v`.

Нежелательно:

- Backspace удаляет слишком много текста до начала conversion;
- после отпускания Backspace следующие Double Shift продолжают думать, что
  `backspace_hold_active=True`.

## 10. Debug Monitor и `ctrl+c` spam

Что сделать:

1. Запустить GUI mode с tray.
2. Открыть Debug Monitor из tray menu.
3. Ничего не нажимать 3-5 секунд.
4. Закрыть Debug Monitor.

Ожидать по текущей реализации:

- пока Debug Monitor открыт, каждые примерно 500 ms может появляться
  `VirtualKeyboard: send_combo sequence=ctrl+c`;
- после закрытия Debug Monitor spam должен прекратиться.

Если это подтверждается, Debug Monitor на Wayland нужно менять: не poll-ить
selection через active `Ctrl+C` flow, либо показывать selection panel disabled.

## 11. Clipboard restore

Что сделать:

1. Скопировать `CLIPBOARD_SENTINEL`.
2. Выполнить selection conversion из раздела 8.
3. После conversion в новом месте нажать Ctrl+V вручную.

Ожидать:

- вставляется `CLIPBOARD_SENTINEL`, а не converted text;
- если вставляется converted text, restore timing не сработал.

Повторить в:

- Qt editor;
- browser input;
- VS Code;
- terminal.

## 12. Headless mode

Запуск:

```bash
.venv/bin/python -m lswitch --headless --replace --debug
```

Проверить:

- нет tray icon;
- приложение все равно стартует с Qt runtime на Wayland;
- `Auto-conversion на Space` работает;
- `RetypeMode` работает;
- `SelectionMode` работает так же, как в GUI;
- нет Debug Monitor polling, значит не должно быть monitor-induced `ctrl+c`.

## 13. Stop criteria для `ctrl+c` проблемы

Считать баг подтвержденным, если выполняется хотя бы одно:

- `ctrl+c` идет без Double Shift, без selection conversion и без открытого
  Debug Monitor;
- после закрытия Debug Monitor `ctrl+c` продолжает идти каждые 0.5-1 сек;
- обычный `RetypeMode` с `chars_in_buffer > 0` ломает clipboard или активное
  приложение из-за baseline `ctrl+c`;
- empty-buffer Double Shift отправляет больше одного copy-flow на один жест.

Для отчета сохранить 20-40 строк лога вокруг события с `--debug` или `--trace`,
включая строки:

- `DoubleShift detected`;
- `DoConversion`;
- `choose_mode`;
- `Converting in mode`;
- `SelectionMode`;
- все `send_combo sequence=ctrl+c`;
- все `send_combo sequence=ctrl+v`.

## 14. Короткая таблица результатов

| Сценарий | Ожидание | Статус | Заметки |
|----------|----------|--------|---------|
| Startup GUI | N устройств, нет idle `ctrl+c` |  |  |
| KDE diagnostics | `via setLayout(uint32)` |  |  |
| Auto EN->RU Space | `ghbdtn ` -> `привет `, без `ctrl+c` |  |  |
| Auto RU->EN Space | `руддщ ` -> `hello `, без `ctrl+c` |  |  |
| Manual Retype EN->RU | `ghbdtn` -> `привет` |  |  |
| Manual Retype RU->EN | `руддщ` -> `hello` |  |  |
| Sticky repeat | Чередование текста |  |  |
| Empty-buffer Double Shift | Нет бесконечного `ctrl+c` |  |  |
| Mouse selection | Selection conversion + clipboard restore |  |  |
| Keyboard selection | Selection conversion + clipboard restore |  |  |
| Backspace hold | Selection mode only while gesture active |  |  |
| Debug Monitor | `ctrl+c` только пока окно открыто |  |  |
| Headless | Без tray, основные сценарии работают |  |  |
