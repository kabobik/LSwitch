# LSwitch 2.0 — Контекст проекта

## Текущий статус

- **Ветка:** `v2-rewrite`
- **Тесты:** 331 passed
- **Python:** 3.12.3, pytest 7.4.4

## Завершённые этапы

### Этап 1: Intelligence Layer ✅
- Словари: 347 ru, 562 en (дубли удалены)
- N-граммы: bigrams (79 ru, 64 en), trigrams (40 ru, 35 en)
- AutoDetector: dict P1 → dict convert P2 → ngram P3
- Фиксы: None-crash в DictionaryService, isalpha() guard для ngrams, len>=4 для zero-score

### Этап 2: Platform Layer ✅
- X11XKBAdapter: get_layouts, switch_layout, keycode_to_char, кешированный Display*
- X11SelectionAdapter: get/replace_selection, has_fresh_selection (owner_id+text+cursor)
- SubprocessSystemAdapter: run_command с таймаутом, get/set_clipboard
- Фиксы по ревью: `if old_clip is not None:`, удалён мёртвый clipboard.py, почищен xkb_bindings.py
- Минорный tech-debt: XKB_USE_CORE_KBD дублируется (xkb_bindings + адаптер)

### Этап 3: Input Layer ✅
- DeviceManager: портирован из архива, thread-safe, callback API, device_filter интегрирован
- UdevMonitor: standalone класс, daemon thread, pyudev мониторинг
- VirtualKeyboard: tap_key, replay_events, UInput обёртка
- 39 новых тестов (19 + 10 + 10), все с полной мок-изоляцией evdev/pyudev
- Minor tech-debt: VirtualKeyboard без context manager, key_mapper только EN

### Этап 4: Core Layer ✅
- RetypeMode: delete → switch → replay, conditional Shift release (только непарные)
- SelectionMode: get_selection → convert_text → replace_selection → switch_layout
- ConversionEngine: choose_mode по backspace_hold_active → fresh_selection → chars_in_buffer
- EventManager: классификация EV_KEY, MOUSE_CLICK, кеш EV_KEY
- Исправлен баг v1: Shift release в finally триггерил XKB toggle
- Исправлен баг: backspace_hold_active флаг доживает до choose_mode()
- 43 новых теста (11+5+9+9+8+доп), интеграционные E2E сценарии

### Этап 5: Application ✅
- LSwitchApp: lazy _init_platform, _wire_event_bus, event loop, graceful stop()
- ConfigManager: DEFAULT_CONFIG, validate_config, sanitize JSON comments, save/reload/reset
- CLI: --headless, --debug, --version
- Исправлен баг: backspace_repeats не сбрасывался между сессиями
- 50 новых тестов (25 app + 21 config + 4 cli)
- Minor tech-debt: text_buffer в StateContext не заполняется, _sanitize_json URL risk

### Этап 6: UI Layer ✅
- TrayIcon: QSystemTrayIcon, adaptive icon, EventBus подписка (LAYOUT_CHANGED, CONFIG_CHANGED), cleanup() для отписки
- ContextMenu: QMenu с toggle auto_switch/user_dict, service control через systemctl, About, Quit → APP_QUIT
- ConfigDialog: QDialog с QCheckBox/QSpinBox/QDoubleSpinBox, OK → save + CONFIG_CHANGED, Reset defaults
- CinnamonAdapter: CustomMenu + CustomMenuItem + QMenuWrapper (порт из архива), supports_native_menu=False
- KDEAdapter: нативный QMenu с Breeze Dark палитрой, supports_native_menu=True
- detect_desktop_environment() + get_adapter() фабрика по XDG_CURRENT_DESKTOP
- Исправлены: утечка EventBus подписок, sync subprocess блокировка GUI, checked state sync
- threading.Thread(daemon=True) для subprocess вызовов
- 54 новых теста (35 + 19 fix), все с полной PyQt5 mock-изоляцией через sys.modules
- Minor tech-debt: get_theme_colors хардкод (нет парсинга GTK CSS/kdeglobals), cross-thread EventBus→Qt

### Этап 7: Перенос данных ✅
- i18n: класс I18n, 46 ключей перевода ru/en, глобальные t() / get_lang()
- Все UI-строки заменены на t(...) в context_menu.py, config_dialog.py, tray_icon.py
- Исправлено: locale.getdefaultlocale() → locale.getlocale() (нет DeprecationWarning)
- Сквозной тест test_integration_full.py: 14 E2E тестов (EventBus → StateManager → ConversionEngine)
- 28 новых тестов (14 i18n + 14 integration)

### Packaging: обновление сборочных файлов ✅
- __version__.py, lswitch/__init__.py, lswitch/cli.py: синхронизированы на `2.0.0`
- setup.py: убраны py_modules, lswitch-control entry point, data_files; python_requires>=3.10
- requirements.txt: core deps + закомментирован PyQt5
- Makefile: исправлен test target, install [gui], clean .mypy_cache, убрана ссылка на lswitch-control
- TODO.md: обновлены таблица «Лишнее в корне» и базовый статус реализованных модулей

### Деплой: фикс блокеров и рекомендаций ✅
- Создан `config/` с актуальными: lswitch.service (--headless, ImportEnvironment=DISPLAY), 99-lswitch.rules, lswitch-control.desktop (Exec=lswitch), config.json.example
- Makefile: post-install копирует .service→~/.config/systemd/user/, .rules→/etc/udev/rules.d/, .desktop→~/.local/share/applications/; uninstall удаляет
- app.py: logging вместо print (3 места), SIGHUP-обработчик для reload конфига, проверка DISPLAY перед _init_platform()
- config.py: logging вместо print (2 места), метод reload()
- cli.py: версия из lswitch.__version__ (не захардкожена)
- requirements.txt: документированы системные зависимости (xclip, xdotool)

## Проект готов к деплою ✅

### 331 тест — все зелёные
### Версия: 2.0.0
### Режимы запуска:
- `python3 -m lswitch --debug` — ручной с GUI
- `python3 -m lswitch --headless --debug` — ручной без GUI
- `make install && make enable` — systemd-сервис

## Архитектурные решения

- DI через ABC интерфейсы (IXKBAdapter, ISelectionAdapter, ISystemAdapter)
- EventBus pub/sub для связи модулей
- StateManager FSM: IDLE → TYPING → SHIFT_PRESSED → CONVERTING → BACKSPACE_HOLD
- Mock-адаптеры в tests/conftest.py
- Конвейер: Вася (opus-agent) → Вася-диагност (review-agent), max 2 итерации
