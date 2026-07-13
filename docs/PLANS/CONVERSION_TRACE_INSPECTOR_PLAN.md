# Conversion Trace Inspector в Debug Monitor

Дата: 2026-07-13

Статус: реализовано 2026-07-13; автоматические проверки добавлены, ручная
проверка X11/Wayland вынесена в `docs/CONVERSION_TRACE_MANUAL_TESTING.md`.

Уточнение после ручной проверки: MID_WORD trace имеет lifecycle
`ACTIVE`/`FINALIZED`. Успешная ранняя конвертация завершает текущий сегмент, но
correlation ID логического слова сохраняется до Space/Enter/navigation, поэтому
дописанный хвост визуально связан с конвертированным префиксом.

Документ описывает инструмент, который показывает путь принятия решения для
каждого проверенного слова: какие правила были проверены, какие факты получили
эти правила, какое правило стало решающим и удалось ли затем выполнить
конвертацию.

Инструмент размещается в Debug Monitor отдельной вкладкой и не использует
виджеты, текстовые логи или внутреннее состояние существующего монитора.
Текущее содержимое Debug Monitor считается legacy-интерфейсом: его нужно только
обернуть в отдельную вкладку, не переписывая в рамках этой задачи.

## 1. Цель

После реализации разработчик должен иметь возможность ответить на вопросы:

- почему слово было конвертировано;
- почему слово было оставлено без изменения;
- какое правило имело приоритет над остальными;
- какие словари, веса, prefix counts и n-gram scores участвовали в решении;
- какую исходную и целевую раскладку видел алгоритм;
- какой режим исполнения был выбран;
- отличалось ли решение «конвертировать» от фактического результата операции;
- на каком шаге произошла ошибка переключения раскладки, удаления или replay.

Главный контракт:

~~~text
input candidate
  -> structured detector decision
  -> ordered rule trace
  -> conversion execution trace
  -> bounded in-memory history
  -> independent Debug Monitor tab
~~~

GUI не должен повторно запускать детекторы, вычислять scores или восстанавливать
правила из строк журнала. Он только отображает immutable snapshot, созданный в
момент принятия решения.

## 2. Зафиксированные продуктовые решения

### 2.1 Размещение

- В Debug Monitor добавляется QTabWidget.
- Новая вкладка называется «Конвертации» / «Conversions».
- Новая вкладка открывается по умолчанию.
- Все текущее содержимое Debug Monitor переносится без функциональных изменений
  во вкладку «Состояние» / «State».
- Новый код вкладки находится в отдельном модуле
  lswitch/ui/conversion_trace_tab.py.
- Новая вкладка не читает legacy labels, legacy event log и приватные поля
  существующих секций монитора.

Такое разделение позволит позже заменить устаревшую вкладку «Состояние» без
изменения модели и UI трассировщика.

### 2.2 Что считается записью

Одна строка истории соответствует одной проверке слова в конкретном conversion
flow или одной ручной операции, а не одному raw key event.

В историю попадают:

- space auto-conversion: решения convert, keep, skip и execution error;
- mid-word auto-conversion: все prefix-проверки одного набираемого слова,
  объединенные в одну запись;
- ручная конвертация: выбор режима и результат исполнения;
- отмененная операция, если решение уже начало формироваться;
- ошибка после решения «конвертировать».

Одно набираемое слово может получить две связанные записи: MID_WORD во время
набора и SPACE_AUTO на границе слова. Это разные алгоритмы с разными
решениями, поэтому объединять их steps в одно решение нельзя. Обе записи
получают общий correlation_id, а UI показывает связь между ними.

Если соответствующая auto-функция выключена, на каждое вводимое слово запись не
создается. Трассировка начинается только после входа кандидата в активный
conversion flow.

### 2.3 Решение и исполнение

Решение алгоритма и результат исполнения — разные поля:

~~~text
decision = CONVERT
execution = FAILED(layout_switch)
~~~

Такой случай нельзя показывать как «алгоритм решил оставить слово». Это
маскировало бы реальную проблему backend-а.

### 2.4 Срок жизни и приватность

- Трассировка работает только при effective debug.
- Process-level override --trace также включает ее.
- История хранится только в памяти процесса.
- Максимум — 200 записей, старые записи вытесняются.
- При выключении effective debug recorder прекращает запись и очищает историю.
- Уже открытый Debug Monitor не закрывается принудительно: новая вкладка
  показывает состояние «Трассировка выключена», а tray action скрывается по
  существующему runtime-контракту.
- При завершении процесса история исчезает.
- Автоматической записи слов в обычный log, config или файл нет.
- Копирование трассы выполняется только явной кнопкой.
- Очень длинные selection ограничиваются 256 символами с явным признаком
  truncation.
- Raw keycodes, device names и содержимое clipboard в новую модель не входят.

Очистка при выключении debug является намеренным privacy-контрактом. Если
позднее понадобится сохранять историю между включениями, это должно быть
отдельным продуктовым решением.

### 2.5 Первый релиз

В первый релиз входят:

- bounded history;
- фильтры;
- поиск;
- pause/resume отображения;
- очистка;
- копирование выбранной трассы в текстовом виде;
- RU/EN локализация;
- подробные auto, mid-word и manual traces.

Экспорт JSON и сохранение сессии в файл остаются за границами первого релиза.
Модель при этом должна позволять добавить сериализацию без разбора UI-текста.

## 3. Исходное состояние

### 3.1 Debug Monitor

lswitch/ui/debug_monitor.py сейчас строит одно окно с вертикальным splitter:

- Current State;
- Event Buffer;
- Last Word;
- Auto Marker;
- Platform Selection;
- Event Log.

Окно напрямую опрашивает внутреннее состояние приложения и подписывается на
raw events. Его Event Log — человекочитаемый поток строк. Этот поток не содержит
надежной структуры для визуализации решений.

В lswitch/ui/context_menu.py окно создается по требованию и получает app и
EventBus. Action доступен при effective debug.

### 3.2 Conversion events

В lswitch/core/events.py объявлены CONVERSION_START, CONVERSION_COMPLETE и
CONVERSION_CANCELLED, а ConversionEventData содержит только:

- original;
- converted;
- mode;
- is_auto.

Этого недостаточно для правил, промежуточных фактов и execution steps. Кроме
того, текущие conversion flows фактически не публикуют полный жизненный цикл
через эти события. Расширять ConversionEventData десятками optional-полей не
следует.

### 3.3 Детекторы

AutoDetector.should_convert возвращает пару bool и reason string. Внутренние
проверки после return теряются:

- корректность кандидата;
- user dictionary override/protection;
- source dictionary match;
- target dictionary match;
- source и target n-gram scores;
- delta и threshold;
- zero-source fallback;
- отсутствие доказательств.

DictionaryService.should_convert также возвращает строковую причину.

MidWordDetector уже возвращает MidWordDecision с несколькими структурированными
полями, но не хранит упорядоченный список проверенных правил и устойчивые rule
IDs.

### 3.4 Точки исполнения

В lswitch/core/conversion_use_cases.py находятся:

- SpaceAutoConversionUseCase;
- MidWordAutoConversionUseCase;
- ManualConversionUseCase;
- выбор и исполнение retype/selection paths.

Именно use-case boundary знает одновременно candidate, detector decision и
фактический результат ввода. Поэтому финальная запись должна собираться здесь,
а не внутри GUI и не только внутри детектора.

## 4. Нужен ли предварительный рефакторинг

Да, но только локальный и поведенчески нейтральный.

Нельзя строить новый инструмент на разборе строк вида «ngram score suggests
conversion». Формулировки изменятся при локализации, а часть данных вообще не
попадает в log.

Перед UI нужны три небольших изменения:

1. AutoDetector получает структурированный метод evaluate.
2. DictionaryService отдает структурированные evidence/facts.
3. MidWordDecision дополняется стабильными rule steps.

Для безопасной миграции AutoDetector.should_convert временно остается
compatibility wrapper:

~~~text
evaluate(word, layout) -> AutoDecision
should_convert(word, layout) -> (decision.should_convert, decision.reason)
~~~

Сначала все существующие detector tests должны проходить через wrapper без
изменения ожидаемого поведения. Затем production use cases переводятся на
evaluate. После миграции wrapper можно оставить как небольшой публичный
адаптер либо удалить отдельным cleanup-коммитом.

Рефакторинг не должен:

- менять порядок правил;
- менять thresholds;
- повторно вычислять словари или n-gram scores ради трассы;
- переносить conversion policy в UI;
- затрагивать переписывание legacy Debug Monitor.

## 5. Архитектура

Предлагаемая схема:

~~~text
AutoDetector / MidWordDetector / ConversionEngine
                  |
          structured decisions
                  |
Space / Mid-word / Manual use cases
          + execution steps
                  |
        DecisionTraceRecorder
        - thread-safe deque(200)
        - effective-debug gate
        - monotonically increasing IDs
                  |
        EventBus notification
                  |
          Qt signal bridge
                  |
        ConversionTraceTab
~~~

Recorder создается один раз в RuntimeCoreComponents рядом с EventBus и живет
независимо от окна, platform adapter-ов и пересоздаваемых detector-ов. Поэтому
вкладка при первом открытии видит backlog, накопленный с момента включения
debug, а runtime reload не теряет recorder instance.

Окно не является владельцем recorder-а. Закрытие окна не останавливает сбор
трасс.

## 6. Доменная модель

Новый модуль: lswitch/core/decision_trace.py.

### 6.1 Enum-ы

Предлагаемые enum-ы:

~~~text
TraceTrigger
  SPACE_AUTO
  MID_WORD
  MANUAL
  UNDO

DecisionOutcome
  CONVERT
  KEEP
  SKIP
  ERROR

ExecutionOutcome
  NOT_STARTED
  SUCCEEDED
  CANCELLED
  FAILED

StepState
  MATCHED
  NOT_MATCHED
  SKIPPED
  SUCCEEDED
  FAILED
~~~

SKIP означает, что conversion flow был активен, но candidate не дошел до
основной эвристики: например, слово короче minimum length. KEEP означает
осознанное решение детектора оставить допустимый candidate.

### 6.2 Immutable value objects

Предлагаемые frozen dataclass-ы:

~~~text
TraceFact
  key: str
  value: str | int | float | bool | None

DecisionTraceStep
  rule_id: str
  state: StepState
  decisive: bool
  facts: tuple[TraceFact, ...]

DecisionAttempt
  candidate: str
  converted_candidate: str | None
  source_lang: str | None
  target_lang: str | None
  outcome: DecisionOutcome
  steps: tuple[DecisionTraceStep, ...]
  duration_ms: float

DecisionTrace
  trace_id: int
  correlation_id: int
  created_at: datetime
  trigger: TraceTrigger
  original: str
  converted: str | None
  source_lang: str | None
  target_lang: str | None
  decision: DecisionOutcome
  execution: ExecutionOutcome
  lifecycle: TraceLifecycle
  conversion_mode: str | None
  attempts: tuple[DecisionAttempt, ...]
  execution_steps: tuple[DecisionTraceStep, ...]
  duration_ms: float
  truncated: bool
~~~

Для обычного space/manual flow attempts содержит один элемент. Для mid-word
каждая prefix-проверка становится отдельным DecisionAttempt внутри одной
DecisionTrace. duration_ms учитывает только время вычисления/исполнения, но не
паузы пользователя между буквами.

facts — tuple отдельных immutable значений, а не mutable dict. Запись не должна
содержать ссылки на текущий config, dictionary service или layout object.

### 6.3 Rule ID и UI-текст

Core хранит устойчивый rule_id, а не переведенную строку. Например:

~~~text
candidate.empty
candidate.non_alphabetic
candidate.min_length
auto.buffer_threshold
auto.user_dictionary.override
auto.user_dictionary.protection
auto.source_dictionary.match
auto.target_dictionary.match
auto.ngram.delta
auto.ngram.zero_source
auto.no_evidence
midword.prefix_length
midword.case
midword.source_prefix
midword.target_prefix
midword.user_protection
manual.mode.backspace_selection
manual.mode.buffer_retype
manual.mode.fresh_selection
manual.mode.expand_fallback
execution.target_layout
execution.layout_switch
execution.delete
execution.replay
execution.clipboard
execution.success
execution.error
~~~

В lswitch/i18n.py добавляется registry подписей и описаний rule IDs для RU/EN.
Неизвестный rule_id показывается как сам ID и не ломает вкладку.

Rule ID являются частью внутреннего диагностического API. Их изменения требуют
явной миграции tests и formatter-а.

## 7. DecisionTraceRecorder

Recorder предоставляет небольшой API:

~~~text
record(trace_draft) -> DecisionTrace
upsert_attempt(correlation_id, trigger, attempt) -> DecisionTrace
close_session(correlation_id) -> None
snapshot() -> tuple[DecisionTrace, ...]
clear() -> None
reconfigure(enabled: bool) -> None
enabled -> bool
~~~

Требования:

- внутри используется deque(maxlen=200);
- доступ защищен threading.RLock;
- trace_id назначается recorder-ом монотонно;
- snapshot копирует ссылки только на immutable записи;
- record при выключенном recorder-е является дешевым no-op;
- исключение EventBus subscriber-а никогда не влияет на conversion;
- после добавления записи публикуется DECISION_TRACE_RECORDED;
- clear публикует DECISION_TRACE_CLEARED, чтобы открытая вкладка очистилась;
- медленный GUI subscriber не должен выполняться под lock;
- trace formatting и локализация не выполняются под lock;
- record не делает I/O.

Payload notification должен содержать immutable DecisionTrace либо trace_id.
Полная запись предпочтительнее: вкладке не потребуется дополнительный lookup,
а max history eviction не создаст гонку. При открытии вкладка все равно берет
snapshot recorder-а.

## 8. Instrumentation алгоритмов

### 8.1 AutoDetector

Новый AutoDecision содержит:

- should_convert;
- stable final_reason_id;
- original;
- converted;
- source_lang;
- target_lang;
- ordered steps.

Порядок steps обязан повторять существующий порядок short-circuit правил:

1. candidate validation;
2. user dictionary override/protection;
3. already-correct source dictionary word;
4. converted target dictionary word;
5. n-gram comparison;
6. zero-source fallback;
7. no-evidence keep.

Каждый достигнутый branch добавляет step. Правила после decisive short-circuit
не нужно искусственно запускать. UI внизу показывает «Дальнейшие правила не
проверялись после решающего результата», а не создает фиктивные вычисления.

Для n-gram step фиксируются вычисленные в этот момент:

- source_score;
- target_score;
- delta;
- threshold;
- minimum length для zero-source fallback.

UI не вызывает NgramAnalyzer повторно.

### 8.2 DictionaryService

Структурированный результат должен различать:

- source full-word match;
- target full-word match;
- miss;
- язык и нормализованное слово;
- user dictionary weight и configured threshold;
- disabled/unavailable dictionary, если это влияет на branch.

Нельзя выводить «словарь не найден» только потому, что слово не найдено.
Unavailable resource и обычный miss — разные факты.

Текущий PrefixDictionary объединяет built-in и system words в одно множество.
Поэтому первый релиз честно показывает combined prefix count и активные пути
system dictionaries, но не заявляет точный источник каждого prefix match.

Чтобы активные источники можно было показать без обращения к GUI/app internals,
PrefixDictionary при построении получает immutable source metadata для каждого
языка: built-in source и SystemDictionaryStatus с resolved path/status.
Метаданные не содержат сами word sets и не меняют lookup API.

Отдельное происхождение «built-in / Hunspell / user dictionary» потребует
provenance-aware index и остается будущим расширением. Полный word match через
существующие отдельные сервисы показывается с доступной фактической
provenance.

### 8.3 MidWordDetector

Существующий MidWordDecision сохраняется и расширяется:

- rule steps;
- final_reason_id;
- converted prefix;
- source/target counts;
- configured minimum prefix count;
- user dictionary protection weight/threshold.

Порядок branches остается текущим:

1. empty/invalid;
2. minimum prefix length;
3. mixed case/uppercase protection;
4. source prefix existence;
5. target prefix minimum count;
6. user dictionary protection;
7. switch.

### 8.4 Manual conversion

Ручная операция не должна притворяться результатом AutoDetector. Ее trace
показывает выбор режима ConversionEngine:

1. backspace hold -> selection;
2. typed buffer -> retype;
3. fresh selection -> selection;
4. fallback -> selection expand.

Далее показываются:

- найден ли original text;
- определены ли source/target layouts;
- выбранный conversion mode;
- удалось ли переключить layout;
- удалось ли удалить исходный текст;
- удалось ли replay/type/paste результата;
- восстановлена ли исходная layout по policy;
- итог или exception class/message.

Exception message перед сохранением ограничивается безопасной длиной и не
должно содержать clipboard content.

## 9. Корреляция mid-word попыток

Mid-word detector вызывается после отпускания каждой текстовой клавиши. Если
каждую попытку показывать отдельной строкой, история заполнится префиксами
одного слова и перестанет отвечать требованию «путь каждого слова».

Нужна word session:

- InputEventRouter хранит monotonically increasing word_session_id;
- первый текстовый символ открывает сессию;
- сигнатуры InputConversionPort для space и mid-word callbacks получают этот
  ID;
- каждая mid-word проверка передает ID в use case;
- recorder обновляет MID_WORD trace текущей сессии и добавляет
  DecisionAttempt;
- space flow получает тот же ID, создает отдельный SPACE_AUTO trace и затем
  закрывает сессию;
- Space закрывает сессию после space flow, а при выключенном space auto —
  сразу на boundary;
- Enter, navigation, mouse click, buffer reset и manual completion закрывают
  логическую сессию;
- успешный mid-word switch финализирует текущий trace-сегмент, но сохраняет
  correlation ID до реальной границы слова; дописанный хвост создаёт связанную
  активную запись;
- Backspace продолжает ту же сессию, но следующая проверка содержит новый
  candidate snapshot;
- новая буква после boundary открывает новый ID.

Пока сессия активна, recorder может публиковать update notification с тем же
trace_id. В UI строка обновляется на месте, а не добавляется повторно.

Чтобы immutable public history не конфликтовала с накоплением:

- mutable builder существует только внутри recorder-а под lock;
- после каждой попытки наружу публикуется новый frozen DecisionTrace snapshot;
- в deque snapshot с тем же trace_id заменяется атомарно;
- закрытие сессии только запрещает дальнейшее обновление этой записи.

Тесты обязаны покрыть границы сессии, Backspace и успешный switch.

## 10. Instrumentation use cases

### 10.1 SpaceAutoConversionUseCase

Trace получает текущий correlation_id после входа в активный space auto flow и
включает gates:

- detector available;
- chars_in_buffer;
- последний buffered event не является Space, то есть это не повторная
  проверка уже завершенного слова;
- auto_switch_threshold;
- current layout available;
- candidate extraction;
- SpaceAutoConversionUseCase.min_word_len;
- AutoDecision;
- conversion execution.

Результат use case дополняется trace metadata либо use case получает recorder
как dependency. Предпочтительнее dependency и один finalize в finally-блоке,
чтобы execution exception не потерял начатый trace.

### 10.2 MidWordAutoConversionUseCase

Use case получает word_session_id и добавляет attempt:

- candidate;
- current layout;
- MidWordDecision steps;
- switch/replay steps, если решение положительное.

Отрицательное prefix-решение не считается ошибкой. Финальная строка может иметь
статус KEEP до следующего обновления, а после успешного switch — CONVERT.

### 10.3 ManualConversionUseCase

Trace создается на каждый фактический manual request. Если текста для операции
нет, результат SKIP с rule manual.no_candidate.

Learning/user dictionary update после успешной конвертации показывается
отдельным execution step, но сбой диагностической записи не должен менять
результат самой conversion.

### 10.4 Undo

Если undo использует отдельный use case, он получает trigger UNDO и те же
execution steps. Если текущая реализация undo является частью manual path,
первый этап допускает общий instrumentation helper, но trigger в данных должен
оставаться отдельным.

## 11. Runtime wiring и lifecycle

DecisionTraceRecorder создается в lswitch/runtime.py внутри
create_core_components после EventBus и добавляется в RuntimeCoreComponents.
Он передается в use cases через dependency injection и не пересоздается вместе
с platform runtime, AutoDetector или MidWordDetector. Глобальный singleton не
используется.

LSwitchApp:

- хранит ссылку на recorder;
- включает его из effective debug, а не только из config.toml debug;
- учитывает --debug и --trace precedence;
- при live CONFIG_CHANGED вызывает recorder.reconfigure;
- при выключении очищает recorder и переводит открытую вкладку в disabled
  state, не закрывая legacy monitor;
- при включении начинает собирать backlog до первого открытия окна.

Context menu передает recorder в DebugMonitorWindow. Window передает его только
ConversionTraceTab; legacy tab продолжает использовать существующие app и
EventBus dependencies.

Новые события:

~~~text
DECISION_TRACE_RECORDED
DECISION_TRACE_UPDATED
DECISION_TRACE_CLEARED
~~~

RECORDED и UPDATED можно объединить в DECISION_TRACE_CHANGED, если payload
всегда содержит полный snapshot. Выбор закрепить в первом implementation
commit и не дублировать два механизма.

## 12. Потоки и отказоустойчивость

Input events и detector calls могут приходить не из Qt GUI thread. Поэтому:

- EventBus callback ConversionTraceTab не трогает widgets;
- callback emit-ит Qt signal с immutable payload;
- slot изменяет model/widgets уже в GUI thread;
- closeEvent отписывает вкладку от всех trace events;
- повторное открытие не создает двойных subscriptions;
- event после закрытия безопасно игнорируется;
- selection по trace_id сохраняется при вставке или обновлении строки.

Трассировщик является best-effort диагностикой:

- ошибка формирования trace логируется один раз и не прерывает ввод;
- ошибка GUI subscriber-а подавляется существующим EventBus contract;
- formatter не участвует в conversion path;
- trace instrumentation не содержит sleep, disk I/O и clipboard reads.

Ориентир overhead при включенном debug — менее 1 мс поверх уже выполненных
словарных/n-gram вычислений для обычной проверки. При выключенном debug
дополнительная работа ограничивается одним enabled check.

## 13. UI новой вкладки

### 13.1 Компоновка

Вкладка строится как master-detail:

~~~text
+--------------------------------------------------------------------+
| [Все] [Конверт.] [Оставлены] [Ошибки]  Поиск...  [Пауза]          |
+-------------------------------+------------------------------------+
| 14:18:35  ghbdtn -> привет    | SPACE AUTO                         |
| Конвертировано                | ghbdtn -> привет                    |
|                               | EN -> RU, 1.4 ms                    |
| 14:18:29  world               |                                    |
| Оставлено                     |  1  Candidate valid            ✓    |
|                               |  2  User dictionary            —    |
|                               |  3  Source dictionary          —    |
|                               |  4  Target dictionary          ✓    |
|                               |     decisive: target match          |
+-------------------------------+------------------------------------+
| [Очистить]                                      [Копировать трассу]|
+--------------------------------------------------------------------+
~~~

Левая часть:

- время;
- original -> converted;
- outcome badge;
- trigger;
- индикатор связанной MID_WORD/SPACE_AUTO записи с тем же correlation_id;
- одна строка на trace_id.

Правая часть:

- summary;
- source/target languages и mode;
- ordered decision attempts;
- ordered execution steps;
- decisive rule;
- facts с единицами;
- duration;
- явный execution error.

Для mid-word attempts показываются как collapsible группы:

~~~text
Attempt «gh»      keep: prefix too short
Attempt «ghb»     keep: target prefix count 0
Attempt «ghbd»    convert: target prefix count 12
Execution         success
~~~

### 13.2 Фильтры и поиск

Фильтры:

- Все;
- Конвертированы;
- Оставлены/пропущены;
- Ошибки.

Поиск проверяет:

- original;
- converted;
- rule_id;
- localized rule label;
- trigger/mode.

Фильтрация работает по model snapshot, а не удаляет записи из recorder-а.

### 13.3 Pause

Pause замораживает только визуальные обновления:

- recorder продолжает bounded collection;
- notification count можно показать рядом с кнопкой;
- Resume полностью перечитывает snapshot;
- Pause не влияет на conversion и debug lifecycle.

### 13.4 Clear и Copy

Clear:

- вызывает recorder.clear;
- очищает обе панели;
- сбрасывает selection;
- не выключает recorder.

Copy Trace:

- форматирует только выбранную запись;
- использует локализованные labels и добавляет stable rule IDs;
- не копирует невидимые raw events;
- отключена при отсутствии selection.

### 13.5 Цвет и доступность

- красный используется только для ошибок;
- convert — accent/blue;
- успешный keep — green;
- not matched/skipped — neutral gray;
- heuristic warning — amber;
- decisive step имеет icon, text и font weight, а не только цвет;
- статусы доступны в текстовом виде для screen reader;
- вкладка корректно работает со светлой и темной системной темой;
- длинные слова и facts elide-ятся в списке, но переносятся в detail panel.

## 14. Локализация

Все новые пользовательские строки добавляются в lswitch/i18n.py:

- названия вкладок;
- toolbar actions;
- empty state;
- filters/outcomes;
- trigger names;
- execution statuses;
- rule labels и explanations;
- privacy hint для Copy;
- unknown rule fallback.

Core reason strings не используются как готовый UI. Для логов compatibility
formatter может по-прежнему выдавать английскую краткую строку.

## 15. Этапы реализации

### Этап 0. Characterization tests

- Зафиксировать текущие ветви AutoDetector.should_convert.
- Зафиксировать порядок приоритетов user/built-in/ngram правил.
- Зафиксировать MidWordDecision branches.
- Зафиксировать ConversionEngine mode selection.
- Сохранить behavior tests до изменения signatures.

Результат: последующий рефакторинг можно доказуемо считать поведенчески
нейтральным.

### Этап 1. Trace domain и recorder

- Добавить enum-ы и frozen dataclass-ы.
- Добавить bounded thread-safe recorder.
- Добавить trace event.
- Покрыть lifecycle, eviction и concurrency tests.
- Не подключать пока GUI.

### Этап 2. Structured auto decisions

- Добавить AutoDetector.evaluate.
- Добавить structured dictionary evidence.
- Оставить compatibility should_convert.
- Не менять порядок/thresholds.
- Добавить точные ordered-step tests для каждой ветви.

### Этап 3. Structured mid-word decisions

- Добавить stable rule IDs и steps в MidWordDecision.
- Реализовать word_session_id.
- Добавить immutable prefix attempt aggregation.
- Покрыть boundary/Backspace/switch tests.

### Этап 4. Auto use-case instrumentation

- Подключить recorder к space flow.
- Подключить recorder к mid-word flow.
- Разделить detector decision и execution outcome.
- Гарантировать finalize при exception.
- Проверить, что вычисления не повторяются.

### Этап 5. Manual и undo instrumentation

- Трассировать mode selection.
- Трассировать layout/delete/replay/clipboard/restore stages.
- Подключить learning step.
- Подключить undo trigger.

### Этап 6. Runtime и effective-debug lifecycle

- Создать recorder в composition root.
- Передать dependency во все use cases.
- Подключить --debug/--trace/config precedence.
- Реализовать clear/disabled state при выключении.
- Проверить backlog до открытия окна.

### Этап 7. Независимая вкладка

- Создать ConversionTraceTab.
- Добавить master-detail model.
- Добавить Qt signal bridge.
- Реализовать filters/search/pause/clear/copy.
- Обернуть legacy monitor во вкладку «Состояние».
- Сделать «Конвертации» вкладкой по умолчанию.

### Этап 8. i18n, polish и документация

- Добавить RU/EN строки.
- Проверить темы, keyboard navigation и eliding/wrapping.
- Добавить manual testing document.
- Обновить README debug section.
- Зафиксировать JSON export как future work.

## 16. Automated tests

### 16.1 Qt-free unit tests

Decision trace model:

- frozen values нельзя изменить;
- facts не удерживают mutable config;
- formatter корректно обрабатывает unknown IDs;
- truncation отмечается.

Recorder:

- сохраняет порядок;
- вытесняет запись 201;
- назначает уникальные IDs;
- snapshot безопасен при параллельной записи;
- disabled record — no-op;
- reconfigure(false) очищает history;
- clear публикует notification;
- subscriber failure не ломает record.

Auto decisions:

- empty/invalid candidate;
- user override;
- user protection;
- already-correct source word;
- target dictionary match;
- n-gram delta;
- zero-source fallback;
- no evidence;
- unavailable dictionary;
- steps после decisive branch не вычисляются.

Mid-word decisions:

- minimum prefix length;
- case protection;
- source prefix exists;
- target prefix missing;
- user dictionary protection;
- successful switch;
- несколько prefixes объединяются в один trace;
- MID_WORD и SPACE_AUTO одного слова получают общий correlation_id;
- Backspace обновляет session;
- boundary закрывает session.

Use cases:

- CONVERT decision + successful execution;
- CONVERT decision + layout failure;
- KEEP без execution;
- SKIP на gate;
- exception сохраняет FAILED trace и пробрасывается/обрабатывается по прежнему
  контракту;
- manual mode priority;
- original layout restore;
- learning step.

### 16.2 Runtime integration tests

- effective debug включает recorder;
- --trace удерживает recorder включенным;
- config debug off очищает recorder и отключает открытую trace tab;
- запись накапливается до первого открытия окна;
- runtime reload не создает второй recorder;
- все use cases получают тот же recorder instance;
- EventBus callbacks не меняют conversion result.

### 16.3 GUI tests

- Debug Monitor содержит две вкладки;
- «Конвертации» выбрана по умолчанию;
- legacy widgets остались во вкладке «Состояние»;
- backlog появляется при открытии;
- новый trace добавляется через Qt signal;
- update с тем же trace_id заменяет строку;
- filters и search не меняют store;
- pause/resume перечитывает snapshot;
- clear очищает model и detail;
- selection сохраняется при новой записи;
- copy formatter работает для RU/EN;
- unknown rule не вызывает exception;
- close/reopen не удваивает subscriptions;
- empty/error/truncated states отображаются.

Текущий tests/test_debug_monitor.py использует собственное дерево PyQt mocks.
На этапе 7 нужно либо расширить mocks для QTabWidget и новых model widgets,
либо перевести новые сценарии на offscreen Qt tests. Старые characterization
tests legacy tab удалять нельзя.

## 17. Manual QA

Проверить минимум следующие сценарии:

1. Включить debug, набрать слово, открыв monitor только после этого: trace есть.
2. Слово уже корректно в source dictionary: KEEP с решающим source match.
3. Слово распознано после конвертации: CONVERT с target match.
4. Решение принято по n-gram: видны оба score, delta и threshold.
5. User dictionary override и protection имеют больший приоритет.
6. Mid-word prefixes объединены в одну строку и раскрываются по порядку.
7. Ошибка layout switch не меняет decision CONVERT, execution имеет FAILED.
8. Manual retype и selection показывают разные mode paths.
9. Pause не прекращает collection; Resume показывает пропущенные UI updates.
10. Clear очищает текущую историю, следующая запись появляется нормально.
11. Выключение debug удаляет историю и отключает trace tab, не закрывая окно.
12. RU/EN переключение локализует UI, сохраняя stable rule IDs в Copy Trace.
13. Светлая и темная темы не используют цвет как единственный индикатор.
14. 201-я запись вытесняет самую старую без потери текущего selection ID.

## 18. Критерии приемки

Задача считается завершенной, когда:

- Debug Monitor имеет независимые вкладки «Конвертации» и «Состояние»;
- старое содержимое функционально не смешано с новым;
- для каждого активного conversion flow существует structured trace;
- для auto decisions виден точный порядок достигнутых правил;
- решающее правило выделено;
- словарные веса/counts и n-gram scores показаны без повторного вычисления;
- mid-word attempts сгруппированы по слову;
- decision и execution result визуально разделены;
- вкладка безопасна для событий из non-GUI thread;
- история bounded, memory-only и очищается при debug off;
- filters/search/pause/clear/copy работают;
- RU/EN локализация завершена;
- существующие conversion tests проходят без изменения поведения;
- добавлены unit, integration и offscreen GUI tests;
- manual checklist пройден в доступных X11/Wayland окружениях.

## 19. Риски и меры

### Изменение поведения при рефакторинге детектора

Мера: characterization tests до изменения API, compatibility wrapper и
сравнение результата старого/new API на одном наборе cases.

### Замедление hot path

Мера: фиксировать уже вычисленные facts, не вызывать сервисы повторно, frozen
snapshot собирать только при enabled recorder-е.

### Flood mid-word записей

Мера: word_session_id и update одной строки вместо trace на каждую букву.

### Гонки GUI и input threads

Мера: lock только внутри recorder-а, immutable payload и Qt queued signal.

### Утечка набираемого текста

Мера: debug-only, memory-only, max 200, clear on disable, explicit Copy,
truncation и отсутствие raw events.

### Ложная детализация словарного источника

Мера: не обещать provenance, которого нет в объединенном PrefixDictionary;
показывать combined evidence и отдельно спланировать provenance-aware index.

### Связывание с устаревшим монитором

Мера: отдельный ConversionTraceTab с собственными dependencies и model; старый
UI только оборачивается tab container-ом.

## 20. Рекомендуемая разбивка коммитов

1. add conversion trace domain and recorder
2. expose structured auto detector decisions
3. expose structured mid-word decision steps
4. instrument automatic conversion traces
5. instrument manual conversion execution traces
6. wire trace recorder to effective debug lifecycle
7. add conversion trace debug monitor tab
8. localize and document conversion trace inspector

Каждый коммит должен проходить относящиеся к нему tests. Поведенческий
рефакторинг детектора и визуальная реализация не объединяются в один большой
коммит.
