# LSwitch 2.0 — Контекст проекта

## Текущий статус

- **Ветка:** `v2-rewrite`
- **Тесты:** 146 passed
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

## Следующий этап

### Этап 4: Core Layer (бизнес-логика)
- 4.1 RetypeMode
- 4.2 SelectionMode
- 4.3 ConversionEngine.convert()
- 4.4 EventManager.handle_raw_event()
- 4.5 Интеграция EventManager + StateManager + ConversionEngine

## Архитектурные решения

- DI через ABC интерфейсы (IXKBAdapter, ISelectionAdapter, ISystemAdapter)
- EventBus pub/sub для связи модулей
- StateManager FSM: IDLE → TYPING → SHIFT_PRESSED → CONVERTING → BACKSPACE_HOLD
- Mock-адаптеры в tests/conftest.py
- Конвейер: Вася (opus-agent) → Вася-диагност (review-agent), max 2 итерации
