# LSwitch 2.0 — план работы

Статусы: `[ ]` не начато · `[~]` в работе · `[x]` готово · `[!]` требует решения

---

## Этап 1: Intelligence Layer (словари и данные)

> Нет зависимостей от X11/evdev — можно разрабатывать и тестировать без железа.

- [x] **1.1** Перенести словарные данные из `archive/lswitch/dictionary.py`
  - Заполнить `lswitch/intelligence/ru_words.py` → `RUSSIAN_WORDS: set[str]`
  - Заполнить `lswitch/intelligence/en_words.py` → `ENGLISH_WORDS: set[str]`
  - Написать тест: `tests/test_dictionary_service.py`

- [x] **1.2** Перенести N-граммы из `archive/lswitch/ngrams.py`
  - Заполнить `lswitch/intelligence/bigrams.py` → `BIGRAMS_RU`, `BIGRAMS_EN`
  - Заполнить `lswitch/intelligence/trigrams.py` → `TRIGRAMS_RU`, `TRIGRAMS_EN`
  - Написать тест: `tests/test_ngram_analyzer.py`
    - Проверить что "ghbdtn" получает высокий RU-score после конвертации
    - Проверить что "привет" получает низкий EN-score

- [x] **1.3** Интеграционный тест автоопределения
  - `lswitch/intelligence/auto_detector.py` → `AutoDetector` (dict + ngram pipeline)
  - `tests/test_auto_detect.py` — 11 тестов, все проходят
  - Сценарий: `should_convert("ghbdtn", "en")` → `True`
  - Сценарий: `should_convert("hello", "en")` → `False`

---

## Этап 2: Platform Layer (X11 адаптеры)

> Требует X11. Разработка на живой системе, мок-адаптеры для тестов уже в `conftest.py`.

- [x] **2.1** Реализовать `XKBAdapter` (конкретная реализация интерфейса)
  - Файл: `lswitch/platform/xkb_adapter.py` → класс `X11XKBAdapter(IXKBAdapter)`
  - Источник: `archive/lswitch/xkb.py` + XKB-блок из `archive/lswitch/core.py`
  - Методы: `get_layouts()`, `get_current_layout()`, `switch_layout()`, `keycode_to_char()`
  - Написать тест с `MockXKBAdapter` из conftest: `tests/test_xkb_adapter.py`

- [x] **2.2** Реализовать `X11SelectionAdapter(ISelectionAdapter)`
  - Файл: `lswitch/platform/selection_adapter.py`
  - Источник: `archive/lswitch/selection.py`
  - Ключевое исправление: использовать `owner_id + text + timestamp` (баг v1)
  - Написать тест: `tests/test_selection_adapter.py`
    - `has_fresh_selection()` возвращает `True` при повторном выделении того же текста

- [x] **2.3** Написать тест `SubprocessSystemAdapter`
  - Файл: `tests/test_system_adapter.py`
  - Проверить `run_command` с таймаутом, `get_clipboard` падает gracefully

---

## Этап 3: Input Layer (устройства ввода)

> Требует evdev. Мокаем evdev в тестах.

- [ ] **3.1** Перенести `DeviceManager`
  - Файл: `lswitch/input/device_manager.py`
  - Источник: `archive/lswitch/device_manager.py` (помечен как "хороший")
  - Адаптировать: убрать зависимость от `LSwitch`-инстанса, принимать callback
  - Написать тест: `tests/test_device_manager.py`

- [ ] **3.2** Реализовать `UdevMonitor`
  - Файл: `lswitch/input/udev_monitor.py`
  - Источник: udev-монитор из `archive/lswitch/device_manager.py`
  - Написать тест с моком udev

- [ ] **3.3** Протестировать `VirtualKeyboard`
  - Файл: `tests/test_virtual_keyboard.py`
  - Мок `evdev.UInput`, проверить что `tap_key` пишет press+release
  - Проверить что `replay_events` не падает на пустом списке

---

## Этап 4: Core Layer (бизнес-логика)

> Чистый Python, хорошо тестируется. Самый важный этап.

- [ ] **4.1** Реализовать `RetypeMode`
  - Файл: `lswitch/core/modes.py`
  - Логика: delete N chars → switch layout → replay events
  - Ключевое исправление: Shift release отправлять **только если были Shift press** в буфере
  - Написать тест: `tests/test_retype_mode.py`

- [ ] **4.2** Реализовать `SelectionMode`
  - Файл: `lswitch/core/modes.py`
  - Логика: get_selection → convert → replace_selection
  - Написать тест: `tests/test_selection_mode.py`
    - Повторное выделение того же текста конвертируется корректно

- [ ] **4.3** Реализовать `ConversionEngine.convert()`
  - Файл: `lswitch/core/conversion_engine.py`
  - Логика выбора режима: backspace_hold / has_fresh_selection / chars_in_buffer
  - Написать тест: `tests/test_conversion_engine.py`
    - Сценарий retype: "ghbdtn" → "привет"
    - Сценарий selection: выделенный текст конвертируется
    - Сценарий auto-convert: словарь распознаёт и конвертирует

- [ ] **4.4** Реализовать `EventManager.handle_raw_event()`
  - Файл: `lswitch/core/event_manager.py`
  - Источник: `archive/lswitch/input.py`
  - Написать тест: `tests/test_event_manager.py`
    - Shift press → KEY_PRESS событие в шину
    - Навигационная клавиша → MOUSE_CLICK / navigation событие

- [ ] **4.5** Интеграция EventManager + StateManager + ConversionEngine
  - Написать интеграционный тест: `tests/test_core_integration.py`
  - Сценарий: двойной Shift → конвертация → IDLE
  - Сценарий: двойной Shift во время is_converting → игнорируется

---

## Этап 5: Application (точка входа)

- [ ] **5.1** Реализовать `LSwitchApp.run()`
  - Файл: `lswitch/app.py`
  - `headless=True`: event loop без UI
  - `headless=False`: event loop + tray icon в отдельном потоке

- [ ] **5.2** Настроить конфиг
  - Файл: `lswitch/config.py` (новый, на основе `archive/lswitch/config.py`)
  - Единый путь: `~/.config/lswitch/config.json`
  - Использовать `persistence.save_json` для записи

- [ ] **5.3** Протестировать CLI
  - `tests/test_cli.py`: `--headless`, `--debug`, `--version`

---

## Этап 6: UI Layer (tray + config)

> Последний этап, зависит от Qt.

- [ ] **6.1** Реализовать `TrayIcon`
  - `lswitch/ui/tray_icon.py`
  - Источник: `archive/lswitch_control.py`
  - Показывать текущую раскладку, статус auto_switch

- [ ] **6.2** Реализовать `ContextMenu`
  - Toggle auto_switch, открыть ConfigDialog, Quit

- [ ] **6.3** Реализовать `ConfigDialog`
  - Все настройки из config.json видны и редактируемы
  - Изменения применяются через EventBus немедленно

- [ ] **6.4** Реализовать `CinnamonAdapter`
  - Источник: кастомное меню из `archive/lswitch_control.py`

---

## Этап 7: Перенос данных (низкий приоритет)

- [ ] **7.1** Перенести i18n из `archive/lswitch/i18n.py`
- [ ] **7.2** Написать `tests/test_integration_full.py` — сквозной тест

---

## Лишнее в корне (не удаляется — нет прав)

| Файл/папка | Статус | Действие |
|------------|--------|----------|
| `lswitch.egg-info/` | В `.gitignore` | Игнорируем |
| `__pycache__/` | В `.gitignore` | Игнорируем |
| `setup.py` | Оставить | Обновить для v2 на этапе 5 |
| `requirements.txt` | Оставить | Обновить на этапе 5 |
| `Makefile` | Оставить | Обновить команды |

---

## Текущее состояние (baseline)

```
25 tests passed  ✓  (event_bus, state_manager, text_converter, persistence, user_dictionary)
```

Готовые модули (реализованы, тесты зелёные):
- `lswitch/core/event_bus.py`
- `lswitch/core/events.py`
- `lswitch/core/states.py`
- `lswitch/core/transitions.py`
- `lswitch/core/state_manager.py`
- `lswitch/core/text_converter.py`
- `lswitch/intelligence/maps.py`
- `lswitch/intelligence/persistence.py`
- `lswitch/intelligence/user_dictionary.py`

Заглушки (структура есть, реализация TODO):
- `lswitch/core/conversion_engine.py`
- `lswitch/core/modes.py`
- `lswitch/core/event_manager.py`
- `lswitch/input/device_manager.py`
- `lswitch/input/virtual_keyboard.py`
- `lswitch/input/udev_monitor.py`
- `lswitch/platform/xkb_adapter.py` (интерфейс)
- `lswitch/platform/selection_adapter.py` (интерфейс)
- `lswitch/intelligence/dictionary_service.py` (пустые словари)
- `lswitch/intelligence/ngram_analyzer.py` (пустые таблицы)
- `lswitch/ui/` (все файлы)
- `lswitch/app.py`
