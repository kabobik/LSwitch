# LSwitch — переключатель раскладки клавиатуры

Перехватчик событий клавиатуры на уровне ядра (evdev) для быстрого преобразования текста между английской и русской раскладками через двойное нажатие Shift.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
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
- ✅ **GUI иконка в трее** — основной режим запуска, статус и управление через PyQt5
- ✅ **systemd headless-режим** — опциональный запуск без GUI

## Установка

### Требования

| Компонент | Назначение | Критичность |
|-----------|-----------|-------------|
| Python 3.10+ | Основной интерпретатор | **Критично** |
| pip3 | Установка Python пакетов | **Критично** |
| evdev | Чтение событий клавиатуры из `/dev/input/` | **Критично** |
| python-xlib | Определение раскладки, X11 | **Критично** |
| pyudev | Мониторинг hot-plug устройств | **Критично** |
| PyQt5 | Иконка в системном трее | Рекомендуется |
| systemd | Опциональный headless-сервис | Опционально |

**Display Server:** X11 (основной), Wayland через XWayland

### Установка из исходников

```bash
git clone https://github.com/kabobik/lswitch.git
cd lswitch
bash scripts/install.sh
```

Скрипт автоматически:
- Проверит Python 3.10+ и все зависимости
- Установит недостающие пакеты через apt
- Скопирует приложение в `~/.local/share/lswitch/`
- Создаст команду `lswitch` в `~/.local/bin/`
- Установит udev правила, иконку, ярлык в меню и опциональный systemd unit
- Не включает headless-сервис автоматически, чтобы не конфликтовать с GUI-запуском

⚠️ **После первой установки перелогиньтесь** — права группы `input` применяются только после logout.
После входа запустите `lswitch` из меню приложений или из терминала.

### Установка через .deb (Ubuntu/Debian)

Скачайте `.deb` из [Releases](https://github.com/kabobik/lswitch/releases) или соберите сами:

```bash
bash scripts/build-deb.sh
sudo dpkg -i build/lswitch_2.0.0_all.deb
sudo apt install -f  # если нужны зависимости
```

После установки `.deb` добавьте пользователя в группу `input`, перелогиньтесь и запускайте GUI:

```bash
sudo usermod -a -G input $USER
# logout/login
lswitch
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

Основной способ запуска:

```bash
lswitch
```

После запуска иконка LSwitch появляется в системном трее, а процесс сам слушает клавиатуру. Правая кнопка мыши — меню управления:
- Переключить авто-конвертацию
- Переключить самообучающийся словарь
- Debug Monitor (если `"debug": true` в конфиге)

### Опциональный headless-сервис

Если нужен запуск без GUI и без иконки в трее, используйте user service. Не запускайте его одновременно с GUI-режимом: LSwitch использует PID lock и рассчитан на один активный экземпляр.

```bash
systemctl --user enable --now lswitch  # автозапуск + старт
systemctl --user disable --now lswitch # отключить автозапуск + остановить
systemctl --user start lswitch         # запустить
systemctl --user stop lswitch          # остановить
systemctl --user restart lswitch       # перезапустить
systemctl --user status lswitch        # статус
journalctl --user-unit=lswitch -f      # следить за логами
```

### Запуск вручную (для отладки)

```bash
lswitch             # запуск с GUI
lswitch --headless  # без GUI (headless daemon)
lswitch --debug     # с отладочными сообщениями
lswitch --trace     # с трассировкой всех событий
lswitch --replace   # остановить предыдущий экземпляр и запустить новый
```

> **Защита от двойного запуска:** LSwitch использует PID lock — если экземпляр уже работает, второй не запустится. Для замены используйте `--replace`.

## Как это работает

1. **Перехват:** Процесс LSwitch слушает события клавиатуры через `/dev/input/` (evdev)
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

Конфиг: `~/.config/lswitch/config.json` (создаётся автоматически при первом запуске).

```json
{
  "double_click_timeout": 0.3,
  "switch_layout_after_convert": true,
  "layout_switch_key": "Alt_L+Shift_L",
  "debug": false,
  "auto_switch": false,
  "auto_switch_threshold": 40,
  "user_dict_enabled": true,
  "user_dict_min_weight": 2,
  "app_policies": {
    "Code": "retype",
    "Firefox": "selection"
  }
}
```

**Параметры:**
- `double_click_timeout` — максимальный интервал между двумя Shift (сек)
- `switch_layout_after_convert` — переключать раскладку после конвертации
- `layout_switch_key` — комбинация переключения раскладки (`Alt_L+Shift_L`, `Ctrl_L+Shift_L`)
- `debug` — отладочные сообщения + пункт Debug Monitor в трее
- `auto_switch` — автоматически определять и конвертировать раскладку
- `auto_switch_threshold` — порог уверенности авто-детектора (%)
- `user_dict_enabled` — самообучающийся словарь
- `app_policies` — режим конвертации по имени окна: `"retype"` или `"selection"`

После изменения конфига:
```bash
lswitch --replace
# если используете headless-сервис, можно отправить SIGHUP:
systemctl --user kill -s HUP lswitch
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

Убедитесь, что запускаете обычный GUI-режим:

```bash
lswitch
```

На сервере без GUI используйте headless-режим:

```bash
lswitch --headless
```

Если запускаете через systemd, это будет режим без иконки в трее.

### Конвертация не работает

```bash
lswitch --debug                      # запуск GUI с отладкой вручную
systemctl --user status lswitch      # статус, если используете headless-сервис
journalctl --user-unit=lswitch -f    # логи headless-сервиса
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
- PyQt5 для GUI

---

**⭐ Понравилось? Поставьте звезду на GitHub!**
