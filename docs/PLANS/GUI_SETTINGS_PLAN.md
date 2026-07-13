# GUI settings and live runtime configuration plan

Дата: 2026-07-13

Этот документ фиксирует план разработки полноценного окна настроек LSwitch на
основе всех поддерживаемых ключей `config.toml`. Главные требования: все
настройки активной сессии применяются без перезапуска, сохранение выполняется
транзакционно, а зависимые элементы формы визуально отключаются вместе с
родительской функцией без потери своих значений.

## Статус реализации

Основная реализация завершена 2026-07-13:

- этапы 0–6 реализованы и покрыты automated tests;
- все 33 leaf-параметра подключены к пяти страницам GUI;
- GUI, tray и SIGHUP используют единый транзакционный controller;
- словари и mid-word detector подготавливаются до commit;
- README, TOML comments/example и RU/EN labels актуализированы;
- отдельный manual checklist находится в
  `docs/GUI_SETTINGS_MANUAL_TESTING.md`.

Automated и offscreen Qt проверки выполнены. Реальные X11 и KDE Wayland
manual-сценарии оставлены в статусе «ожидает соответствующей графической
сессии» и не отмечаются как пройденные из headless окружения.

## 1. Цель

Нужно получить единый путь изменения конфигурации для GUI, tray menu и SIGHUP:

```text
GUI draft / tray action / external TOML reload
  -> validate and normalize candidate
  -> calculate changed dotted paths
  -> prepare fallible runtime resources
  -> atomically persist and commit config
  -> atomically reconfigure runtime components
  -> publish CONFIG_CHANGED notification
```

Итоговое поведение:

- окно показывает все 33 текущих параметра `DEFAULT_CONFIG`;
- `Отмена` никогда не меняет конфиг или runtime;
- `Применить` и `OK` вступают в силу без перезапуска процесса;
- ошибка валидации, подготовки runtime или записи файла не оставляет частично
  примененное состояние;
- изменение из tray menu и изменение из окна используют один контроллер;
- внешнее изменение TOML с последующим SIGHUP проходит через тот же runtime
  applier;
- GUI и tray menu синхронизируются только после успешного commit;
- выключенные дочерние настройки сохраняют введенные значения и снова
  становятся доступными после включения родителя;
- GUI скрывает параметры неактивной графической платформы. Если тип сессии
  определить не удалось, GUI показывает обе группы и честное предупреждение о
  возможной некорректной работе LSwitch.

Для настроек неактивной платформы действует естественное ограничение: в X11
нет живого Wayland adapter-а, а в Wayland нет X11 selection poller-а. Такие
поля скрыты, но их значения остаются в `config.toml` и будут переданы adapter-у
при следующем запуске в соответствующей сессии. Применение других параметров
не меняет скрытые значения. Если adapter текущей платформы существует, его
параметры обязаны обновляться на лету.

## 2. Исходное состояние

До реализации плана существовали несколько разрозненных механизмов:

- `DEFAULT_CONFIG` содержит 15 верхнеуровневых значений и 18 значений в
  timing-секциях;
- `ConfigDialog` показывает только `auto_switch`, `auto_switch_threshold`,
  `user_dict_enabled` и `double_click_timeout`;
- окно не подключено к tray menu;
- диалог вызывает несколько `config.set()`, игнорирует результат `save()` и
  публикует `CONFIG_CHANGED`, даже если запись завершилась ошибкой;
- `ConfigManager.get_all()` возвращает неглубокую копию, поэтому изменение
  вложенного draft может случайно изменить рабочий конфиг до нажатия
  `Применить`;
- tray menu самостоятельно делает `set()` + `save()`, обходя общий контракт;
- runtime reload уже обновляет часть timing и словарных объектов, но не
  `VirtualKeyboard`, platform selection adapters, poller interval, Wayland
  strategy и logging level;
- `CONFIG_CHANGED` доставляется синхронным EventBus, который логирует и
  подавляет исключения обработчиков. Поэтому это событие нельзя использовать
  как транзакционную команду;
- `switch_layout_after_convert`, `layout_switch_key` и TOML-параметр `debug`
  не подключены к заявленному поведению полностью.

Отдельное расхождение: `auto_switch_threshold` сейчас проверяется как
минимальное число символов в буфере перед space auto-conversion, а UI/README
местами описывают его как процент уверенности или n-gram sensitivity. В GUI
нужно показывать реальный смысл параметра и синхронно исправить документацию.

## 3. Границы задачи

В задачу входят:

- транзакционное API конфигурации;
- единый runtime config controller;
- live reconfigure всех существующих runtime consumers;
- подключение трех неработающих параметров;
- полноценный PyQt6 settings dialog;
- визуальные зависимости контролов;
- интеграция с tray menu;
- русская и английская локализация;
- automated tests и manual QA сценарии;
- обновление README и примера TOML при изменении описаний.

В задачу не входят:

- raw TOML editor внутри GUI;
- автоматическая генерация всей формы только по типам значений из TOML;
- переход на полноценные `LayoutProfile` / `ConversionPair`;
- расширение языков за пределы текущего runtime;
- изменение алгоритмов AutoDetector и MidWordDetector, кроме корректной
  передачи обновленных параметров;
- автоматический перезапуск процесса или systemd service.

## 4. Зафиксированные продуктовые решения

### 4.1 Применение

- Виджеты редактируют локальный draft.
- Runtime не меняется при каждом клике или вводе символа.
- `Применить` сохраняет и применяет draft, не закрывая окно.
- `OK` выполняет тот же commit и закрывает окно только при успехе.
- `Отмена` закрывает окно без commit.
- Повторное открытие всегда начинает с актуального committed snapshot.
- Если конфиг изменился через tray, пока открыт чистый dialog, dialog
  обновляется. Если dialog dirty, внешний change не перетирает draft: GUI
  показывает уведомление и при commit объединяет только измененные пользователем
  dotted paths с последним committed snapshot.

### 4.2 Сброс

- `Сбросить страницу` меняет только draft текущей страницы.
- `Сбросить всё` меняет весь draft на глубокую копию `DEFAULT_CONFIG`.
- Сам сброс не пишет файл и не меняет runtime до `Применить`/`OK`.
- Сброс затрагивает и визуально выключенные дочерние значения.

### 4.3 Явная форма вместо полностью динамической

TOML содержит значения, но не содержит UX-метаданные: подписи, описания,
единицы измерения, widget type, допустимый диапазон, зависимости и platform
context. Поэтому страницы строятся явно. Для чтения и записи используется
общий binding registry по dotted paths, например:

```text
auto_switch
timing.key_press_delay
wayland_selection_timing.copy_wait_timeout
```

Это уменьшает дублирование, но оставляет возможность сделать разные UX-контролы
для shortcut, dictionary path и Wayland strategy.

## 5. Семантика трех подключаемых параметров

### 5.1 `switch_layout_after_convert`

Существующее имя сохраняется ради совместимости с TOML, но подпись GUI должна
точнее отражать смысл:

```text
Оставлять раскладку результата после конвертации
```

Контракт:

- `true`: после успешной ручной или автоматической конвертации активной остается
  раскладка результата;
- `false`: операция при необходимости временно переключается на target layout,
  вводит/вставляет результат и восстанавливает layout, активный перед началом
  операции;
- правило применяется к typed retype, selection conversion, space auto,
  mid-word и undo/correction flows;
- при смешанном selection и `true` остается layout последнего конвертированного
  language run;
- при `false` исходный layout восстанавливается только после успешного ввода;
  при частичной ошибке выполняется best-effort restore с явным error log.

Нельзя реализовывать `false` простым пропуском target switch: replay физических
key events в исходной раскладке воспроизведет исходный, а не конвертированный
текст.

### 5.2 `layout_switch_key`

Прямое переключение на конкретный layout через XKB/D-Bus остается основным
механизмом. Это необходимо для конфигураций с тремя и более раскладками.

`layout_switch_key` становится live-configurable fallback:

- используется, если backend не может установить target layout напрямую;
- используется для cycle switch, когда target неизвестен;
- после отправки shortcut runtime повторно читает текущий layout и проверяет
  результат;
- для достижения известного target допускается не более `len(layouts) - 1`
  циклических переключений;
- неуспешная проверка завершает conversion с ошибкой, а не продолжает replay в
  неизвестной раскладке.

Нужен единый parser/normalizer shortcut-ов:

- сохранить поддержку legacy формата `Alt_L+Shift_L`,
  `Ctrl_L+Shift_L`, `Caps_Lock`;
- принимать нормализованный GUI-формат `Alt+Shift`, `Ctrl+Shift`, `Meta+Space`;
- валидировать все key names до commit;
- хранить в TOML стабильное каноническое представление;
- `QKeySequenceEdit` не должен напрямую определять внутренний формат без
  нормализации.

В GUI параметр следует назвать `Резервная комбинация переключения` и дать
пояснение о приоритете XKB/D-Bus.

### 5.3 `debug`

`debug` становится runtime-настройкой:

- меняет logging level между `INFO` и `DEBUG`;
- обновляет debug flags уже созданных компонентов;
- немедленно показывает или скрывает action `Debug Monitor` в tray menu;
- открытый monitor не уничтожается принудительно при выключении: action
  скрывается, новые подробные записи прекращаются, окно можно закрыть обычно.

CLI precedence:

- `--trace` является process-level override и удерживает уровень `TRACE`;
- `--debug` включает debug на старте без обязательной записи в TOML;
- после старта изменение GUI может включать и выключать effective debug, если
  процесс не запущен с `--trace`;
- GUI должен показывать пояснение, если `--trace` не позволяет понизить
  effective log level.

## 6. Полный реестр live-применения

| Config path | Runtime consumer | Live action |
|---|---|---|
| `double_click_timeout` | `StateManager` | заменить timeout |
| `debug` | logging и debug-capable components | изменить level и flags |
| `switch_layout_after_convert` | layout conversion policy | атомарно заменить policy snapshot |
| `layout_switch_key` | layout switch controller | заменить parsed fallback shortcut |
| `auto_switch` | input routing | следующий `Space` читает новый snapshot |
| `auto_switch_threshold` | space auto-conversion | следующий candidate использует новый минимум символов |
| `auto_switch_mid_word` | input routing / mid-word runtime | включить/выключить и подготовить detector |
| `mid_word_min_prefix_len` | `MidWordDetector` | построить новый detector и swap |
| `system_dict_enabled` | prefix dictionary runtime | подготовить новый dictionary runtime и swap |
| `system_dict_en_path` | system dictionary loader | загрузить EN candidate до commit |
| `system_dict_ru_path` | system dictionary loader | загрузить RU candidate до commit |
| `user_dict_enabled` | user dictionary runtime | подключить или отсоединить shared instance |
| `user_dict_auto_confirm` | space auto-conversion | следующий result читает новый snapshot |
| `user_dict_min_weight` | auto/mid-word detectors | обновить detector references/weight |
| `wayland_selection_strategy` | `WaylandSelectionAdapter` | normalize, clear transient selection state, apply strategy |
| `timing.key_press_delay` | `VirtualKeyboard` | заменить press delay |
| `timing.key_repeat_delay` | `VirtualKeyboard` | заменить repeat delay |
| `timing.retype_before_replay_delay` | manual retype | следующий use case читает новый snapshot |
| `timing.direct_type_after_layout_switch_delay` | direct selection typing | следующий mode читает новый snapshot |
| `timing.undo_before_replay_delay` | undo flow | следующий undo читает новый snapshot |
| `timing.auto_before_replay_delay` | space auto flow | следующий use case читает новый snapshot |
| `timing.auto_before_space_delay` | space auto flow | следующий use case читает новый snapshot |
| `x11_selection_timing.poll_interval` | `SelectionPollerThread` | thread-safe interval update и wake-up |
| `x11_selection_timing.paste_delay` | `X11SelectionAdapter` | заменить timing snapshot |
| `x11_selection_timing.restore_delay` | `X11SelectionAdapter` | заменить timing snapshot |
| `x11_selection_timing.expand_selection_delay` | `X11SelectionAdapter` | заменить timing snapshot |
| `wayland_timing.wl_clipboard_timeout` | `WaylandSystemAdapter` | заменить command timeout |
| `wayland_selection_timing.copy_wait_timeout` | `WaylandSelectionAdapter` | заменить timing snapshot |
| `wayland_selection_timing.copy_poll_interval` | `WaylandSelectionAdapter` | заменить timing snapshot |
| `wayland_selection_timing.copy_retry_delay` | `WaylandSelectionAdapter` | заменить timing snapshot |
| `wayland_selection_timing.paste_delay` | `WaylandSelectionAdapter` | заменить timing snapshot |
| `wayland_selection_timing.restore_delay` | `WaylandSelectionAdapter` | заменить timing snapshot |
| `wayland_selection_timing.expand_selection_delay` | `WaylandSelectionAdapter` | заменить timing snapshot |

Таблица является checklist: параметр нельзя считать реализованным, пока есть
тест, проверяющий изменение именно существующего runtime object без его
process-level restart.

## 7. Конфигурационная транзакция

### 7.1 Snapshot и diff

Добавить явные модели:

```text
ConfigSnapshot
  values: deep immutable/owned config tree

ConfigChangeSet
  old: ConfigSnapshot
  new: ConfigSnapshot
  changed_paths: frozenset[str]
  source: "gui" | "tray" | "sighup"

ConfigApplyResult
  ok: bool
  changed_paths: frozenset[str]
  error: str | None
```

Минимальное требование к immutability: вложенные таблицы никогда не изменяются
in-place. Новый normalized dict подготавливается целиком, после чего ссылка на
него заменяется под lock. `get_all()` должен возвращать `deepcopy` или отдельный
snapshot, а не ссылки на внутренние timing dicts.

Diff вычисляется рекурсивно по dotted paths. GUI применяет только свои dirty
paths поверх последнего committed snapshot, чтобы не затереть изменение из
tray menu, сделанное во время открытого окна.

### 7.2 Контроллер

Добавить единый API, например:

```text
RuntimeConfigController.apply(candidate, source, persist=True)
```

Порядок:

1. Сделать deep copy candidate.
2. Вызвать `validate_config()` и получить normalized config.
3. Построить `ConfigChangeSet`; при пустом diff вернуть success без записи и
   runtime churn.
4. Выполнить `RuntimeConfigApplier.prepare(change_set)` без изменения текущего
   runtime:
   - распарсить shortcut;
   - проверить platform strategy;
   - подготовить новые словари/detectors;
   - подготовить immutable timing/policy snapshots.
5. Атомарно записать TOML и заменить config snapshot в памяти.
6. Выполнить только non-failing `commit(prepared)` для runtime references и
   числовых setters.
7. При неожиданной ошибке commit восстановить старый snapshot/runtime и
   атомарно вернуть старый TOML.
8. Только после полного успеха опубликовать `CONFIG_CHANGED` как уведомление.

Для SIGHUP `persist=False`: файл уже изменен внешним редактором. При ошибке
runtime preparation старый memory/runtime snapshot остается активным, ошибка
логируется, внешний файл не переписывается автоматически.

### 7.3 Все writers используют контроллер

Запрещается оставлять отдельные пути `set()` + `save()`:

- `ConfigDialog` вызывает controller;
- tray actions `auto_switch` и `user_dict_enabled` вызывают controller;
- SIGHUP загружает candidate и вызывает controller;
- будущие DBus/CLI writers должны использовать тот же API.

`CONFIG_CHANGED.data` должен содержать хотя бы `changed_paths` и `source`, чтобы
tray и dialog могли обновлять только затронутые controls.

## 8. Runtime reconfiguration

### 8.1 Общий applier

Расширить `lswitch/runtime_config.py` до orchestration layer, но не переносить
туда platform-specific детали. Он вызывает capability methods существующих
объектов:

```text
virtual_keyboard.reconfigure_timing(timing)
selection.reconfigure(...)
system.reconfigure(...)
selection_poller.set_poll_interval(value)
logging_controller.reconfigure(debug)
layout_switch_controller.reconfigure(policy, shortcut)
```

Методы должны принимать уже validated значения и не читать TOML самостоятельно.

### 8.2 Thread safety

Настройки применяются Qt thread-ом, а ввод и selection polling работают в
фоновых потоках. Поэтому:

- нельзя изменять общий timing dict in-place;
- conversion/use case захватывает один snapshot в начале операции и завершает
  ее с согласованным набором значений;
- adapter заменяет целиком immutable timing snapshot либо обновляет поля под
  собственным lock;
- dictionary/prefix runtime сначала полностью строится, затем одна ссылка
  атомарно заменяется;
- `SelectionPollerThread` использует `threading.Event.wait(timeout)` вместо
  `time.sleep()`; setter обновляет interval под lock и будит thread;
- изменение Wayland strategy очищает `_saved_clipboard`, passive freshness и
  связанный `SelectionFreshnessTracker`, чтобы state старой стратегии не
  использовался новой;
- изменение config во время conversion не прерывает текущую операцию: новый
  snapshot используется со следующего пользовательского события.

### 8.3 Словари

System dictionary reload может быть дорогим. `prepare()` должен строить новый
prefix runtime вне активной ссылки. В GUI на время подготовки показывается
состояние `Применение настроек…`, повторный commit блокируется.

Если explicit `.dic` path не пуст:

- path должен существовать, быть обычным читаемым файлом;
- ошибка загрузки показывается пользователю и отменяет commit;
- пустая строка продолжает означать auto-discovery;
- старый detector остается рабочим до успешного swap.

## 9. Layout switch policy

Добавить отдельный component, не привязывая core use cases к GUI или TOML:

```text
LayoutSwitchPolicy
  keep_target_after_conversion: bool
  fallback_shortcut: ParsedKeySequence

LayoutSwitchController
  current_layout()
  switch_to(target)
  cycle()
  restore(layout)
```

Controller делегирует основную операцию `IXKBAdapter`, а fallback shortcut
отправляет через `VirtualKeyboard`. Retype/selection/auto flows получают
controller или policy snapshot, а не читают config напрямую.

Для compatibility с будущим `LAYOUT_PROFILE_ARCHITECTURE_PLAN.md` API должен
работать с конкретным `LayoutInfo` target и не предполагать, что layouts всегда
ровно две. Shortcut остается fallback, а не источником выбора conversion pair.

Acceptance для policy:

- typed manual conversion при `true` оставляет target layout;
- typed manual conversion при `false` вводит конвертированный текст и возвращает
  исходный layout;
- те же проверки проходят для space auto и mid-word;
- clipboard selection при `false` не делает лишний persistent switch;
- direct typing selection временно переключает layouts и восстанавливает
  исходный;
- mixed selection при `true` заканчивает на layout последнего converted run;
- backend failure запускает configured shortcut fallback;
- неверный shortcut не может попасть в committed config;
- multi-layout test достигает exact target и не делает бесконечный cycle.

## 10. Структура окна

Окно остается modeless и открывается единственным экземпляром из tray menu.
Повторный выбор `Настройки…` вызывает `show()`, `raise_()` и
`activateWindow()` существующего dialog.

Рекомендуемая компоновка:

```text
+---------------------------------------------------------------+
| Настройки LSwitch                                             |
|----------------------+----------------------------------------|
| Основные             | заголовок страницы                    |
| Автокоррекция        | краткие пояснения                      |
| Словари              | controls / groups / descriptions       |
| Выделение            |                                        |
| Дополнительно        |                                        |
|----------------------+----------------------------------------|
| Сбросить страницу  Сбросить всё   Отмена  Применить  OK       |
+---------------------------------------------------------------+
```

Использовать `QListWidget + QStackedWidget` или эквивалентную боковую навигацию,
`QScrollArea` для длинных страниц и нативные Qt styles без жестко заданной
цветовой темы. Ориентир минимального размера: 720x560, но окно должно корректно
работать на меньшем экране со scroll areas.

### 10.1 Основные

- `double_click_timeout` — `QDoubleSpinBox`, секунды;
- `switch_layout_after_convert` — checkbox с точной подписью;
- `layout_switch_key` — `QKeySequenceEdit` и пояснение fallback;
- краткий статус текущей platform/session.

### 10.2 Автокоррекция

- `auto_switch`;
- `auto_switch_threshold` с подписью `Минимум символов до автоконвертации`;
- `auto_switch_mid_word`;
- `mid_word_min_prefix_len`.

`auto_switch_threshold = 0` отображается как отсутствие дополнительного
ограничения. Виджет не должен ограничивать существующие валидные значения
максимумом 100 и незаметно менять TOML при простом открытии/сохранении.

### 10.3 Словари

- `system_dict_enabled`;
- `system_dict_en_path`, `system_dict_ru_path` — `QLineEdit` + `Обзор…`, filter
  `*.dic`, пустое значение означает auto-discovery;
- `user_dict_enabled`;
- `user_dict_auto_confirm`;
- `user_dict_min_weight`.

GUI показывает read-only статус фактически выбранных system dictionaries:
auto/explicit source, активный путь и число слов. Статусы `Не найден` и
`Отключён` отличаются явно; сами status-строки не являются настройками.

### 10.4 Выделение

- `wayland_selection_strategy` — `QComboBox` с пользовательскими названиями и
  внутренними values `auto`, `clipboard_copy`, `primary_selection`, `disabled`;
- X11 selection timings;
- Wayland system/selection timings;
- в X11 скрываются Wayland strategy и timings;
- в Wayland скрываются X11 selection timings;
- при неизвестном типе сессии обе группы остаются видимыми, а на общей
  странице выводится предупреждение, что окружение не определено и LSwitch
  может работать некорректно.

Скрытие влияет только на представление: значения неактивной платформы
сохраняются в draft и `config.toml` без изменений.

Для каждой Wayland strategy нужен краткий текст с последствиями для clipboard
и direct typing.

### 10.5 Дополнительно

- `debug`;
- общие `[timing]` values;
- путь к `config.toml` как read-only text;
- optional action копирования пути, но без обязательного запуска внешнего
  редактора.

Все timing controls используют секунды, достаточное число decimal places
(не менее 6) и диапазон валидатора `0.0..30.0`. Простое открытие и `OK` без
изменений не должно округлять существующие значения.

## 11. Визуальные зависимости

Зависимость управляет `enabled` state controls, label, browse button и help
text как единой группы. Значение disabled control не сбрасывается.

| Условие | Визуально отключаемые параметры |
|---|---|
| `auto_switch == false` | `auto_switch_threshold` |
| `auto_switch_mid_word == false` | `mid_word_min_prefix_len`, вся группа system dictionaries |
| `auto_switch_mid_word == true` и `system_dict_enabled == false` | `system_dict_en_path`, `system_dict_ru_path`, обе кнопки `Обзор…` |
| `user_dict_enabled == false` | `user_dict_min_weight`, `user_dict_auto_confirm` |
| `user_dict_enabled == true`, но `auto_switch == false` | только `user_dict_auto_confirm` |
| `wayland_selection_strategy == "disabled"` | все `wayland_selection_timing.*` |
| `wayland_selection_strategy == "primary_selection"` | `copy_wait_timeout`, `copy_poll_interval`, `copy_retry_delay`, `paste_delay`, `restore_delay`; `expand_selection_delay` остается доступным |

Дополнительные правила:

- изменение parent немедленно обновляет визуальное состояние draft, но runtime
  меняется только после commit;
- tooltip disabled group объясняет, какую функцию нужно включить;
- keyboard focus не должен попадать на disabled controls;
- dependency logic хранится отдельно от layout construction и покрывается
  table-driven tests;
- при Reset dependency state пересчитывается после установки всех значений, а
  не после каждого отдельного widget update.

## 12. Валидация и отсутствие потерь

GUI не является заменой `validate_config()`. Перед commit всегда валидируется
весь candidate.

Нужно устранить расхождения:

- `double_click_timeout`: `0.05..10.0`;
- `mid_word_min_prefix_len`: `1..32`;
- все timing: `0.0..30.0`;
- `auto_switch_threshold`: integer `>= 0`, реальный смысл — минимальное число
  buffered characters, не confidence percentage;
- `user_dict_min_weight`: integer `>= 0`;
- shortcut проходит parser validation;
- Wayland strategy берется только из допустимого enum;
- explicit dictionary paths проверяются на этапе prepare.

Для integer без верхней границы Qt widget должен использовать достаточно
большой технический maximum и показывать validation error вместо silent clamp.
Для float важно не уменьшать precision при roundtrip. Неизмененный widget не
должен считаться dirty только из-за display formatting.

## 13. Синхронизация tray menu

В `ContextMenu` добавить action `Настройки…` и хранить один `ConfigDialog`.

Текущие быстрые actions остаются:

- `Автопереключение`;
- `Самообучающийся словарь`.

Но они:

- формируют candidate от последнего snapshot;
- вызывают общий controller;
- меняют checked state только после success;
- при ошибке возвращают прежнее состояние и показывают error;
- обновляют открытый settings dialog через successful notification.

`Debug Monitor` action создается один раз и меняет visibility при live `debug`,
вместо полного rebuild menu.

## 14. Предлагаемые изменения по файлам

### Config и runtime

- `lswitch/config.py`
  - deep snapshots;
  - recursive dotted-path diff/merge;
  - validated atomic commit с rollback result;
  - исключить in-place mutation вложенных секций.
- `lswitch/runtime_config.py`
  - `ConfigChangeSet` / prepared runtime update;
  - orchestration всех live setters;
  - dictionary prepare/swap;
  - debug propagation.
- `lswitch/core/layout_switch_controller.py` (новый)
  - policy;
  - parsed fallback shortcut;
  - direct target switch, cycle, restore и verification.
- `lswitch/core/retype_service.py`, `lswitch/core/modes.py`,
  `lswitch/core/conversion_use_cases.py`, `lswitch/runtime_conversion.py`
  - принимать layout policy/controller snapshot;
  - реализовать restore semantics.
- `lswitch/runtime_lifecycle.py`
  - live poll interval;
  - SIGHUP через общий controller.
- `lswitch/app.py`
  - владение controller/applier;
  - передача одного apply callback GUI и tray;
  - исключить частичную ручную sync-логику.

### Platform components

- `lswitch/input/virtual_keyboard.py`
  - shortcut parser integration;
  - live timing/debug setters.
- `lswitch/platform/selection_adapter.py`
  - X11 timing/debug reconfigure.
- `lswitch/platform/wayland.py`
  - system timeout reconfigure;
  - strategy/timing/debug reconfigure;
  - очистка transient selection state.
- platform XKB adapters
  - standardized debug setter при необходимости;
  - не встраивать чтение config.

### GUI

- `lswitch/ui/config_dialog.py`
  - shell, pages, buttons, dirty state, commit result handling.
- `lswitch/ui/settings_model.py` (новый, без Qt)
  - draft, bindings metadata, dotted get/set, dirty paths, dependency rules.
- `lswitch/ui/context_menu.py`
  - settings action, singleton dialog, controller-based toggles, sync.
- `lswitch/i18n.py`
  - все labels, descriptions, errors и strategy names на RU/EN.
- `README.md`, `config/config.toml.example`
  - актуальная семантика threshold, layout policy, shortcut fallback и live
    settings.

Имена новых классов можно уточнить при реализации, но разделение обязанностей
между config storage, runtime application и Qt presentation обязательно.

## 15. Этапы реализации

### Этап 0 — characterization tests

- Зафиксировать текущие 33 config paths.
- Добавить тесты реальной семантики `auto_switch_threshold`.
- Зафиксировать текущее поведение retype/selection/auto layout switching.
- Зафиксировать, какие runtime object identities должны сохраняться при reload.

Acceptance:

- тесты падают при потере любого config path;
- layout behavior описан тестами до изменения policy;
- текущий suite проходит.

### Этап 1 — транзакционный config API

- Реализовать snapshot, diff, dirty-path merge и validated commit.
- Исправить `get_all()` deep-copy contract.
- Добавить rollback при ошибке записи.
- Перевести tray writers на controller API без изменения GUI.

Acceptance:

- nested draft не меняет live config;
- invalid candidate не пишет файл;
- simulated save failure сохраняет old memory/disk state;
- successful commit возвращает точный changed path set.

### Этап 2 — runtime reconfigure foundation

- Добавить prepare/commit applier.
- Реализовать immutable timing/policy snapshots.
- Подключить live debug и logging controller.
- Перевести SIGHUP на общий путь.

Acceptance:

- no-op change не вызывает setters;
- runtime failure откатывает GUI/tray commit;
- SIGHUP применяет valid file и отвергает invalid без потери старого runtime;
- `debug` меняется без restart.

### Этап 3 — все timing и platform settings live

- VirtualKeyboard timing.
- Conversion timing.
- X11 selection timing и poll interval.
- Wayland system/selection timing и strategy.
- Reset selection freshness при смене strategy.

Acceptance:

- каждый путь из timing-таблиц имеет отдельную runtime assertion;
- poller использует новый interval без пересоздания process;
- Wayland adapter object identity сохраняется;
- strategy change не использует stale clipboard state.

### Этап 4 — layout policy и три параметра

- Подключить `switch_layout_after_convert` ко всем conversion flows.
- Добавить shortcut parser и fallback controller.
- Подключить live `layout_switch_key`.
- Завершить propagation `debug` во все долгоживущие и short-lived services.

Acceptance:

- policy tests из раздела 9 проходят;
- legacy shortcuts продолжают читаться;
- invalid shortcut дает понятную ошибку до записи TOML;
- изменение shortcut используется следующей conversion без restart.

### Этап 5 — settings model и GUI

- Реализовать Qt-free draft/settings model.
- Построить пять страниц и bindings всех 33 paths.
- Реализовать dependency rules.
- Добавить Apply/OK/Cancel/reset/error states.
- Добавить RU/EN strings.

Acceptance:

- load/save/reset покрывают все config paths;
- Cancel не имеет side effects;
- save error оставляет dialog открытым;
- dependency matrix покрыта table-driven tests;
- unchanged open/OK не округляет float и не пишет файл без необходимости.

### Этап 6 — tray integration

- Добавить `Настройки…`.
- Обеспечить singleton dialog.
- Синхронизировать быстрые toggles, dialog и Debug Monitor action.
- Обработать внешний change при dirty dialog.

Acceptance:

- повторное открытие не создает второй dialog;
- tray change обновляет clean dialog;
- dirty dialog не затирается внешним change;
- checked state меняется только после successful commit.

### Этап 7 — документация и manual QA

- Обновить README и TOML example.
- Выполнить X11 и Wayland manual scenarios.
- Запустить полный test suite.
- Проверить package/install сценарий с GUI extras.

## 16. Automated test matrix

### Config

- roundtrip всех 33 paths;
- deep-copy isolation nested tables;
- recursive diff;
- dirty merge поверх более нового snapshot;
- invalid shortcut/path/strategy/value;
- atomic save success/failure;
- rollback memory + disk;
- no-op commit.

### Runtime

- каждый consumer из таблицы раздела 6;
- object identity для UInput, selection adapters и poller;
- atomic dictionary swap;
- debug propagation;
- Wayland strategy transient-state reset;
- concurrent snapshot read во время apply;
- SIGHUP valid/invalid.

### Layout policy

- manual retype true/false;
- selection clipboard true/false;
- Wayland direct typing true/false;
- space auto и mid-word true/false;
- undo/correction;
- mixed selection;
- backend direct success;
- backend failure + shortcut fallback;
- fallback verification failure;
- multi-layout exact target;
- legacy/canonical shortcut parsing.

### GUI

- все widgets загружают корректные values;
- каждый widget пишет правильный dotted path/type;
- nested timing не теряются;
- Apply, OK, Cancel;
- reset page/all;
- validation/save/runtime error presentation;
- dependency matrix;
- path browse empty/selected;
- Wayland combo value mapping;
- shortcut normalization;
- float precision/no unintended dirty state;
- singleton dialog и tray synchronization.

Qt-free `settings_model.py` должен получить основную часть unit coverage. Для
Qt layer оставить focused widget/wiring tests; существующие PyQt mocks придется
расширить либо заменить отдельные tests на offscreen Qt fixture, если это не
ухудшит CI portability.

## 17. Manual QA

### Общий сценарий

1. Запустить LSwitch без debug.
2. Открыть `Настройки…` из tray.
3. Проверить текущие значения из реального `~/.config/lswitch/config.toml`.
4. Изменить несколько параметров на разных страницах и нажать `Применить`.
5. Убедиться, что процесс/PID не изменился, TOML обновился, поведение изменилось.
6. Изменить draft и нажать `Отмена`; файл/runtime должны остаться прежними.
7. Проверить `Сбросить страницу` и `Сбросить всё` до и после commit.

### Зависимости

- выключить `auto_switch` и проверить threshold/auto-confirm states;
- выключить mid-word и проверить всю system dictionary group;
- включить mid-word, выключить system dictionary и проверить path rows;
- выключить user dictionary;
- перебрать все Wayland strategies;
- повторно включить parents и убедиться, что child values сохранились.

### Live runtime

- изменить double Shift timeout и проверить без restart;
- изменить VirtualKeyboard delays и убедиться по debug timing/logs;
- на X11 изменить selection poll interval и selection delays;
- на Wayland переключить `primary_selection` / `clipboard_copy` / `disabled`;
- включить debug и проверить появление Debug Monitor action и DEBUG logs;
- выключить debug и проверить обратное;
- изменить dictionary paths и mid-word prefix length;
- изменить user dictionary settings.

### Layout policy

- `switch_layout_after_convert=true`: ручная, auto и selection conversion
  оставляют target layout;
- `false`: результат текста корректный, layout возвращается к исходному;
- задать работающий fallback shortcut и принудительно смоделировать backend
  failure;
- проверить legacy `Alt_L+Shift_L` и canonical `Alt+Shift`;
- проверить систему с тремя layouts, если доступна.

## 18. Риски и меры

### Race между GUI и input thread

Мера: immutable snapshots, atomic reference swap, operation-local snapshot,
lock только на коротком commit участке.

### Частично примененная конфигурация

Мера: prepare/commit/rollback, event только после успеха, единый writer API.

### Зависание GUI при загрузке Hunspell

Мера: prepare вне активной ссылки, progress state; при необходимости вынести
dictionary build в worker и вернуть result в Qt thread.

### Неверный shortcut переключил не туда

Мера: parser validation, ограниченное число попыток, read-back verification,
fail conversion до replay при неизвестном layout.

### Restore layout после частичной ошибки

Мера: исходный layout фиксируется до операции, restore выполняется в guarded
finalization и отдельно логируется.

### Silent value clamping/rounding GUI

Мера: диапазоны синхронизированы с validator, достаточная precision, dirty
сравнивается по model values, а не display text.

### Будущий layout profile refactor

Мера: GUI bindings используют config paths, core получает target `LayoutInfo`
и policy/controller, shortcut остается fallback. Не добавлять новые EN/RU
ветвления ради settings dialog.

## 19. Definition of Done

- [x] Все 33 текущих config values представлены в GUI и корректно roundtrip-ятся.
- [x] Все параметры активной platform/runtime применяются после `Применить`
  без process restart.
- [x] Нет отдельного runtime writer path, обходящего config controller.
- [x] Config/runtime rollback работает при validation, preparation и save errors.
- [x] `switch_layout_after_convert`, `layout_switch_key`, `debug` имеют
  автоматизированно проверенное runtime-поведение.
- [x] Все зависимости визуально отключают controls и сохраняют child values.
- [x] GUI скрывает настройки неактивной платформы, сохраняет их значения и
  предупреждает при неизвестном типе сессии.
- [x] GUI показывает фактически загруженные system dictionaries и число слов.
- [x] Tray menu открывает один dialog и синхронизирован с ним.
- [x] SIGHUP использует тот же validation/runtime application path.
- [x] Изменение timing не требует пересоздания UInput или process.
- [x] README, TOML comments/example и RU/EN GUI labels описывают реальную
  семантику.
- [x] Полный automated test suite проходит.
- [x] X11 и Wayland manual QA выполнены или явно отмечены как ожидающие
  соответствующей сессии.

## 20. Рекомендуемый порядок коммитов

1. `add transactional config snapshots`
2. `add runtime config prepare commit pipeline`
3. `make platform timings and strategy live`
4. `add live logging configuration`
5. `add configurable layout switch policy`
6. `add settings draft model and dependencies`
7. `build full settings dialog`
8. `integrate settings dialog with tray`
9. `update settings documentation and manual qa`

Каждый коммит должен оставлять рабочий test suite. GUI следует начинать после
готовности транзакционного controller и live setters, чтобы форма с первого дня
подключалась к окончательному пути применения, а не к временному набору
`config.set()`.
