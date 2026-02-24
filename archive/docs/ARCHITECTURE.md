# Архитектура LSwitch

## Обзор

LSwitch — переключатель раскладки для Linux (X11). Перехватывает события клавиатуры через evdev, определяет ошибочную раскладку и конвертирует текст при двойном нажатии Shift.

## Структура пакета

```
lswitch/                        # Основной пакет (pip install -e .)
├── __init__.py                 # Re-exports: LSwitch, x11_adapter, etc.
├── __main__.py                 # python -m lswitch
├── cli.py                      # Entry point: lswitch CLI
├── core.py                     # Главный класс LSwitch (event loop, conversion)
├── config.py                   # Загрузка ~/.config/lswitch/config.json
├── input.py                    # InputHandler — обработка событий клавиатуры
├── xkb.py                      # XKB: раскладки, keycode→char через libX11
├── conversion.py               # ConversionManager + check_and_auto_convert()
├── conversion_maps.py          # EN_TO_RU / RU_TO_EN маппинги
├── dictionary.py               # Словари EN/RU для определения языка
├── ngrams.py                   # N-gram анализ + should_convert()
├── user_dictionary.py          # Пользовательский словарь (самообучение)
├── selection.py                # Работа с X11 выделением/clipboard
├── monitor.py                  # LayoutMonitor — мониторинг смены раскладки
├── system.py                   # SystemInterface — обёртка xdotool/xclip
├── i18n.py                     # Интернационализация GUI
├── adapters/                   # GUI адаптеры для DE
│   ├── __init__.py             # Фабрика get_adapter()
│   ├── base.py                 # BaseGUIAdapter (ABC)
│   ├── cinnamon.py             # CustomMenu для Cinnamon
│   ├── kde.py                  # Нативный QMenu для KDE
│   └── x11.py                  # X11-утилиты (clipboard, selection, window)
├── handlers/                   # Обработчики событий
│   └── event_handler.py
├── managers/                   # Менеджеры
│   └── layout_manager.py
├── processors/                 # Обработчики данных
│   ├── buffer_manager.py       # Управление буфером событий
│   └── text_processor.py       # Конвертация текста EN↔RU
└── utils/                      # Утилиты
    ├── buffer.py
    ├── desktop.py              # Определение DE
    ├── keyboard.py
    └── theme.py                # Чтение цветов темы DE

lswitch_control.py              # GUI панель управления (entry point)
```

## Ключевые компоненты

### core.py — LSwitch

Центральный класс. Инициализирует evdev-перехват, виртуальную клавиатуру, обрабатывает события.

Основной поток:
1. `run()` → evdev select loop → `handle_event()`
2. `handle_event()` → делегирует в `InputHandler`
3. InputHandler определяет: обычный ввод, Shift, Backspace, Space
4. Двойной Shift → `on_double_shift()` → `convert_and_retype()`
5. Пробел → `check_and_auto_convert()` (если включено)

### input.py — InputHandler

Первичная обработка событий клавиатуры:
- Заполняет `text_buffer` (текстовое представление) и `event_buffer` (сырые события)
- Отслеживает `chars_in_buffer`, `last_was_space`, `had_backspace`
- Делегирует специальные действия в LSwitch

### conversion.py — ConversionManager

Выбор режима конвертации:
- `retype` — удалить backspace'ами + переключить раскладку + replay (быстрый, для IDE)
- `selection` — через X11 selection (медленный, для браузеров)

`check_and_auto_convert()` — автоконвертация при пробеле: анализирует слово через ngrams, вызывает `convert_and_retype(is_auto=True)`.

### xkb.py

Определение текущей раскладки и маппинг keycode→char через libX11/XKB. Поддерживает полный набор кириллических символов.

### adapters/x11.py

Обёртка вокруг xclip/xdotool/xprop для X11-операций:
- `get_primary_selection()`, `get_clipboard()`, `set_clipboard()`
- `paste_clipboard()`, `cut_selection()`, `delete_selection()`
- `expand_selection_to_space()` — расширение выделения до пробела
- `safe_replace_selection()` — безопасная замена выделенного текста

## Установка и запуск

- **Установка**: `pip install -e .` (editable)
- **Entry points**: `lswitch` (CLI), `lswitch-control` (GUI)
- **Сервис**: systemd user-level (`systemctl --user`)
- **Конфиг**: `~/.config/lswitch/config.json`

## Поддерживаемые DE

| DE | Адаптер | Особенности |
|----|---------|-------------|
| Cinnamon | `CinnamonAdapter` | CustomMenu (QWidget), GTK CSS темы |
| KDE Plasma | `KDEAdapter` | Нативный QMenu, kdeglobals темы |
