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

## 6. Текущий статус рефакторинга

Мелкие этапы 1-10 из первой версии плана в основном уже закрыты или переведены
в compatibility facade. Дальше задачи нужно брать более крупными вертикальными
срезами, чтобы не продолжать бесконечное перемещение single-use helper-ов.

Выполнено:

- input routing переехал в `InputEventRouter`;
- typed buffer decode / last-word extraction живут в `TypedBufferService` и
  runtime helper-ах;
- replay/backspace/layout switching вынесены в `RetypeService`;
- auto-conversion marker стал typed model, transient state вынесен в
  `AutoConversionSessionState`;
- selection freshness и baseline state живут в `SelectionFreshnessTracker`;
- mouse release/click baseline, poller freshness и selection baseline helpers
  вынесены из `LSwitchApp`;
- manual/undo/space conversion flow живет в controllers/use cases;
- user dictionary learning side effects идут через `LearningService`;
- runtime config update, user dictionary enable, Qt/evdev loop composition,
  selection helpers, conversion boundary и resource lifecycle вынесены из
  `runtime.py` в отдельные runtime modules;
- input router получает conversion/selection зависимости через явные port
  objects, а не длинный список callback-ов;
- `LSwitchApp` больше не содержит крупных key/mouse handlers.

Осталось:

- `LSwitchApp` все еще содержит thin compatibility wrappers:
  `_do_conversion()`, `_try_auto_conversion_at_space()`,
  `_do_auto_conversion_at_space()`, `_space_auto_conversion()`;
- `LSwitchApp` сохраняет compatibility properties для старого внешнего API:
  `_selection_valid`, `_selection_generation`, `_prev_sel_text`,
  `_last_auto_marker`, `_pending_auto_space`;
- `runtime.py` все еще остается compatibility/composition module, но уже не
  содержит config/selection/lifecycle/conversion helper blocks физически;
- app-level tests почти не проверяют private conversion/session facade:
  остались только smoke tests для `_do_conversion()`;
- следующий этап - feature readiness gate перед возвратом к mid-word,
  per-app layout memory и layout profile планам.

## 7. Следующие крупные пакеты работ

### Пакет A - Conversion Runtime Facade

Статус: выполнено.

Цель: убрать conversion orchestration из `LSwitchApp`, не меняя behavior.

Сделать единый объект, например:

```text
ConversionRuntimeFacade
  request_manual_conversion()
  try_space_auto_conversion()
  perform_space_auto_conversion(...)
  extract_last_word(...)
  decode_buffer(...)
```

Он должен владеть wiring-ом:

- `ManualConversionController`;
- `SpaceAutoConversionUseCase`;
- `AutoConversionSessionState`;
- `SelectionFreshnessTracker` baseline updates;
- synced `LearningService`;
- accessors к platform adapters (`xkb`, `selection`, `virtual_kb`,
  `conversion_engine`).

Acceptance:

- `LSwitchApp._do_conversion()`, `_try_auto_conversion_at_space()`,
  `_do_auto_conversion_at_space()` становятся thin compatibility wrappers или
  удаляются из internal wiring;
- `InputRouterCallbacks` получает conversion callbacks от facade, а не от app
  lambdas;
- tests для manual/space conversion можно запускать без полного app lifecycle;
- текущий полный test suite проходит.

Фактический результат:

- `ConversionRuntimeFacade` создан и используется input router wiring-ом;
- app conversion methods стали thin compatibility wrappers;
- `DebugMonitor` и tests используют `conversion_runtime` /
  `auto_conversion_session` вместо private app fields.

### Пакет B - App Compatibility Facade Cleanup

Статус: выполнено для conversion/session surface, оставлен минимальный
compatibility smoke.

Цель: оставить `LSwitchApp` публичной точкой входа, но перестать использовать
его private fields как основной тестовый API.

Сделать:

- перевести часть tests с `app._selection_valid`,
  `app._last_auto_marker`, `app._extract_last_word_events()` на
  `SelectionFreshnessTracker`, `AutoConversionSessionState`,
  `TypedBufferService` и conversion facade;
- оставить в `LSwitchApp` минимальные compatibility properties только там, где
  их реально использует UI/debug monitor;
- убрать app wrappers, которые больше не нужны после перевода tests.

Acceptance:

- app tests покрывают lifecycle/wiring smoke cases;
- domain behavior покрывается tests соответствующих services/controllers;
- количество прямых обращений tests к `LSwitchApp._*` заметно снижено;
- полный test suite проходит.

Фактический результат:

- auto-conversion, user-dict, selection conversion, regression и debug monitor
  tests переведены на state owners/facade;
- в app tests остались только lifecycle/wiring smoke и `_do_conversion()`
  compatibility coverage.

### Пакет C - Runtime Module Split

Статус: выполнено как совместимый split.

Цель: не дать `runtime.py` стать новым god module.

Разделить `runtime.py` на несколько модулей без изменения public imports или с
малой совместимой прослойкой:

```text
lswitch/runtime.py              # temporary compatibility exports
lswitch/runtime/config.py       # config reload, timing, user dict sync
lswitch/runtime/composition.py  # core/platform/input/conversion factories
lswitch/runtime/lifecycle.py    # pid lock, evdev/Qt loops, resources
lswitch/runtime/selection.py    # selection baseline/poller helpers
lswitch/runtime/conversion.py   # conversion facade/factories/boundaries
```

Acceptance:

- `runtime.py` больше не содержит все helpers физически в одном файле;
- старые imports из `lswitch.runtime` либо продолжают работать, либо заменены
  одним механическим commit-ом;
- tests runtime/config/lifecycle/conversion остаются зелеными.

Фактический результат:

```text
lswitch/runtime.py              # compatibility exports + composition factories
lswitch/runtime_config.py       # config reload, timing, user dict sync
lswitch/runtime_lifecycle.py    # pid lock, evdev/Qt loops, resources
lswitch/runtime_selection.py    # selection baseline/poller helpers
lswitch/runtime_conversion.py   # conversion facade/factories/boundaries
```

### Пакет D - Input Router Callback Contract Cleanup

Статус: выполнено.

Цель: заменить часть callback soup на явные runtime/controller объекты.

Сделать:

- `InputRouterCallbacks.request_conversion` и
  `try_auto_conversion_at_space` перевести на `ConversionRuntimeFacade`;
- pending-space, marker clearing и sticky-events оставить через
  `AutoConversionSessionState`, а не отдельные lambdas;
- selection read/baseline callbacks сгруппировать в selection runtime object.

Acceptance:

- `InputRouterCallbacks` становится короче и читабельнее;
- `LSwitchApp.__init__` не собирает длинные callback lists;
- input router tests продолжают проверять behavior на уровне событий.

Фактический результат:

- `InputEventRouter` принимает `InputConversionPort` и `InputSelectionPort`;
- `InputRouterCallbacks` состоит из двух port objects;
- `LSwitchApp.__init__` передает `conversion_runtime` целиком, а не набор
  conversion lambdas.

### Пакет E - Feature Readiness Gate

Статус: следующий пакет.

Цель: определить, когда можно возвращаться к feature-планам
`MID_WORD_SYSTEM_DICTIONARY_PLAN.md`, `PER_APP_LAYOUT_MEMORY_PLAN.md` и
`LAYOUT_PROFILE_ARCHITECTURE_PLAN.md`.

Feature-работы можно начинать, когда выполнены условия:

- conversion facade существует и используется input router-ом;
- app private-field tests сокращены до lifecycle/facade smoke coverage;
- runtime module split хотя бы начат, чтобы новые capabilities не добавлялись в
  большой `runtime.py`;
- full suite зеленый;
- для mid-word есть отдельная точка расширения рядом с
  `SpaceAutoConversionUseCase`, а не новый блок в `LSwitchApp`.

Текущая оценка:

- первые четыре условия выполнены;
- перед стартом feature-работ нужно зафиксировать extension point для mid-word
  рядом с `SpaceAutoConversionUseCase` и обновить соответствующий feature plan;
- после этого можно переходить к `MID_WORD_SYSTEM_DICTIONARY_PLAN.md`.

## 8. Что делать после модульного ядра

После этапов 1-10 порядок feature-работ:

1. `MID_WORD_REFACTORING_PLAN.md` оставшиеся пункты, если не покрыты общим
   рефакторингом.
2. `PrefixDictionary` и `SystemDictionaryLoader`.
3. `MidWordAutoConversionUseCase`.
4. `PER_APP_LAYOUT_MEMORY_PLAN.md` через отдельный controller capability.
5. `LAYOUT_PROFILE_ARCHITECTURE_PLAN.md` как следующий большой слой, когда
   EN/RU helpers уже локализованы в `LayoutService`.

## 9. Файловая структура после миграции

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

## 10. Риски

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

## 11. Definition of done

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
