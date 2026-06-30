# LSwitch — переключатель раскладки клавиатуры

Перехватчик событий клавиатуры на уровне ядра (evdev) для быстрого преобразования текста между английской и русской раскладками через двойное нажатие Shift.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform: Linux](https://img.shields.io/badge/platform-Linux-green.svg)](https://www.linux.org/)

---

**Быстрая установка:**
```bash
git clone https://github.com/kabobik/lswitch.git && cd lswitch && bash scripts/install.sh
```

---

## Возможности

- ✅ **Конвертация текста по двойному Shift** — нажми Shift дважды быстро, и текст конвертируется
- ✅ **Перехват на уровне ядра** — через `/dev/input/`, работает во всех приложениях
- ✅ **Конвертация слова или выделения** — последнее напечатанное слово ИЛИ выделенный текст
- ✅ **EN ⟷ RU** — английский ↔ русский
- ✅ **Автоопределение раскладки** — по n-граммам и словарю
- ✅ **Самообучающийся словарь** — учится на истории ошибок пользователя
- ✅ **GUI иконка в трее** — статус и управление через PyQt6
- ✅ **GUI автозапуск** — старт внутри X11/Wayland пользовательской сессии

## Установка

### Требования

| Компонент | Назначение | Критичность |
|-----------|-----------|-------------|
| Python 3.11+ | Основной интерпретатор | **Критично** |
| evdev | Чтение событий клавиатуры из `/dev/input/` | **Критично** |
| python-xlib | Определение раскладки, X11 | **Критично** |
| pyudev | Мониторинг hot-plug устройств | **Критично** |
| PyQt6 + QtDBus | GUI и KDE Wayland layout backend | **Критично для Wayland** |
| wl-clipboard | Clipboard fallback для Wayland (`wl-copy`/`wl-paste`) | **Критично для Wayland** |
| qt6-wayland | Qt Wayland platform plugin | **Критично для Wayland** |

**Display Server:** X11 и KDE Plasma Wayland

### Установка из исходников

```bash
git clone https://github.com/kabobik/lswitch.git
cd lswitch
bash scripts/install.sh
```

Скрипт автоматически:
- Проверит Python 3.11+ и все зависимости
- Установит недостающие пакеты через `apt` на Ubuntu/Debian или `pacman` на Arch Linux
- Скопирует приложение в `~/.local/share/lswitch/`
- Создаст команду `lswitch` в `~/.local/bin/`
- Установит udev правила, иконку, ярлык в меню
- Предложит включить GUI автозапуск через `~/.config/autostart/`

⚠️ **После первой установки перелогиньтесь** — права группы `input` применяются только после logout.

### Установка через .deb (Ubuntu/Debian)

Скачайте `.deb` из [Releases](https://github.com/kabobik/lswitch/releases) или соберите сами:

```bash
bash scripts/build-deb.sh
sudo dpkg -i build/lswitch_2.0.0_all.deb
sudo apt install -f  # если нужны зависимости
```

### Удаление

```bash
# Если ставили через install.sh:
bash scripts/install.sh --remove

# Если ставили через .deb:
sudo apt remove lswitch
```

## Использование

### GUI

После запуска иконка LSwitch появляется в системном трее. Правая кнопка мыши — меню управления:
- Переключить авто-конвертацию
- Переключить самообучающийся словарь
- Статус текущего процесса
- Debug Monitor (если `"debug": true` в конфиге)

### Автозапуск

```bash
mkdir -p ~/.config/autostart
cp ~/.local/share/applications/lswitch-control.desktop ~/.config/autostart/
sed -i "s|^Exec=.*|Exec=$HOME/.local/bin/lswitch --replace|" ~/.config/autostart/lswitch-control.desktop
```

`scripts/install.sh` делает это автоматически, если согласиться на включение автозапуска.
Запуск через desktop autostart предпочтителен для X11/Wayland, потому что процесс наследует окружение пользовательской графической сессии.

### Запуск вручную (для отладки)

```bash
lswitch                    # запуск с GUI
lswitch --headless         # без трея/видимого GUI
lswitch --debug            # с отладочными сообщениями
lswitch --trace            # с трассировкой всех событий
lswitch --replace          # остановить предыдущий экземпляр и запустить новый
lswitch --diagnose-wayland # диагностика KDE Wayland backend
lswitch --diagnose-wayland-switch-test # диагностика + тест переключения раскладки
```

> **Защита от двойного запуска:** LSwitch использует PID lock — если экземпляр уже работает, второй не запустится. Для замены используйте `--replace`.

## Как это работает

1. **Перехват:** LSwitch слушает события клавиатуры через `/dev/input/` (evdev)
2. **Детектор двойного Shift:** При двух нажатиях Shift с интервалом < `double_click_timeout` сек — срабатывание
3. **Получение текста:** Извлекает последнее слово из внутреннего буфера событий ИЛИ выделение (X11 PRIMARY)
4. **Конвертация:** Посимвольное преобразование EN ↔ RU через таблицу маппинга
5. **Вставка:** Удаляет оригинал (Backspace × N) и «перепечатывает» конвертированный текст через виртуальную клавиатуру
6. **Переключение раскладки:** Посылает `layout_switch_key` если `switch_layout_after_convert: true`

## Примеры

| Введи (не та раскладка) | Двойной Shift | Результат |
|---|---|---|
| `ghbdtn` | → | `привет` (+ переключает на RU) |
| `привет` | → | `ghbdtn` (+ переключает на EN) |
| `ghbdtn vbh` (выделено) | → | `привет мир` |
| `Hello world` (выделено) | → | `Руддщ цщкдв` |

## Конфигурация

Конфиг: `~/.config/lswitch/config.toml`.

```toml
# LSwitch configuration
#
# Wayland selection strategies:
#   auto              - read PRIMARY selection first, fallback to clipboard copy/paste
#   clipboard_copy    - always use clipboard copy/paste flow
#   primary_selection - read PRIMARY and replace selection by direct UInput typing
#   disabled          - disable Wayland selection conversion

# Maximum interval between two Shift presses, seconds.
double_click_timeout = 0.3
# Enable verbose logging and Debug Monitor tray action.
debug = false
# Switch keyboard layout after manual conversion.
switch_layout_after_convert = true
# Shortcut used by the system to switch keyboard layout.
layout_switch_key = "Alt_L+Shift_L"
# Enable automatic wrong-layout detection and conversion.
auto_switch = false
# Minimum detector confidence for automatic conversion.
auto_switch_threshold = 40
# Enable the self-learning user dictionary.
user_dict_enabled = true
# Minimum user dictionary score required to affect detection.
user_dict_min_weight = 2
# Wayland selection conversion mode.
wayland_selection_strategy = "auto"

# Common input/conversion timings, seconds.
[timing]
# Delay between virtual key press and release.
key_press_delay = 0.001
# Delay between successive virtual key taps.
key_repeat_delay = 0.001
# After layout switch before replaying typed word.
retype_before_replay_delay = 0.05
# After layout switch before direct selection typing.
direct_type_after_layout_switch_delay = 0.03
# After layout switch before undo replay.
undo_before_replay_delay = 0.03
# After layout switch before auto-conversion replay.
auto_before_replay_delay = 0.03
# After auto-conversion replay before final Space handling.
auto_before_space_delay = 0.01

# X11-only selection timings, seconds.
[x11_selection_timing]
# PRIMARY selection polling interval.
poll_interval = 0.5
# After writing clipboard before Ctrl+V.
paste_delay = 0.02
# After Ctrl+V before restoring clipboard.
restore_delay = 0.05
# After Ctrl+Shift+Left before reading PRIMARY.
expand_selection_delay = 0.05

# Wayland-only system timings, seconds.
[wayland_timing]
# Timeout for wl-copy/wl-paste helper commands.
wl_clipboard_timeout = 1.0

# Wayland-only selection timings, seconds.
[wayland_selection_timing]
# Maximum wait for Ctrl+C to update clipboard.
copy_wait_timeout = 1.0
# Clipboard poll interval after copy shortcut.
copy_poll_interval = 0.05
# Delay before trying fallback copy shortcut.
copy_retry_delay = 0.1
# After writing clipboard before Ctrl+V.
paste_delay = 0.12
# After Ctrl+V before restoring clipboard.
restore_delay = 0.15
# After Ctrl+Shift+Left before reading selection.
expand_selection_delay = 0.2
```

**Параметры:**
- `double_click_timeout` — максимальный интервал между двумя Shift (сек)
- `switch_layout_after_convert` — переключать раскладку после конвертации
- `layout_switch_key` — комбинация переключения раскладки (`Alt_L+Shift_L`, `Ctrl_L+Shift_L`)
- `debug` — отладочные сообщения + пункт Debug Monitor в трее
- `auto_switch` — автоматически определять и конвертировать раскладку
- `auto_switch_threshold` — порог уверенности авто-детектора (%)
- `user_dict_enabled` — самообучающийся словарь
- `wayland_selection_strategy` — стратегия selection-конвертации на Wayland:
  `"auto"` сначала читает PRIMARY без `Ctrl+C`, затем использует clipboard fallback;
  `"clipboard_copy"` всегда использует copy/paste flow;
  `"primary_selection"` читает PRIMARY и заменяет выделение прямым набором без `Ctrl+C/Ctrl+V`;
  `"disabled"` отключает selection-конвертацию на Wayland
- `[timing]` — общие задержки виртуальной клавиатуры и replay после смены раскладки
- `[x11_selection_timing]` — X11-only задержки polling, expand, paste и restore для selection
- `[wayland_timing]` — Wayland-only системные задержки clipboard backend-а
- `[wayland_selection_timing]` — Wayland-only задержки copy/paste/restore и expand для selection

Пользовательский словарь хранится отдельно: `~/.config/lswitch/user_dict.toml`.
Он запоминает не "правильные слова", а решения для текста, набранного в конкретной раскладке:

```toml
[convert.en]
"ghbdtn" = 2

[keep.en]
"hello" = 2

[convert.ru]
"руддщ" = 2

[keep.ru]
"привет" = 2
```

Число — это уверенность. Итоговый score считается как `convert - keep`; когда `abs(score)` достигает `user_dict_min_weight`, правило начинает влиять на автоопределение.

После изменения конфига:
```bash
lswitch --replace
```

## Архитектура

```
lswitch/
├── app.py               # Точка входа и главный цикл
├── cli.py               # Аргументы командной строки
├── config.py            # Загрузка и сохранение конфига
│
├── core/                # Ядро: состояния, события, конвертация
│   ├── state_manager.py # FSM состояний (IDLE/TYPING/CONVERTING...)
│   ├── event_manager.py # Маршрутизация evdev событий
│   ├── event_bus.py     # Внутренняя шина событий
│   ├── conversion_engine.py  # Движок конвертации текста
│   └── text_converter.py     # Посимвольная конвертация EN ↔ RU
│
├── input/               # Работа с устройствами ввода
│   ├── device_manager.py  # Сканирование и hot-plug /dev/input/
│   ├── virtual_keyboard.py # Виртуальная клавиатура (uinput)
│   └── key_mapper.py    # Маппинг keycode → символ
│
├── intelligence/        # Умные функции
│   ├── auto_detector.py     # Авто-определение раскладки
│   ├── ngram_analyzer.py    # N-грамм анализ
│   ├── dictionary_service.py # Словарный сервис
│   └── user_dictionary.py   # Пользовательский словарь
│
├── platform/            # Платформо-зависимый код
│   ├── clipboard.py         # Работа с буфером обмена
│   └── selection_adapter.py # X11 PRIMARY selection
│
└── ui/                  # Графический интерфейс
    ├── tray_icon.py     # Иконка в системном трее
    ├── context_menu.py  # Меню трея
    ├── debug_monitor.py # Окно отладки (real-time буфер и состояние)
    └── config_dialog.py # Диалог настроек
```

## Тестирование

```bash
pytest tests/ -v             # все тесты
pytest tests/ --cov=lswitch  # с покрытием кода
pytest tests/test_conversion_engine.py -v  # конкретный модуль
```

📊 **Статус:** 30 тестовых модулей

## Решение проблем

### PermissionError: `/dev/input/eventX`

```bash
sudo usermod -a -G input $USER
# Затем перелогиниться
```

### Иконка трея не появляется

Проверьте, что запущен GUI-режим:
```bash
lswitch --replace
```

Если нужен режим без иконки трея, используйте `lswitch --headless`.

### Конвертация не работает

```bash
lswitch --replace --debug            # запуск с отладкой вручную
```

## Разработка

```bash
git clone https://github.com/kabobik/lswitch.git
cd lswitch

# Установить в editable режиме (для разработки)
pip install -e ".[gui,dev]"

# Запустить тесты
pytest tests/ -v

# Запустить с трассировкой событий
lswitch --trace
```

## Лицензия

MIT License — см. [LICENSE](LICENSE)

## Автор

Anton — 2024-2026

## Благодарности

- Вдохновлено [Punto Switcher](https://yandex.ru/support/punto/) от Яндекса
- Использует [python-evdev](https://python-evdev.readthedocs.io/) для перехвата клавиатуры
- PyQt6 для GUI

---

**⭐ Понравилось? Поставьте звезду на GitHub!**
