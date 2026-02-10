# 🔍 Аудит проекта LSwitch

Дата: 10 февраля 2026  
Версия проекта: 1.1.1  
Аудитор: opus-agent (Copilot)

---

## Краткое резюме

| Категория | Количество |
|-----------|-----------|
| 🔴 Критических проблем | 6 |
| 🟡 Предупреждений | 23 |
| 🔵 Информационных | 10 |
| **Итого** | **39** |

---

## 🔴 Критические проблемы

> Блокируют работу, вызывают ошибки при запуске или установке

### CRIT-1: Некорректный импорт `ConversionManager` в `core.py`

**Файл:** `lswitch/core.py`, строка 434  
**Проблема:** `from conversion import ConversionManager` — импорт без префикса пакета. Модуль `conversion` находится в `lswitch/conversion.py`, импорт должен быть `from lswitch.conversion import ConversionManager`.  
**Влияние:** `self.conversion_manager` всегда `None` (ошибка ловится `except Exception`), выбор режима конвертации не работает.

### CRIT-2: Некорректный импорт `x11_adapter` в `core.py`

**Файл:** `lswitch/core.py`, строка 99  
**Проблема:** `from adapters import x11 as x11_adapter` — обращение как к top-level пакету `adapters`, а не к `lswitch.adapters`.  
**Влияние:** Импорт всегда проваливается, `x11_adapter = None`. Функции, зависящие от x11_adapter на уровне модуля, работают через fallback.

### CRIT-3: 2 теста не собираются (collection errors)

**Файлы:**
- `tests/test_input_handler.py` — строка 9: `spec.loader.exec_module(mod)` вызывает `ImportError: attempted relative import with no known parent package` при загрузке `lswitch/input.py` через `spec_from_file_location`.
- `tests/test_xkb.py` — строка 14: аналогичная ошибка при загрузке `lswitch/xkb.py`.

**Причина:** Оба модуля (`input.py`, `xkb.py`) используют `from . import system`, а тесты загружают их напрямую через `spec_from_file_location`, минуя пакетную структуру.

### CRIT-4: 30 из 90 тестов проваливаются

**Проваливающиеся группы:**
- `test_convert_text.py` (8 тестов) — `AttributeError`, вероятно `lswitch.LSwitch` не экспортирует `convert_text` на уровне пакета
- `test_integration_selection.py` (7 тестов) — аналогично
- `test_conversion.py` (3 теста) — `conv.convert_text` не существует в `conversion.py` (там `ConversionManager`, а не функция `convert_text`)
- `test_monitor_disable.py` (2 теста) — `AttributeError` при `monkeypatch.setattr(lswitch, ...)` — пакет `lswitch` не экспортирует ожидаемые атрибуты
- `test_shim_documentation.py` (2 теста) — ожидает, что `lswitch` пакет имеет `LSwitch`, `x11_adapter`, `XLIB_AVAILABLE`, `__path__` — но `lswitch/__init__.py` их не предоставляет

### CRIT-5: Хардкоженный абсолютный путь разработчика

**Файл:** `lswitch/adapters/__init__.py`, строка 4  
```python
sys.path.insert(0, '/home/anton/VsCode/LSwitch')
```
**Влияние:** На любой другой машине этот путь не существует. Может вызвать конфликты при импорте.

**Также в:** `tests/test_adapters.py`, строка 9

### CRIT-6: Дублирование инициализации в `core.py`

**Файл:** `lswitch/core.py`, `__init__()` (начинается на строке 265)  
**Проблема:** Следующие блоки выполняются **дважды** внутри `__init__`:
- `self.x11_display = display.Display()` — строки ~375 и ~455
- `self.layouts = self.get_layouts_from_xkb()` — строки ~376 и ~456
- `self.current_layout = ...`, `self.layout_lock`, `self.running` — строки ~383–385 и ~461–463
- `self.user_dict` инициализация — строки ~390–400 и ~467–477
- `self.current_device = None` — строки ~370 и ~449

**Влияние:** Двойное создание X11 Display connection, дублирование потоков мониторинга, потенциальные утечки ресурсов.

---

## 🟡 Предупреждения

> Не блокируют работу, но требуют исправления

### WARN-1: README.md — неверные ключи конфигурации

**Файл:** `README.md`, строки ~143–153  
**Проблема:** Показан пример конфига с несуществующими ключами:
- `double_shift_timeout` → правильно: `double_click_timeout`
- `repair_enabled` → не используется в `validate_config`
- `keyboard_layout_switch_key` → правильно: `layout_switch_key`
- `conversion_rules` → не существует
- `layouts` → не существует в конфиге (определяется через XKB)

### WARN-2: README.md — `sudo systemctl` вместо `systemctl --user`

**Файл:** `README.md`, строки 96–105  
**Проблема:** Документация рекомендует `sudo systemctl start lswitch`, но сервис установлен как user-level (`/etc/systemd/user/lswitch.service`). Правильно: `systemctl --user start lswitch`.

**Также в:** `docs/INSTALL.md`, `docs/MODES_COMPARISON.txt`, `docs/UNIFIED_ARCHITECTURE.md`, `docs/EXAMPLES.md`, `scripts/check_autostart.sh`, `scripts/diagnose.sh`

### WARN-3: Многочисленные ссылки на `/etc/systemd/system/` вместо `/etc/systemd/user/`

**Файлы:**
- `scripts/diagnose.sh:30-31` — проверяет `/etc/systemd/system/lswitch.service`
- `docs/DEPLOYMENT.md:50` — указывает `/etc/systemd/system/lswitch.service`
- `docs/INSTALL.md:41` — аналогично
- `docs/MODES_COMPARISON.txt:92` — аналогично
- `docs/EXAMPLES.md:39,49,86,92` — аналогично

**Реальный путь:** `/etc/systemd/user/lswitch.service`

### WARN-4: ARCHITECTURE.md — устаревшая структура проекта

**Файл:** `docs/ARCHITECTURE.md`, строки 9–22  
**Проблема:** Описана структура с файлами на верхнем уровне:
```
├── lswitch.py              # ← удалён
├── lswitch_control.py      # ← существует
├── utils/                  # ← переехало в lswitch/utils/
├── adapters/               # ← переехало в lswitch/adapters/
└── drivers/                # ← пустая папка
```
Не упомянуты: `lswitch/processors/`, `lswitch/handlers/`, `lswitch/managers/`, `lswitch/core.py`, `lswitch/cli.py`

### WARN-5: Ссылки на несуществующий `lswitch-tray.desktop`

**Файлы:**
- `config/README.md:6` — описывает файл `lswitch-tray.desktop`, который не существует (актуальный: `lswitch-control.desktop`)
- `scripts/check_autostart.sh:9-19` — ищет `lswitch-tray.desktop`
- `docs/MODES_COMPARISON.txt:39-40,194`
- `docs/UNIFIED_ARCHITECTURE.md:232`

### WARN-6: Ссылки на несуществующие `lswitch_tray.py` и `lswitch.py`

**Файлы:**
- `scripts/test_quick.sh:52` — `python3 lswitch_tray.py`
- `scripts/test_quick.sh:61,63` — `python3 -u lswitch.py`
- `docs/DEPLOYMENT.md:40,77,164,167` — упоминает `lswitch.py` как исполняемый файл
- `docs/GUI_AUTOSWITCH.md:30` — `python3 lswitch_tray.py`

### WARN-7: Плейсхолдер `yourusername` в URLs

**Файлы:**
- `setup.py:26` — `url='https://github.com/yourusername/lswitch'`
- `README.md:40,250` — `git clone https://github.com/yourusername/lswitch.git`
- `config/lswitch.service:3` — `Documentation=https://github.com/yourusername/lswitch`
- `docs/EXAMPLES.md:51`

### WARN-8: `config.json.example` содержит ключи, не проходящие валидацию

**Файл:** `config/config.json.example`  
**Ключи, отсутствующие в `validate_config()` и `DEFAULT_CONFIG`:**
- `gui_manage_service` — не обрабатывается
- `allow_user_overrides` — не обрабатывается  
- `app_policies` — обрабатывается только в `ConversionManager`, но не в `validate_config`

Также файл использует `#` комментарии, что не является валидным JSON (хотя sanitizer их удаляет).

### WARN-9: Тройное дублирование DEFAULT_CONFIG

**Файл:** `lswitch/config.py`  
**Проблема:** Конфиг по умолчанию определяется в трёх местах:
1. `validate_config()`:35-42 — 7 ключей
2. `load_config()`:152-157 — 5 ключей (нет `user_dict_enabled`, `user_dict_min_weight`)
3. `ConfigManager.DEFAULT_CONFIG`:174-181 — 7 ключей

Значения совпадают, но любое изменение нужно вносить в 3 места.

### WARN-10: Дублирование `convert_text()` между `core.py` и `text_processor.py`

**Файлы:**
- `lswitch/core.py:880` — метод `LSwitch.convert_text()`
- `lswitch/processors/text_processor.py:23` — метод `TextProcessor.convert_text()`

Обе реализации выполняют одинаковую логику конвертации EN↔RU.

### WARN-11: Версия в `cli.py` захардкожена как `1.0`

**Файл:** `lswitch/cli.py:34`  
```python
version='%(prog)s 1.0'
```
**Проблема:** `__version__.py` содержит `1.1.1`. Нужно использовать динамический импорт.

### WARN-12: `requirements.txt` неполный

**Файл:** `requirements.txt`  
**Содержимое:** Только `python-xlib`.  
**Проблема:** `setup.py` указывает `evdev` и `python-xlib` в `install_requires`, но `requirements.txt` не включает `evdev`.

### WARN-13: `lswitch_control.py` — дублирование импортов

**Файл:** `lswitch_control.py`  
**Проблема:** 
- `import os` — строки 9 и 21
- `import sys` — строки 8 и 22
- `import time` — строки 17 и 48

### WARN-14: Устаревший комментарий о `lswitch.py`

**Файл:** `lswitch_control.py:24`  
```python
# Import lswitch.system robustly (work even if top-level lswitch.py exists)
```
`lswitch.py` удалён, комментарий и защитный блок `try/except` больше не нужны.

**Также в:** `lswitch/adapters/x11.py:10`, `lswitch/utils/theme.py:14-20`

### WARN-15: Хардкоженный путь `/usr/local/lib/lswitch`

**Файл:** `lswitch_control.py:13`  
```python
sys.path.insert(0, '/usr/local/lib/lswitch')
```
**Проблема:** Этот путь не используется в текущей архитектуре установки (pip install). Пакет устанавливается как стандартный Python пакет.

### WARN-16: Хардкоженные пути `/usr/local/bin/` в `lswitch_control.py`

**Файл:** `lswitch_control.py`
- Строка 582: `/usr/local/bin/lswitch-control`
- Строка 589: `/usr/local/bin/lswitch-control`
- Строка 783: `Exec=/usr/local/bin/lswitch-control`

**Проблема:** Entry point может быть установлен в другое место (напр. `~/.local/bin/`).

### WARN-17: Устаревший комментарий о пути в `core.py`

**Файл:** `lswitch/core.py:20-21`  
```python
# Добавляем /usr/local/bin в путь для импорта dictionary.py
# Также добавляем /usr/local/lib/lswitch в путь — туда копирует инсталлятор утилиты `utils` и `adapters`
```
Комментарий не соответствует действительности — dictionary.py теперь импортируется из пакета `lswitch`.

### WARN-18: Устаревшая проверка `/usr/local/bin/user_dictionary.py`

**Файл:** `lswitch/core.py:93`  
```python
if os.path.exists('/usr/local/bin/user_dictionary.py'):
    print("⚠️  user_dictionary.py найден но не импортируется")
```
Не актуально — `user_dictionary.py` находится в `lswitch/user_dictionary.py`.

### WARN-19: Неиспользуемые (unused) модули из рефакторинга

**Модули, определённые но не интегрированные полноценно:**
- `lswitch/handlers/event_handler.py` — класс `EventHandler` не используется в `core.py`
- `lswitch/managers/layout_manager.py` — класс `LayoutManager` не используется в `core.py`

Эти модули были созданы при рефакторинге, но `core.py` всё ещё содержит inline-реализации.

### WARN-20: `lswitch/adapters/x11.py` — избыточный fallback для импорта `lswitch.system`

**Файл:** `lswitch/adapters/x11.py:10-18`  
**Проблема:** Fallback через `spec_from_file_location` использует неверный относительный путь:
```python
os.path.join(os.path.dirname(__file__), '..', 'lswitch', 'system.py')
```
Файл уже в `lswitch/adapters/`, поэтому `../lswitch/system.py` ведёт к правильному месту случайно. Но если `__file__` изменится — путь сломается.

### WARN-21: `test_conversion.py` обращается к несуществующим функциям

**Файл:** `tests/test_conversion.py`
- Строка 11: `conv.convert_text('hello')` — функции `convert_text` нет в `conversion.py` (это `ConversionManager` класс)
- Строка 28: `conv._check_with_dictionary(d, 'hello')` — функции `_check_with_dictionary` нет в `conversion.py`

### WARN-22: Тесты, импортирующие `import lswitch` ожидают shim-поведение

**Файлы:** `test_monitor_disable.py`, `test_shift_release_behavior.py`, `test_selection_whitespace.py`, `test_suppression.py`, `test_convert_text.py`, `test_integration_selection.py`, `test_selection_expand_strip_leading.py`, `test_selection_trim_clipboard.py`

Все используют `import lswitch` и затем `lswitch.LSwitch`, `lswitch.XLIB_AVAILABLE`, `lswitch.x11_adapter`. Но `lswitch/__init__.py` не экспортирует эти символы. Нужен shim в `__init__.py`.

### WARN-23: `scripts/diagnose.sh` проверяет несуществующий путь конфига

**Файл:** `scripts/diagnose.sh:24-27`  
Проверяет `/etc/lswitch/config.json`, но текущая установка через pip + editable mode не создаёт этот файл. Конфиг пользователя: `~/.config/lswitch/config.json`.

---

## 🔵 Информационные

> Рекомендации по улучшению

### INFO-1: Артефакты сборки в репозитории

Следующие директории/файлы не нужны в git:
- `build/lswitch_1.1.0_all.deb` — артефакт сборки .deb
- `lswitch.egg-info/` — генерируется `pip install -e .`
- `__pycache__/` — присутствуют в `lswitch/__pycache__/`, `lswitch/adapters/__pycache__/`, и др.

**Рекомендация:** `.gitignore` покрывает паттерны `__pycache__/`, `*.egg-info/`, `build/`, но эти файлы уже были закоммичены. Выполнить `git rm -r --cached`.

### INFO-2: Пустые директории

- `archive/` — пустая директория
- `drivers/` — пустая директория
- `lswitch/managers/` — содержит только `__init__.py` и `layout_manager.py` (не используется)

### INFO-3: `lswitch/processors/__init__.py` — пустой файл

Не экспортирует `TextProcessor` и `BufferManager`. Рекомендуется добавить:
```python
from .text_processor import TextProcessor
from .buffer_manager import BufferManager
```

### INFO-4: `lswitch/__init__.py` не найден или пуст

Пакет `lswitch` не экспортирует ключевые символы на уровне `__init__.py`. Многие тесты ожидают `lswitch.LSwitch`, `lswitch.XLIB_AVAILABLE`, `lswitch.x11_adapter`. Нужен re-export.

### INFO-5: `lswitch.egg-info/top_level.txt` содержит только `lswitch_control`

Не включает пакет `lswitch`. Вероятно, нужно пересобрать: `pip install -e .`

### INFO-6: `conftest.py` содержит bare `except:` (строка ~36 в i18n.py)

**Файл:** `lswitch/i18n.py:33`  
```python
except:
    pass
```
Рекомендуется использовать `except Exception:`.

### INFO-7: README.md утверждает "98 тестов, все проходят ✅"

**Файл:** `README.md:214`  
**Реальность:** 90 тестов собирается, 2 ошибки сбора, 30 проваливаются, 60 проходят.

### INFO-8: Документация в `docs/` частично устаревшая

Следующие файлы содержат устаревшую информацию:
- `docs/DEPLOYMENT.md` — описывает установку через ручное копирование `lswitch.py`
- `docs/GUI_AUTOSWITCH.md` — инструкции `python3 lswitch_tray.py`, `lswitch-tray`
- `docs/MODES_COMPARISON.txt` — ссылки на `lswitch-tray.desktop` и `sudo systemctl`
- `docs/UNIFIED_ARCHITECTURE.md` — ссылки на `lswitch-tray.desktop`
- `docs/INSTALL.md` — путь `/etc/systemd/system/lswitch.service`

### INFO-9: `assets/lswitch.png` существует, но неизвестно валидный ли размер иконки

Директория `assets/` содержит несколько размеров: 64, 128, 256 px и SVG. Используется `lswitch.png` (без суффикса) — проверить, что это корректный размер для pixmaps.

### INFO-10: `from __future__ import annotations` не везде используется

Некоторые модули (`core.py`, `i18n.py`, `dictionary.py`, `ngrams.py`) не используют `from __future__ import annotations`, что может вызвать проблемы с type hints на Python 3.8–3.9.

---

## Детальный анализ по категориям

### Импорты

| # | Файл | Строка | Проблема | Критичность |
|---|------|--------|----------|-------------|
| 1 | `lswitch/core.py` | 434 | `from conversion import ConversionManager` — должно быть `from lswitch.conversion import ConversionManager` | 🔴 |
| 2 | `lswitch/core.py` | 99 | `from adapters import x11 as x11_adapter` — должно быть `from lswitch.adapters import x11 as x11_adapter` | 🔴 |
| 3 | `lswitch/adapters/__init__.py` | 4 | `sys.path.insert(0, '/home/anton/VsCode/LSwitch')` — хардкоженный путь | 🔴 |
| 4 | `lswitch_control.py` | 9+21, 8+22, 17+48 | Дублирование импортов `os`, `sys`, `time` | 🟡 |
| 5 | `lswitch_control.py` | 13 | `sys.path.insert(0, '/usr/local/lib/lswitch')` — устаревший путь | 🟡 |
| 6 | `tests/test_adapters.py` | 9 | `sys.path.insert(0, '/home/anton/VsCode/LSwitch')` — хардкоженный путь | 🔴 |

### Установка и entry points

| # | Файл | Проблема | Критичность |
|---|------|----------|-------------|
| 1 | `setup.py` | Entry points `lswitch=lswitch.cli:main` и `lswitch-control=lswitch_control:main` — корректные ✅ | — |
| 2 | `config/lswitch-control.desktop` | `Exec=lswitch-control` — корректно ✅ | — |
| 3 | `config/lswitch.service` | User-level service, `ExecStart=/usr/local/bin/lswitch` — корректно ✅ | — |
| 4 | `setup.py:26` | URL `https://github.com/yourusername/lswitch` — плейсхолдер | 🟡 |
| 5 | `Makefile` | Все команды рабочие ✅ | — |
| 6 | `scripts/install.sh` | Рабочий ✅ | — |
| 7 | `scripts/uninstall.sh` | Рабочий ✅ | — |

### Код

| # | Файл | Строка | Проблема | Критичность |
|---|------|--------|----------|-------------|
| 1 | `lswitch/core.py` | `__init__` | Дублирование инициализации (6+ атрибутов инициализированы дважды) | 🔴 |
| 2 | `lswitch/core.py` + `text_processor.py` | 880 + 23 | Дублирование `convert_text()` | 🟡 |
| 3 | `lswitch/config.py` | 35,152,174 | Тройное дублирование DEFAULT_CONFIG | 🟡 |
| 4 | `lswitch/cli.py` | 34 | Версия `1.0` захардкожена, должна быть `__version__` | 🟡 |
| 5 | `lswitch/core.py` | 93 | Проверка `/usr/local/bin/user_dictionary.py` — устаревший путь | 🟡 |
| 6 | `lswitch/core.py` | 20-21 | Устаревшие комментарии о путях | 🟡 |
| 7 | `lswitch/handlers/event_handler.py` | — | Создан, но не используется в core.py | 🟡 |
| 8 | `lswitch/managers/layout_manager.py` | — | Создан, но не используется в core.py | 🟡 |
| 9 | `lswitch/i18n.py` | 33 | Bare `except:` без типа исключения | 🔵 |

### Тесты

| # | Файл | Проблема | Критичность |
|---|------|----------|-------------|
| 1 | `tests/test_input_handler.py` | Collection error: relative import failure | 🔴 |
| 2 | `tests/test_xkb.py` | Collection error: relative import failure | 🔴 |
| 3 | `tests/test_conversion.py` | Обращение к несуществующим `convert_text()` и `_check_with_dictionary()` | 🟡 |
| 4 | `tests/test_convert_text.py` | Ожидает `lswitch.LSwitch` через shim | 🟡 |
| 5 | `tests/test_shim_documentation.py` | Тестирует shim-поведение, которое не реализовано в `__init__.py` | 🟡 |
| 6 | `tests/test_monitor_disable.py` | `monkeypatch.setattr(lswitch, ...)` — атрибуты не экспортированы | 🟡 |
| 7 | 8 тестов `selection`/`integration` | `import lswitch` → `lswitch.LSwitch` не работает | 🟡 |
| — | **Итого** | **2 ошибки сбора, 30 проваливаются, 60 проходят** | — |

### Конфигурация

| # | Файл | Проблема | Критичность |
|---|------|----------|-------------|
| 1 | `config/config.json.example` | Содержит ключи `gui_manage_service`, `allow_user_overrides`, `app_policies` — не проходят валидацию | 🟡 |
| 2 | `config/config.json.example` | Использует `#` комментарии (не стандартный JSON) | 🔵 |
| 3 | `lswitch/config.py` | DEFAULT_CONFIG в 3 местах | 🟡 |
| 4 | `requirements.txt` | Отсутствует `evdev` (есть в `setup.py:install_requires`) | 🟡 |

### Документация

| # | Файл | Проблема | Критичность |
|---|------|----------|-------------|
| 1 | `README.md:143-153` | Неверные ключи конфигурации (`double_shift_timeout`, `repair_enabled`, etc.) | 🟡 |
| 2 | `README.md:96-105` | `sudo systemctl` вместо `systemctl --user` | 🟡 |
| 3 | `README.md:40,250` | Плейсхолдер `yourusername` в URL | 🟡 |
| 4 | `README.md:214` | "98 тестов, все проходят" — неверно | 🔵 |
| 5 | `docs/ARCHITECTURE.md:9-22` | Устаревшая структура проекта (упоминает `lswitch.py`, `utils/`, `adapters/` как top-level) | 🟡 |
| 6 | `docs/DEPLOYMENT.md` | Ссылки на `lswitch.py`, устаревшие пути установки | 🟡 |
| 7 | `docs/GUI_AUTOSWITCH.md:30` | `python3 lswitch_tray.py` — файл не существует | 🟡 |
| 8 | `docs/INSTALL.md:41` | `/etc/systemd/system/lswitch.service` — неверный путь | 🟡 |
| 9 | `docs/MODES_COMPARISON.txt` | Множество устаревших ссылок | 🟡 |
| 10 | `config/README.md:6` | Упоминает `lswitch-tray.desktop` — не существует | 🟡 |

### Артефакты

| # | Путь | Проблема | Критичность |
|---|------|----------|-------------|
| 1 | `build/lswitch_1.1.0_all.deb` | Артефакт сборки в репозитории | 🔵 |
| 2 | `lswitch.egg-info/` | Генерируемый метаданные пакета | 🔵 |
| 3 | `__pycache__/` (множественные) | Скомпилированные .pyc в репозитории | 🔵 |
| 4 | `archive/` | Пустая директория | 🔵 |
| 5 | `drivers/` | Пустая директория | 🔵 |

---

## Рекомендации по приоритету исправлений

### Немедленно (блокеры)
1. Исправить импорт в `core.py:434` → `from lswitch.conversion import ConversionManager`
2. Исправить импорт в `core.py:99` → `from lswitch.adapters import x11 as x11_adapter`
3. Убрать хардкоженный путь из `adapters/__init__.py:4`
4. Создать shim в `lswitch/__init__.py` для совместимости тестов
5. Исправить тесты `test_input_handler.py` и `test_xkb.py` — использовать пакетный импорт
6. Устранить дублирование инициализации в `core.py.__init__`

### В ближайшее время
7. Обновить README.md (ключи конфига, systemctl --user, yourusername)
8. Обновить `requirements.txt` — добавить `evdev`
9. Исправить версию в `cli.py` — динамический импорт из `__version__`
10. Обновить ARCHITECTURE.md — актуальная структура

### Рефакторинг
11. Объединить DEFAULT_CONFIG в одно место
12. Выделить инициализацию `core.py.__init__` в подмодули
13. Убрать устаревшие защитные конструкции от `lswitch.py`
14. Интегрировать или удалить `EventHandler` и `LayoutManager`
15. Очистить артефакты (`git rm --cached`)
