# Краткая инструкция: структура и поведение приложения LSwitch

Это удобная, читаемая инструкция для быстрых ознакомления с архитектурой и порядком работы LSwitch.

## 1. Краткое описание
LSwitch — сервис для быстрого переключения раскладки клавиатуры и конвертации ошибочно набранного текста (EN ↔ RU). Работает на уровне ввода (evdev) и включает необязательный GUI (иконка в трее) для управления.

## 2. Основные компоненты
- `lswitch` (пакет)
  - `lswitch.core.LSwitch` — основной класс демона; читает конфиг, создаёт виртуальную клавиатуру (uinput), стартует background‑потоки, обрабатывает события.
  - `lswitch.cli.main` — точка входа для `python -m lswitch` / console script.
  - `conversion.ConversionManager` — логика выбора и выполнения режима конвертации (retype vs selection).
- `adapters/` — GUI‑адаптеры по DE (Cinnamon, KDE). Предоставляют меню, чтение цвета темы и API для взаимодействия трея.
- `utils/` — помощники:
  - `desktop.py` — определение DE и display server;
  - `theme.py` — чтение цветов темы;
  - `buffer.py`, `keyboard.py` — вспомогательные классы для тестирования и эмуляции клавиатуры.
- `adapters/x11.py` — облегчённые обёртки xclip/xdotool для работы с PRIMARY/CLIPBOARD и безопасной вставки/вырезания.
- `dictionary.py` / `user_dictionary.py` — словари для автопереключения и самообучения.

## 3. Установка и запуск (резюме)
- Рекомендуется использовать виртуальное окружение и `pip install -e .`.
- Service (systemd) запускает `python -u -m lswitch` (или консольный `lswitch` entry point).
- GUI: `lswitch-tray` (иконка/меню) — необязательный компонент.

## 4. Порядок запуска и инициализация
1. Точка входа (`python -m lswitch` / console script) вызывает `lswitch.cli.main()`.
2. `cli.main()` читает опции / ловит сигналы (SIGHUP для reload) и создаёт `LSwitch(...)`.
3. `LSwitch.__init__`:
   - вызывает `load_config` → `validate_config`;
   - создаёт виртуальный uinput через `evdev.UInput` (мокаем в тестах);
   - инициализирует `InputBuffer`, `KeyboardController`; загружает `UserDictionary` при включённой опции;
   - получает текущие XKB‑layouts (через Xlib или runtime файл), вычисляет `layouts` и `current_layout`;
   - при `start_threads=True` запускает фоновые потоки: монитор раскладки, монитор файлов раскладок, конфигурация виртуальной клавиатуры;
   - создаёт `ConversionManager` (если доступен модуль `conversion`).

## 5. Основной runtime‑поток (поведение в runtime)
- Демон слушает события клавиатуры (evdev) — собирает `event_buffer` и `text_buffer`.
- При обнаружении двойного Shift (в пределах `double_click_timeout`) или других триггеров вызывает логику конвертации:
  1. `ConversionManager.choose_mode(...)` выбирает `retype` или `selection` на основе контекста (наличие выделения, настройки, политики приложения).
  2. Если `retype`: демонтирует последние события и эмулирует повторную печать корректного текста через виртуальную клавиатуру.
  3. Если `selection`: использует X11 adapter (`adapters/x11.py`) — расширяет выделение при помощи `expand_selection_to_space`, делает `safe_replace_selection` (cut/delete + paste), восстанавливает clipboard.
- После конвертации, если включён `switch_layout_after_convert`, переключает XKB layout (через libX11/XKB или xkbutils).
- Состояние (последние автоконвертации, статистика) может обновляться в `UserDictionary` при включённой самообучающейся опции.

## 6. Конфигурация
- По умолчанию конфиг в `/etc/lswitch/config.json` (локально `config.json` для разработки).
- Ключевые параметры:
  - `double_click_timeout` (float)
  - `debug` (bool)
  - `switch_layout_after_convert` (bool)
  - `layout_switch_key` (string)
  - `auto_switch` (bool)
  - `user_dict_enabled` (bool)
  - `user_dict_min_weight` (int)
- `validate_config(conf)` проверяет типы и диапазоны и возвращает normalized config.

## 7. Тестируемость и mock‑контракты
- Конструктор `LSwitch(..., start_threads=False)` полезен для unit‑тестов (не стартует фоновые потоки).
- Модули `adapters/x11.py`, `utils.keyboad`, `utils.buffer` имеют чёткие, мокируемые интерфейсы.
- GUI‑тесты помечены `@pytest.mark.gui` и требуют PyQt5 + Xvfb в CI.

## 8. Развертывание и systemd
- Unit-файл запускает `python -u -m lswitch` (т.е. запущен код из пакета), что устраняет проблемы с путями.
- Скрипты `install.sh`/`scripts/install.sh` пытаются `pip install` пакет, затем настраивают сервис и udev правила.

## 9. Диагностика (быстрые шаги)
- Сервис падает — смотрите `journalctl -u lswitch -f`.
- Ошибка импорта `No module named 'utils'` — пакет не установлен корректно; проверьте `pip install -e .` или systemd ExecStart использует `-m lswitch`.
- Проблемы с XKB — проверьте, доступна ли `libX11` и `python-xlib`.
- Тестовая локальная отладка: `pytest -q` (по умолчанию GUI‑тесты пропускаются), GUI‑тесты: `xvfb-run pytest -m gui`.

---

Если нужно, могу расширить этот документ конкретными диаграммами запуска (sequence diagram), показать пример гипотетического flow (event → buffer → conversion) или добавить ASCII‑диаграмму потоков данных. Хотите добавить диаграмму? 
