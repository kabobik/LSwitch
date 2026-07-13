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
- ✅ **GUI иконка в трее** — быстрые переключатели и полное окно настроек через PyQt6
- ✅ **Настройки без перезапуска** — все параметры активной сессии применяются на лету
- ✅ **systemd служба** — автозапуск GUI при входе в систему

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
- Открыть `Настройки…`
- Статус текущего процесса
- Debug Monitor (если включено отладочное журналирование)

Окно настроек содержит пять страниц и все параметры `config.toml`.
`Применить` сохраняет значения и обновляет работающий процесс, `OK` делает то
же и закрывает окно, а `Отмена` отбрасывает несохранённый draft. Зависимые
поля визуально отключаются вместе с родительской функцией, но введённые в них
значения не теряются. Ошибка проверки ресурса или записи файла не оставляет
частично применённую конфигурацию.

Параметры текущего X11/Wayland adapter-а меняются сразу. Параметры другой
графической платформы тоже сохраняются сразу и будут использованы при запуске
соответствующей сессии.

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
lswitch --debug            # с отладочными сообщениями
lswitch --trace            # с трассировкой всех событий
lswitch --replace          # явный совместимый флаг замены экземпляра
lswitch --diagnose-wayland # диагностика KDE Wayland backend
lswitch --diagnose-wayland-switch-test # диагностика + тест переключения раскладки
```

> **Единственный экземпляр:** при обычном запуске LSwitch автоматически останавливает предыдущий процесс и запускает новый. `--replace` сохранён для совместимости и используется в systemd unit и ярлыке приложения.

## Как это работает

1. **Перехват:** LSwitch слушает события клавиатуры через `/dev/input/` (evdev)
2. **Детектор двойного Shift:** При двух нажатиях Shift с интервалом < `double_click_timeout` сек — срабатывание
3. **Получение текста:** Извлекает последнее слово из внутреннего буфера событий ИЛИ выделение (X11 PRIMARY)
4. **Конвертация:** Посимвольное преобразование EN ↔ RU через таблицу маппинга
5. **Вставка:** Удаляет оригинал (Backspace × N) и «перепечатывает» конвертированный текст через виртуальную клавиатуру
6. **Раскладка результата:** Переключается прямо на целевую раскладку через
   XKB/D-Bus, а проверяемую `layout_switch_key` использует как резервный способ.
   `switch_layout_after_convert` определяет, оставить целевую раскладку или
   восстановить исходную после ввода результата.

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
# Enable live DEBUG logging and Debug Monitor; --trace remains an override.
debug = false
# Keep the result layout after conversion; false restores the previous layout.
switch_layout_after_convert = true
# Verified fallback shortcut; direct XKB/D-Bus target switching has priority.
layout_switch_key = "Alt+Shift"
# Enable automatic wrong-layout conversion at a word boundary.
auto_switch = false
# Minimum buffered characters before automatic conversion; 0 adds no restriction.
auto_switch_threshold = 0
# Enable automatic conversion while the current word is being typed.
auto_switch_mid_word = false
# Minimum prefix length before mid-word detection starts.
mid_word_min_prefix_len = 4
# Use system Hunspell/MySpell dictionaries for mid-word detection.
system_dict_enabled = true
# Optional readable .dic paths; empty values enable auto-discovery.
system_dict_en_path = ""
system_dict_ru_path = ""
# Enable the self-learning user dictionary.
user_dict_enabled = false
# Automatically confirm accepted auto-conversions in the user dictionary.
user_dict_auto_confirm = false
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
- `switch_layout_after_convert` — `true` оставляет раскладку результата;
  `false` восстанавливает раскладку, активную до конвертации
- `layout_switch_key` — резервная комбинация (`Alt+Shift`, `Ctrl+Shift`,
  `Meta+Space`, `CapsLock`); прямое переключение на target через XKB/D-Bus
  имеет приоритет. Legacy-форматы вроде `Alt_L+Shift_L` принимаются и
  сохраняются в каноническом виде
- `debug` — live-переключение уровня `INFO`/`DEBUG` и пункта Debug Monitor;
  запущенный с `--trace` процесс сохраняет уровень `TRACE`
- `auto_switch` — автоматически определять и конвертировать раскладку
- `auto_switch_threshold` — минимальное число символов в буфере до
  автоконвертации на границе слова; `0` не добавляет ограничения
- `auto_switch_mid_word` — переключать раскладку до завершения слова; агрессивный
  opt-in режим, по умолчанию выключен
- `mid_word_min_prefix_len` — минимальная длина префикса для mid-word проверки
- `system_dict_enabled` — подмешивать системные Hunspell/MySpell словари только
  при включенном mid-word режиме
- `system_dict_en_path`, `system_dict_ru_path` — необязательные явные пути к
  английскому и русскому `.dic`; путь должен указывать на существующий
  читаемый обычный файл, пустое значение включает автоопределение. Под полями
  GUI показывает фактически активный путь, способ выбора и число загруженных
  слов
- `user_dict_enabled` — самообучающийся словарь
- `user_dict_auto_confirm` — записывать в словарь молчаливое принятие авто-конвертации на следующем пробеле; по умолчанию выключено
- `wayland_selection_strategy` — стратегия selection-конвертации на Wayland:
  `"auto"` сначала читает PRIMARY без `Ctrl+C`, затем использует clipboard fallback;
  `"clipboard_copy"` всегда использует copy/paste flow;
  `"primary_selection"` читает PRIMARY и заменяет выделение прямым набором без `Ctrl+C/Ctrl+V`;
  `"disabled"` отключает selection-конвертацию на Wayland
- `[timing]` — общие задержки виртуальной клавиатуры и replay после смены раскладки
- `[x11_selection_timing]` — X11-only задержки polling, expand, paste и restore для selection
- `[wayland_timing]` — Wayland-only системные задержки clipboard backend-а
- `[wayland_selection_timing]` — Wayland-only задержки copy/paste/restore и expand для selection

Для первой проверки mid-word режима включите `auto_switch_mid_word = true`.
Он работает независимо от `auto_switch`, который отвечает за конвертацию после
нажатия пробела.
LSwitch использует встроенный EN/RU словарь и, если доступно и разрешено,
добавляет `/usr/share/hunspell/*.dic` или MySpell-словари. Большие системные
индексы не загружаются, пока mid-word режим выключен. Сценарии проверки описаны
в `docs/PLANS/MID_WORD_SYSTEM_DICTIONARY_PLAN.md`.

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

Все изменения из окна настроек и быстрых переключателей tray применяются без
перезапуска. Если TOML изменён внешним редактором, отправьте работающему
процессу `SIGHUP`:

```bash
kill -HUP "$(cat "${XDG_RUNTIME_DIR:-/run/user/$UID}/lswitch.pid")"
```

Внешний файл проходит ту же валидацию и подготовку runtime. При ошибке текущая
конфигурация процесса продолжает работать; исправьте TOML и повторите `SIGHUP`.
Пошаговые проверки GUI приведены в
[`docs/GUI_SETTINGS_MANUAL_TESTING.md`](docs/GUI_SETTINGS_MANUAL_TESTING.md).

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
Убедитесь, что systemd user unit запускается внутри графической сессии и видит `DISPLAY` или `WAYLAND_DISPLAY`, затем перезапустите его:

```bash
systemctl --user restart lswitch
```
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
