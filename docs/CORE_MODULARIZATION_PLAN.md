# Core modularization plan

Дата: 2026-07-07

Этот файл фиксирует общий план приведения LSwitch к более чистой модульной
архитектуре перед разработкой новых feature-планов:

- `MID_WORD_SYSTEM_DICTIONARY_PLAN.md`;
- `PER_APP_LAYOUT_MEMORY_PLAN.md`;
- `LAYOUT_PROFILE_ARCHITECTURE_PLAN.md`.

Цель - сначала стабилизировать ядро приложения и уменьшить роль `LSwitchApp`,
а уже потом добавлять новые режимы автопереключения, память раскладки и более
общую модель layout profiles.

## 1. Текущее состояние

В проекте уже есть полезное разделение по слоям:

```text
lswitch/input/         evdev devices, raw input, virtual keyboard
lswitch/platform/      X11/Wayland adapters, selection, layout switching
lswitch/core/          state machine, events, conversion modes
lswitch/intelligence/  dictionaries, n-grams, auto detector, user dictionary
lswitch/ui/            tray, config dialog, debug monitor
lswitch/app.py         composition, lifecycle, runtime orchestration
```

Сильные места текущей архитектуры:

- platform factory скрывает X11/Wayland выбор за adapter set;
- `IXKBAdapter`, `ISelectionAdapter`, `ISystemAdapter` дают нормальные ports;
- `RetypeMode` и `SelectionMode` уже отделяют два способа конвертации;
- `AutoDetector`, `DictionaryService`, `NgramAnalyzer` в целом изолированы от
  platform IO;
- тестовая база уже покрывает много регрессий вокруг conversion flow.

Главная проблема: `LSwitchApp` постепенно стал не только composition root, но и
носителем продуктовой логики.

Сейчас `LSwitchApp` отвечает за:

- создание runtime компонентов;
- wiring `EventBus`;
- обработку key press/release/repeat;
- поддержку typed buffer;
- selection freshness tracking;
- manual conversion orchestration;
- space-triggered auto-conversion;
- undo последней auto-conversion;
- user dictionary learning;
- runtime config reload;
- mouse selection baseline logic;
- poller lifecycle;
- main loop lifecycle.

Это делает новые features дорогими: каждая новая возможность требует новых
полей, guards и side effects в одном классе.

## 2. Целевая архитектура

Нужен не большой rewrite, а постепенный переход к application services /
use-case architecture:

```text
CLI / UI / daemon lifecycle
  -> LSwitchApp as composition root
    -> InputEventRouter
      -> GestureController
      -> TypingController
      -> SelectionFreshnessTracker
      -> ManualConversionController
      -> AutoSwitchController
    -> Application services
      -> ConversionUseCases
      -> RetypeService
      -> SelectionReplacementService
      -> LayoutService
      -> LearningService
    -> Ports/adapters
      -> IXKBAdapter
      -> ISelectionAdapter
      -> ISystemAdapter
      -> VirtualKeyboard
```

`LSwitchApp` в целевом виде должен:

- загружать config;
- создавать adapters и services;
- связывать event handlers;
- запускать/останавливать loop, pollers и monitors;
- делегировать доменные действия в controllers/use cases.

`LSwitchApp` не должен:

- вручную добавлять и удалять события из typed buffer;
- знать детали replay/backspace/switch layout;
- хранить dict marker для undo;
- решать, как учить user dictionary;
- содержать EN/RU-specific helpers;
- содержать policy для каждой feature.

## 3. Принципы миграции

1. Поведенчески нейтральные шаги.
   Каждый этап должен сохранять существующее поведение и проходить текущие
   тесты.

2. Сначала выделять services, потом менять behavior.
   Новые features подключать только после того, как существующий flow работает
   через выделенные компоненты.

3. Не ломать platform layer.
   X11/Wayland adapters уже являются полезной границей. Их нужно расширять
   capability-based подходом, а не втягивать platform details в core.

4. Сохранять `LSwitchApp` как facade на время миграции.
   Тесты могут продолжать создавать `LSwitchApp`, но внутри он должен
   делегировать в новые классы.

5. Не вводить абстракции "на будущее" без переноса реальной логики.
   Каждый новый сервис должен забрать конкретный кусок ответственности из
   текущего кода.

## 4. Предлагаемые модули

### 4.1 Runtime composition

```text
lswitch/app.py
lswitch/runtime.py
```

`LSwitchApp` можно оставить публичной точкой входа, но постепенно перенести
сборку runtime graph в отдельный модуль:

```text
RuntimeComponents
  event_bus
  state_manager
  input_router
  controllers
  services
  platform_adapters
```

Это позволит тестировать wiring отдельно и держать `app.py` короче.

### 4.2 Input routing

```text
lswitch/core/input_router.py
```

`InputEventRouter` получает typed `Event` из `EventBus` и распределяет его:

```text
on_key_press(event)
on_key_release(event)
on_key_repeat(event)
on_mouse_click(event)
on_mouse_release(event)
```

На первом этапе router может просто делегировать существующие методы
`LSwitchApp`. Затем в него переезжают:

- modifier handling;
- pending-space handling;
- navigation reset;
- routing к typing/gesture/selection controllers.

### 4.3 Typed buffer

```text
lswitch/core/typed_buffer.py
```

Отдельный сервис для:

- append key event;
- remove last event;
- backspace repeat;
- decode buffer;
- extract last word;
- extract current token;
- classify token eligibility for auto modes.

Этот этап совпадает с `MID_WORD_REFACTORING_PLAN.md`, но является частью более
общей модульной архитектуры.

### 4.4 Gesture controller

```text
lswitch/core/gesture_controller.py
```

Отвечает за:

- Shift down/up;
- double Shift detection;
- Backspace hold;
- state transitions вокруг gestures.

Сейчас часть этого есть в `StateManager`, но controller должен стать местом,
которое переводит low-level key events в high-level commands:

```text
ManualConversionRequested
SelectionExpandRequested
NavigationResetRequested
```

### 4.5 Selection freshness tracker

```text
lswitch/core/selection_tracker.py
```

Отвечает за:

- `_selection_valid`;
- `_selection_generation`;
- `_selection_repeat_valid`;
- baseline text/owner;
- mouse click/release baseline update;
- poller callback handling.

Это один из самых независимых кусков `LSwitchApp`. Его можно вынести рано,
потому что он почти не зависит от dictionaries или conversion algorithm.

### 4.6 Conversion use cases

```text
lswitch/core/conversion_use_cases.py
```

Разделить текущую `_do_conversion()` на явные сценарии:

```text
ManualConversionUseCase
  - choose retype/selection mode;
  - execute conversion;
  - return ConversionResult.

UndoAutoConversionUseCase
  - consume AutoConversionMarker;
  - undo converted text;
  - record keep/correction.

SpaceAutoConversionUseCase
  - extract last word;
  - call AutoDetector;
  - execute retype to target layout;
  - create AutoConversionMarker.
```

Позже добавится:

```text
MidWordAutoConversionUseCase
PerAppLayoutMemoryUseCase
```

### 4.7 Retype service

```text
lswitch/core/retype_service.py
```

Единый primitive для:

- delete N chars;
- switch to target layout или next layout;
- replay events;
- apply delay policy.

`RetypeMode` и auto-conversion должны использовать этот сервис.

### 4.8 Layout service

```text
lswitch/core/layout_service.py
```

Тонкий слой над `IXKBAdapter`:

- current layout;
- find layout by language;
- switch to lang;
- layout-to-lang mapping for current EN/RU implementation;
- future bridge to layout profiles.

Это временный шаг до полного `LAYOUT_PROFILE_ARCHITECTURE_PLAN.md`.

### 4.9 Learning service

```text
lswitch/core/learning_service.py
```

Отвечает за user dictionary side effects:

- manual conversion confirmation;
- selection conversion keep/correction;
- auto-conversion undo correction;
- optional auto-confirm.

`AutoDetector` должен читать user dictionary, но запись решений лучше держать
в отдельном use-case/service слое.

### 4.10 Auto marker

```text
lswitch/core/auto_marker.py
```

Явная модель последней auto-conversion вместо dict:

```text
AutoConversionMarker
  kind
  original_word
  original_lang
  target_lang
  direction
  word_events
  converted_len
  had_space
  created_at
```

Это нужно для текущего undo и для будущего mid-word undo.

## 5. Новый поток событий

Желаемый поток после модульного рефакторинга:

```text
DeviceManager
  -> EventManager.handle_raw_event()
    -> EventBus.publish(KEY_PRESS)
      -> InputEventRouter.on_key_press()
        -> GestureController / TypingController
          -> commands
            -> ConversionUseCase / AutoSwitchController
```

Где commands - не обязательно отдельные классы на первом этапе. Можно начать с
простых return values:

```text
GestureResult(kind="manual_conversion_requested")
TypingResult(kind="space_pressed", token=...)
AutoSwitchResult(kind="converted", marker=...)
```

Главное - перестать размазывать side effects по одному большому handler-у.

## 6. Этапы работ

### Этап 1 - Зафиксировать текущие границы и regression coverage

Цель: перед переносом логики убедиться, что основные сценарии покрыты.

Проверить и при необходимости дополнить тесты:

- manual retype conversion;
- selection conversion;
- space-triggered auto-conversion;
- Shift+Shift undo after auto-conversion;
- repeated Shift+Shift selection conversion;
- selection freshness через mouse release/poller;
- config reload user dictionary enable/disable.

Acceptance:

- текущий test suite проходит;
- есть короткий список core scenarios, которые нельзя сломать;
- новые refactor PR не меняют behavior.

### Этап 2 - TypedBufferService

Перенести операции над `event_buffer` и word extraction из `LSwitchApp`.

Acceptance:

- `LSwitchApp._on_key_press()` больше не делает append/pop напрямую;
- `_decode_buffer()` и `_extract_last_word_events()` переехали или стали
  thin wrappers;
- тесты auto-conversion и buffer extraction проходят.

### Этап 3 - RetypeService

Вынести общий replay primitive из `RetypeMode` и
`_do_auto_conversion_at_space()`.

Acceptance:

- одно место делает `Backspace + switch_layout + replay_events`;
- `RetypeMode` стал thin wrapper;
- auto-conversion на `Space` сохраняет deferred Space behavior.

### Этап 4 - AutoConversionMarker + UndoAutoConversionUseCase

Заменить `_last_auto_marker` dict на dataclass и вынести undo path.

Acceptance:

- undo тесты не зависят от magic dict keys;
- marker lifecycle явно очищается на navigation/mouse/reset;
- текущий Shift+Shift undo работает как раньше.

### Этап 5 - SelectionFreshnessTracker

Вынести selection freshness и baseline tracking.

Acceptance:

- `LSwitchApp` не хранит напрямую `_selection_valid`,
  `_selection_generation`, repeat generation и baseline fields;
- mouse click/release handlers стали thin delegation;
- poller callback делегирует tracker-у.

### Этап 6 - LearningService

Вынести user dictionary writes из `_do_conversion()` и auto-conversion paths.

Acceptance:

- `LSwitchApp` не вызывает напрямую `add_confirmation()` /
  `add_correction()` кроме initialization;
- manual conversion, selection conversion и undo learning покрыты тестами;
- `AutoDetector` по-прежнему получает user dictionary для read decisions.

### Этап 7 - Conversion use cases

Разделить `_do_conversion()` на use cases.

Acceptance:

- `_do_conversion()` в `LSwitchApp` только проверяет state/request и вызывает
  use case;
- manual conversion и undo conversion имеют отдельные тесты без полного app
  lifecycle;
- `ConversionEngine` либо остается lower-level executor, либо переименовывается
  по фактической роли.

### Этап 8 - InputEventRouter

Перенести key/mouse event orchestration из `LSwitchApp`.

Acceptance:

- `LSwitchApp._wire_event_bus()` подписывает router handlers;
- `LSwitchApp` больше не содержит крупных `_on_key_press`,
  `_on_key_release`, `_on_key_repeat`, `_on_mouse_click`,
  `_on_mouse_release`;
- app tests можно постепенно заменить tests для router/controllers.

### Этап 9 - LayoutService

Вынести EN/RU layout helpers и target layout lookup.

Acceptance:

- `_layout_to_lang()` удален из `LSwitchApp`;
- `SelectionMode`, auto-conversion и future controllers используют одну
  реализацию поиска layout по language;
- это не полноценные layout profiles, а маленький стабилизирующий слой.

### Этап 10 - Runtime composition cleanup

Сократить `LSwitchApp` до lifecycle/composition root.

Acceptance:

- `LSwitchApp` создает компоненты, запускает loop, останавливает resources;
- продуктовая логика живет в controllers/use cases;
- новые feature flags можно подключать без добавления больших блоков в
  `app.py`.

## 7. Что делать после модульного ядра

После этапов 1-10 порядок feature-работ:

1. `MID_WORD_REFACTORING_PLAN.md` оставшиеся пункты, если не покрыты общим
   рефакторингом.
2. `PrefixDictionary` и `SystemDictionaryLoader`.
3. `MidWordAutoConversionUseCase`.
4. `PER_APP_LAYOUT_MEMORY_PLAN.md` через отдельный controller capability.
5. `LAYOUT_PROFILE_ARCHITECTURE_PLAN.md` как следующий большой слой, когда
   EN/RU helpers уже локализованы в `LayoutService`.

## 8. Файловая структура после миграции

Ориентировочный вид:

```text
lswitch/
  app.py                         # lifecycle facade
  runtime.py                     # component graph/wiring
  core/
    input_router.py
    typed_buffer.py
    gesture_controller.py
    selection_tracker.py
    conversion_use_cases.py
    conversion_engine.py
    retype_service.py
    layout_service.py
    learning_service.py
    auto_marker.py
    modes.py
    state_manager.py
    states.py
    events.py
  intelligence/
    auto_detector.py
    dictionary_service.py
    prefix_dictionary.py
    system_dictionary_loader.py
  platform/
    platform_factory.py
    xkb_adapter.py
    wayland.py
    selection_adapter.py
  input/
    device_manager.py
    event source helpers
  ui/
    tray/config/debug
```

Не обязательно создать все файлы сразу. Файл появляется только тогда, когда в
него переносится реальная логика.

## 9. Риски

### Слишком крупный PR

Риск: перенос сразу router + buffer + conversion приведет к сложной отладке.

Ответ: каждый этап должен иметь отдельный PR/commit и проходить тесты.

### Сломать тонкие timing/selection сценарии

Риск: selection freshness и deferred Space завязаны на порядок событий.

Ответ: сначала добавить/проверить regression tests, затем переносить код почти
механически.

### Перепроектировать раньше времени

Риск: попытка сразу построить идеальную domain architecture замедлит feature
работу.

Ответ: выделять только те компоненты, которые забирают существующую
ответственность из `LSwitchApp`.

### Распылить state

Риск: после выноса компонентов состояние станет сложнее отслеживать.

Ответ: ownership каждого state должен быть явным:

- typed events -> `TypedBufferService`;
- gesture state -> `StateManager` / `GestureController`;
- selection freshness -> `SelectionFreshnessTracker`;
- last auto conversion -> `AutoConversionMarkerStore` или поле controller-а;
- user learning writes -> `LearningService`.

## 10. Definition of done

Общий рефакторинг можно считать завершенным, когда:

- `LSwitchApp` меньше примерно 400-500 строк и не содержит feature policy;
- key/mouse handlers живут в router/controller слоях;
- conversion сценарии доступны как use cases и тестируются без полного daemon
  lifecycle;
- typed buffer не является сырым списком, которым вручную управляет `app.py`;
- replay/backspace/switch layout logic не дублируется;
- user dictionary writes централизованы;
- platform-specific код остается в `platform/*`;
- все существующие regression tests проходят.

После этого добавление mid-word/per-app/layout-profile features должно
выглядеть как подключение нового controller/use case, а не как расширение
монолитного `LSwitchApp`.
